"""End-to-end test: scanning a Dutch EPUB whose embedded metadata declares
English (filed in an English folder) must resolve FinalMetadata.language to the
content language ("nl") and record the embedded contradiction as designed
(LANGUAGE_DISAGREEMENT), which the resolver must not clobber. An English-only
book in the English folder must resolve cleanly to "en" with no flag."""

import shutil
import tempfile
from pathlib import Path

from django.test import TestCase

from books.models import BookMetadata, DataSource, FinalMetadata, ScanFolder, UnresolvedReason
from books.scanner.folder import scan_directory

DUTCH_CHAPTER = (
    "Nederland is een land in West-Europa dat bekend staat om zijn windmolens, "
    "tulpen en grachten. De hoofdstad van Nederland is Amsterdam, maar de regering "
    "zetelt in Den Haag. De Nederlandse taal wordt door ongeveer vierentwintig "
    "miljoen mensen gesproken, zowel in Nederland als in Vlaanderen en Suriname. "
    "Veel Nederlanders spreken daarnaast ook Engels en Duits, omdat deze talen op "
    "school worden onderwezen. De Nederlandse literatuur kent vele beroemde "
    "schrijvers, zoals Multatuli, Louis Couperus en Annie M.G. Schmidt. Kinderen "
    "in Nederland lezen graag boeken zoals Jip en Janneke, geschreven door Annie "
    "Schmidt. De Nederlandse keuken bestaat onder andere uit stamppot, haring en "
    "poffertjes. Elk jaar in april viert Nederland Koningsdag, een nationale "
    "feestdag met vrijmarkten en oranje kleding. De Nederlandse geschiedenis is "
    "rijk aan handel, kunst en ontdekkingsreizen over de wereldzeeën. De grachten "
    "van Amsterdam, Utrecht en Leiden trekken jaarlijks miljoenen bezoekers aan. "
    "Het koninklijk huis speelt een ceremoniële rol in de Nederlandse samenleving. "
    "De Nederlandse infrastructuur voor fietsers behoort tot de beste ter wereld. "
    "Kaas, drop en stroopwafels zijn bekende Nederlandse lekkernijen die wereldwijd "
    "worden gegeten. Het Nederlandse onderwijssysteem staat bekend om zijn hoge "
    "kwaliteit en toegankelijkheid voor iedereen. De Waddenzee is een uniek "
    "natuurgebied dat op de werelderfgoedlijst van UNESCO staat."
)

ENGLISH_CHAPTER = (
    "English is a West Germanic language that originated in medieval England and "
    "is now the most widely spoken language in the world. It is the official or "
    "primary language of many countries, including the United Kingdom, the United "
    "States, Canada, Australia, and New Zealand. English literature has produced "
    "celebrated authors such as William Shakespeare, Charles Dickens, Jane Austen, "
    "and Mark Twain. The language has a rich vocabulary borrowed from Latin, "
    "French, and Germanic roots, giving it one of the largest lexicons of any "
    "language. English grammar is relatively simple compared to many other "
    "languages, but its spelling is famously irregular and often confuses learners. "
    "Every year thousands of new words are added to English dictionaries as the "
    "language continues to evolve and adapt to modern life. English is the dominant "
    "language of science, technology, business, and international communication. "
    "Many people study English as a second language because it opens doors to "
    "education and employment around the world. The history of the English language "
    "is a story of invasion, trade, and cultural exchange over more than a thousand "
    "years. Writers and poets have shaped English into a flexible and expressive "
    "medium, capable of both formal prose and everyday conversation. Today English "
    "is spoken by hundreds of millions of people across every continent."
)


def _write_dutch_epub(directory, embedded_language=None):
    """Write a real EPUB whose chapters are all Dutch text.

    ``embedded_language`` optionally declares a (contradicting) dc:language in
    the EPUB's own metadata, so the extraction pipeline records it as embedded
    metadata.
    """
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-dutch-1")
    book.set_title("Nederlands Testboek")
    if embedded_language:
        book.set_language(embedded_language)

    chapters = []
    for i in range(12):
        ch = epub.EpubHtml(
            title=f"Hoofdstuk {i}",
            file_name=f"chap_{i}.xhtml",
        )
        # Repeat the Dutch block several times per chapter for a long body.
        ch.content = f"<html><body><p>{DUTCH_CHAPTER * 3}</p></body></html>"
        book.add_item(ch)
        chapters.append(ch)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    path = Path(directory) / "nederlands_testboek.epub"
    epub.write_epub(str(path), book)
    return str(path)


def _write_english_epub(directory):
    """Write a real EPUB whose chapters are all English text."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-english-1")
    book.set_title("English Test Book")

    chapters = []
    for i in range(12):
        ch = epub.EpubHtml(
            title=f"Chapter {i}",
            file_name=f"chap_{i}.xhtml",
        )
        ch.content = f"<html><body><p>{ENGLISH_CHAPTER * 3}</p></body></html>"
        book.add_item(ch)
        chapters.append(ch)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    path = Path(directory) / "english_test_book.epub"
    epub.write_epub(str(path), book)
    return str(path)


class LanguageSliceWiringEndToEndTests(TestCase):
    def setUp(self):
        self.en_dir = tempfile.mkdtemp(prefix="lang_wiring_en_")
        self.nl_dir = tempfile.mkdtemp(prefix="lang_wiring_nl_")
        self.addCleanup(lambda: shutil.rmtree(self.en_dir, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(self.nl_dir, ignore_errors=True))
        # Register both en and nl as library scan-folder languages. This makes
        # "nl" a registered (in-library) code, so the flag below is the embedded
        # contradiction (the book's own metadata claims English), not an
        # out-of-library detection.
        self.en_folder = ScanFolder.objects.create(
            name="English Folder",
            path=self.en_dir,
            content_type="ebooks",
            language="en",
        )
        ScanFolder.objects.create(
            name="Nederlands Folder",
            path=self.nl_dir,
            content_type="ebooks",
            language="nl",
        )

    def test_dutch_book_in_english_folder_records_contradiction(self):
        # A Dutch book filed in the English folder whose embedded metadata
        # declares English: the content code ("nl") wins, and the embedded
        # contradiction is recorded as designed (LANGUAGE_DISAGREEMENT), which
        # the resolver must persist.
        _write_dutch_epub(self.en_dir, embedded_language="en")

        scan_directory(self.en_dir, self.en_folder, enable_external_apis=False)

        fm = FinalMetadata.objects.get(book__scan_folder=self.en_folder)
        self.assertEqual(fm.language, "nl")
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_DISAGREEMENT)

        rows = BookMetadata.objects.filter(
            book=fm.book,
            field_name="language",
            source__name=DataSource.CONTENT_SCAN,
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().field_value, "nl")

    def test_english_book_in_english_folder_clean(self):
        # "en only" case: an English book in the English folder resolves to "en"
        # with a clean result (no language flag, no contradiction).
        _write_english_epub(self.en_dir)

        scan_directory(self.en_dir, self.en_folder, enable_external_apis=False)

        fm = FinalMetadata.objects.get(book__scan_folder=self.en_folder)
        self.assertEqual(fm.language, "en")
        self.assertNotIn(
            fm.unresolved_reason,
            {UnresolvedReason.LANGUAGE_DISAGREEMENT, UnresolvedReason.LANGUAGE_UNDETERMINED},
        )
