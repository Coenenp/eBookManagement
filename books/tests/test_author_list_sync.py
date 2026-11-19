"""Part A: the repacked OPF carries exactly one clean author list from final_author.

``safe_move_book`` builds the author list it writes into the repacked OPF from
``FinalMetadata.final_author`` only (split, de-duplicated, order kept), never
from the per-source author relationship rows, so other books' authors and file
name misparses never leak into the ``dc:creator`` list while the title is
correct.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from django.test import TestCase

from books.models import Author, BookAuthor, DataSource, FinalMetadata, ScanFolder
from books.tests.test_helpers import create_test_book_with_file
from books.tests.test_safe_move_book import _write_default_cover, _write_epub
from books.utils.epub_fix.writer import write_epub
from books.utils.safe_move import safe_move_book
from books.utils.safe_move.metadata_sync import build_epub_metadata

DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"


def _opf_creators(target):
    """Read the dc:creator list straight out of the repacked EPUB's OPF.

    Deliberately independent of ``verify_opf_root`` so a bug that makes the
    built-in check agree with the wrong list cannot hide here.
    """
    from lxml import etree

    with zipfile.ZipFile(target) as z:
        root = etree.fromstring(z.read("OEBPS/content.opf"))
    metadata = root.find(f"{{{OPF_NS}}}metadata")
    creators = metadata.findall(f"{{{DC_NS}}}creator")
    return [(c.text, c.get(f"{{{OPF_NS}}}file-as")) for c in creators]


class AuthorListSyncTests(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.target_dir = self.root / "Moved"
        self.target_dir.mkdir()
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )

    def _source(self, name):
        return DataSource.objects.get_or_create(
            name=name, defaults={"priority": 1, "trust_level": 5}
        )[0]

    def _author_book(self, final_author, author_rows, authors=None):
        """Build a reviewed EPUB book with per-source main-author rows then final metadata.

        ``author_rows`` is ``[(name, source_name, confidence), ...]``. ``authors``
        optionally maps a name to an already-created :class:`Author` to reuse.
        Source rows are created before ``FinalMetadata`` so their save hooks
        cannot re-sync the final author afterwards.
        """
        src = self.scan_root / "sub" / "book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _write_epub(src)
        book = create_test_book_with_file(
            file_path=str(src), file_format="epub", scan_folder=self.scan_folder,
        )
        authors = dict(authors or {})
        for name, source_name, confidence in author_rows:
            author = authors.get(name)
            if author is None:
                author = Author.objects.create(name=name)
                authors[name] = author
            BookAuthor.objects.create(
                book=book, author=author, source=self._source(source_name),
                confidence=confidence, is_main_author=True,
            )
        FinalMetadata.objects.create(
            book=book, final_author=final_author, is_reviewed=True,
            final_cover_path=_write_default_cover(self.scan_root),
        )
        return book, src

    def _authors(self, book):
        return build_epub_metadata(book).get("authors", [])

    # -- (1) mixed source rows collapse to the single final author -----------

    def test_mixed_source_rows_give_single_clean_creator(self):
        book, _ = self._author_book(
            "Robert Newton Peck",
            [
                ("Brian McClellan", DataSource.OPF_FILE, 0.9),
                ("Robert Newton Peck", DataSource.EPUB_INTERNAL, 0.8),
                ("Robert Newton Peck", DataSource.GOOGLE_BOOKS, 0.665),
                ("A Day No Pigs Would Die", DataSource.INITIAL_SCAN, 0.2),
            ],
        )
        self.assertEqual(
            self._authors(book),
            [{"name": "Robert Newton Peck", "file_as": "Peck, Robert Newton"}],
        )

    # -- (2) identical rows still produce one creator ------------------------

    def test_four_identical_rows_give_one_creator(self):
        book, _ = self._author_book(
            "Robert Newton Peck",
            [
                ("Robert Newton Peck", DataSource.EPUB_INTERNAL, 0.8),
                ("Robert Newton Peck", DataSource.GOOGLE_BOOKS, 0.7),
                ("Robert Newton Peck", DataSource.OPEN_LIBRARY, 0.6),
                ("Robert Newton Peck", DataSource.OPF_FILE, 0.5),
            ],
        )
        self.assertEqual(
            [a["name"] for a in self._authors(book)],
            ["Robert Newton Peck"],
        )

    # -- (3) semicolon-separated final author becomes two ordered creators ---

    def test_semicolon_final_author_gives_two_creators_in_order(self):
        book, _ = self._author_book("Ann Lee; Bo Kim", [])
        self.assertEqual(
            [a["name"] for a in self._authors(book)],
            ["Ann Lee", "Bo Kim"],
        )

    # -- (4) a reviewed Author supplies file_as ------------------------------

    def test_reviewed_author_supplies_file_as(self):
        # A reviewed Author exists globally (no relationship row on this book):
        # file_as must come from it, not from a relationship row or sort_name.
        Author.objects.create(
            first_name="Gabriel", last_name="García Márquez", is_reviewed=True
        )
        book, _ = self._author_book("Gabriel García Márquez", [])
        self.assertEqual(
            self._authors(book),
            [{"name": "Gabriel García Márquez", "file_as": "García Márquez, Gabriel"}],
        )

    # -- (5) a second repack changes nothing ---------------------------------

    def test_second_repack_changes_nothing(self):
        book, src = self._author_book(
            "Robert Newton Peck",
            [("Robert Newton Peck", DataSource.EPUB_INTERNAL, 0.8)],
        )
        metadata = build_epub_metadata(book)
        first = self.target_dir / "one.epub"
        second = self.target_dir / "two.epub"
        write_epub(str(src), str(first), metadata=metadata)
        write_epub(str(first), str(second), metadata=metadata)
        self.assertEqual(_opf_creators(first), _opf_creators(second))
        self.assertEqual([c[0] for c in _opf_creators(second)], ["Robert Newton Peck"])

    # -- independent read of the repacked OPF --------------------------------

    def test_repacked_opf_creators_equal_final_author_list(self):
        book, src = self._author_book(
            "Robert Newton Peck",
            [
                ("Brian McClellan", DataSource.OPF_FILE, 0.9),
                ("Robert Newton Peck", DataSource.EPUB_INTERNAL, 0.8),
                ("Robert Newton Peck", DataSource.GOOGLE_BOOKS, 0.665),
                ("A Day No Pigs Would Die", DataSource.INITIAL_SCAN, 0.2),
            ],
        )
        target = self.target_dir / "book.epub"
        safe_move_book(book, str(target))
        self.assertTrue(target.is_file())
        self.assertEqual([c[0] for c in _opf_creators(target)], ["Robert Newton Peck"])
