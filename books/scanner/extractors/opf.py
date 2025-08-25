from lxml import etree as ET
from books.models import (
    DataSource, BookTitle, BookMetadata,
    Publisher, BookPublisher, Series, BookSeries
)
from books.utils.author import attach_authors
from books.utils.language import normalize_language
from books.utils.isbn import normalize_isbn
import logging
import re

logger = logging.getLogger("books.scanner")


def extract(book):
    try:
        if not book.opf_path:
            return

        source = DataSource.objects.get(name=DataSource.OPF_FILE)

        with open(book.opf_path, 'r', encoding='utf-8') as f:
            root = ET.parse(f).getroot()

        ns = {
            'opf': 'http://www.idpf.org/2007/opf',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }

        # Title
        title_elem = root.find('.//dc:title', ns)
        if title_elem is not None and title_elem.text:
            BookTitle.objects.get_or_create(
                book=book,
                title=title_elem.text.strip(),
                source=source,
                defaults={'confidence': 0.95}
            )

        # Authors
        creators = root.findall('.//dc:creator', ns)
        raw_names = [c.text.strip() for c in creators if c.text]
        attach_authors(book, raw_names, source, confidence=0.95)

        # Publisher (handled separately from OPF .xml)
        pub_elem = root.find('.//dc:publisher', ns)
        if pub_elem is not None and pub_elem.text:
            pub_name = pub_elem.text.strip()
            if pub_name:
                existing_pub = Publisher.objects.filter(name__iexact=pub_name).first()
                if existing_pub:
                    pub_obj = existing_pub
                else:
                    pub_obj = Publisher.objects.create(name=pub_name)

                BookPublisher.objects.get_or_create(
                    book=book,
                    publisher=pub_obj,
                    source=source,
                    defaults={"confidence": 0.9}
                )

        # Series metadata (Calibre-style)
        series_name_elem = root.find('.//opf:meta[@name="calibre:series"]', ns)
        series_index_elem = root.find('.//opf:meta[@name="calibre:series_index"]', ns)

        if series_name_elem is not None and series_name_elem.get('content'):
            series_name = series_name_elem.get('content').strip()
            volume = None
            if series_index_elem is not None and series_index_elem.get('content'):
                volume = series_index_elem.get('content').strip()

            series_obj, _ = Series.objects.get_or_create(name__iexact=series_name)
            BookSeries.objects.get_or_create(
                book=book,
                series=series_obj,
                defaults={"volume_number": volume, "confidence": 0.9, "source": source}
            )

        # Field extraction
        field_map = {
            'language': 'language',
            'identifier': 'isbn',
            'description': 'description',
            'date': 'publication_year',
        }

        for dc_field, model_field in field_map.items():
            elem = root.find(f'.//dc:{dc_field}', ns)
            if elem is not None and elem.text:
                value = elem.text.strip()
                if not value:
                    continue
                if model_field == "language":
                    value = normalize_language(value)
                elif model_field == "isbn":
                    value = normalize_isbn(value)
                elif model_field == "publication_year":
                    match = re.search(r"\b\d{4}\b", value)
                    if match:
                        BookMetadata.objects.get_or_create(
                            book=book,
                            field_name=model_field,
                            source=source,
                            defaults={"field_value": match.group(), "confidence": 0.9}
                        )
                else:
                    BookMetadata.objects.get_or_create(
                        book=book,
                        field_name=model_field,
                        source=source,
                        defaults={"field_value": value, "confidence": 0.9}
                    )

    except Exception as e:
        logger.warning(f"OPF metadata extraction failed for {book.opf_path}: {e}")
