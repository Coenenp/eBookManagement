"""End-to-end test: scanning a Dutch EPUB registered in an English folder must
resolve FinalMetadata.language to the content language ("nl"), write exactly one
Content Scan language row, and raise no language flag."""

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


def _write_dutch_epub(directory):
    """Write a real EPUB whose chapters are all Dutch text."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-dutch-1")
    book.set_title("Nederlands Testboek")

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


class LanguageSliceWiringEndToEndTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="lang_wiring_")
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def test_scan_dutch_epub_in_english_folder_resolves_nl(self):
        epub_path = _write_dutch_epub(self.temp_dir)
        folder = ScanFolder.objects.create(
            name="English Folder",
            path=self.temp_dir,
            content_type="ebooks",
            language="en",
        )

        scan_directory(self.temp_dir, folder, enable_external_apis=False)

        fm = FinalMetadata.objects.get(book__scan_folder=folder)
        self.assertEqual(fm.language, "nl")

        rows = BookMetadata.objects.filter(
            book=fm.book,
            field_name="language",
            source__name=DataSource.CONTENT_SCAN,
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().field_value, "nl")

        # No LANGUAGE flag may be raised (folder contradiction is not an error).
        self.assertNotIn(
            fm.unresolved_reason,
            {UnresolvedReason.LANGUAGE_DISAGREEMENT, UnresolvedReason.LANGUAGE_UNDETERMINED},
        )
