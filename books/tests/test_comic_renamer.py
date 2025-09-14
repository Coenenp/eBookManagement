"""Tests for comic book renamer functionality."""
from django.test import TestCase
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
from books.models import Book, DataSource, BookMetadata, FinalMetadata
from books.views import BookRenamerView


class ComicRenamerTests(TestCase):
    """Test cases for comic book renaming functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.content_source = DataSource.objects.create(
            name=DataSource.CONTENT_SCAN,
            trust_level=0.85
        )

    def create_comic_book(self, filename, series_name, issue_type='main_series', issue_number=None, publisher=None):
        """Helper to create a comic book with metadata"""
        book = Book.objects.create(
            file_path=f"/test/{filename}",
            file_size=1000000,
            file_format="cbz"
        )

        # Add final metadata
        final_metadata = FinalMetadata.objects.create(
            book=book,
            final_title=filename.replace('.cbz', ''),
            final_series=series_name,
            final_series_number=str(issue_number) if issue_number else None,
            final_publisher=publisher
        )

        # Force update the title after auto-update
        final_metadata.final_title = filename.replace('.cbz', '')
        final_metadata.save(update_fields=['final_title'])

        # Add detailed metadata
        metadata_entries = [
            ('series', series_name),
            ('issue_type', issue_type),
            ('title', filename.replace('.cbz', '')),  # Add title as metadata
        ]

        if issue_number:
            metadata_entries.append(('issue_number', str(issue_number)))

        if publisher:
            metadata_entries.append(('publisher', publisher))

        for field_name, field_value in metadata_entries:
            BookMetadata.objects.create(
                book=book,
                field_name=field_name,
                field_value=field_value,
                source=self.content_source,
                confidence=0.9
            )

        return book

    def test_generate_comic_file_path_main_series(self):
        """Test comic file path generation for main series"""
        view = BookRenamerView()

        book = self.create_comic_book(
            "spider-man-001.cbz",
            "Spider-Man",
            "main_series",
            1,
            "Marvel Comics"
        )

        result = view._generate_comic_file_path(book)
        expected = "Comics/Marvel Comics/Spider-Man/Unknown/Spider-Man #001 - spider-man-001.cbz"
        self.assertEqual(result, expected)

    def test_generate_comic_file_path_annual(self):
        """Test comic file path generation for annuals"""
        view = BookRenamerView()

        book = self.create_comic_book(
            "spider-man-annual-1.cbz",
            "Spider-Man",
            "annual",
            publisher="Marvel Comics"
        )

        # Add annual number metadata
        BookMetadata.objects.create(
            book=book,
            field_name='annual_number',
            field_value='1',
            source=self.content_source,
            confidence=0.9
        )

        result = view._generate_comic_file_path(book)
        expected = "Comics/Marvel Comics/Spider-Man/Annuals/Spider-Man Annual #1 - spider-man-annual-1.cbz"
        self.assertEqual(result, expected)

    def test_generate_comic_file_path_special(self):
        """Test comic file path generation for specials"""
        view = BookRenamerView()

        book = self.create_comic_book(
            "spider-man-special.cbz",
            "Spider-Man",
            "special",
            publisher="Marvel Comics"
        )

        result = view._generate_comic_file_path(book)
        expected = "Comics/Marvel Comics/Spider-Man/Specials/Spider-Man Special - spider-man-special.cbz"
        self.assertEqual(result, expected)

    def test_generate_comic_file_path_collection(self):
        """Test comic file path generation for collections"""
        view = BookRenamerView()

        book = self.create_comic_book(
            "spider-man-tpb-vol-1.cbz",
            "Spider-Man",
            "collection",
            publisher="Marvel Comics"
        )

        result = view._generate_comic_file_path(book)
        expected = "Comics/Marvel Comics/Spider-Man/Collections/Spider-Man - spider-man-tpb-vol-1.cbz"
        self.assertEqual(result, expected)

    def test_get_comic_subfolder(self):
        """Test comic subfolder determination"""
        view = BookRenamerView()

        test_cases = [
            ('main_series', {}, 'Unknown'),
            ('annual', {}, 'Annuals'),
            ('special', {}, 'Specials'),
            ('collection', {}, 'Collections'),
            ('one_shot', {}, 'One-Shots'),
            ('preview', {}, 'Previews'),
            ('alternate_reality', {}, 'Alternate Reality'),
            ('crossover', {}, 'Events'),
        ]

        for issue_type, metadata, expected_subfolder in test_cases:
            with self.subTest(issue_type=issue_type):
                result = view._get_comic_subfolder(issue_type, metadata)
                self.assertEqual(result, expected_subfolder)

    def test_generate_comic_filename(self):
        """Test comic filename generation"""
        view = BookRenamerView()

        # Create a mock book
        book = MagicMock()
        book.finalmetadata.final_title = "Amazing Spider-Man #1"

        test_cases = [
            {
                'issue_type': 'main_series',
                'metadata': {'issue_number': 1},
                'series': 'Spider-Man',
                'expected': 'Spider-Man #001 - Amazing Spider-Man #1'
            },
            {
                'issue_type': 'annual',
                'metadata': {'annual_number': 1},
                'series': 'Spider-Man',
                'expected': 'Spider-Man Annual #1 - Amazing Spider-Man #1'
            },
            {
                'issue_type': 'special',
                'metadata': {},
                'series': 'Spider-Man',
                'expected': 'Spider-Man Special - Amazing Spider-Man #1'
            },
            {
                'issue_type': 'one_shot',
                'metadata': {},
                'series': 'Spider-Man',
                'expected': 'Spider-Man One-Shot - Amazing Spider-Man #1'
            },
        ]

        for case in test_cases:
            with self.subTest(issue_type=case['issue_type']):
                result = view._generate_comic_filename(
                    case['issue_type'],
                    case['metadata'],
                    case['series'],
                    book
                )
                self.assertEqual(result, case['expected'])

    def test_comic_series_analysis_integration(self):
        """Test comic series analysis integration"""
        # Create a series of comic books
        books = []
        for i in range(1, 4):  # Issues 1, 2, 3
            book = self.create_comic_book(
                f"spider-man-{i:03d}.cbz",
                "Spider-Man",
                "main_series",
                i,
                "Marvel Comics"
            )
            books.append(book)

        # Add an annual
        annual = self.create_comic_book(
            "spider-man-annual-1.cbz",
            "Spider-Man",
            "annual",
            publisher="Marvel Comics"
        )

        BookMetadata.objects.create(
            book=annual,
            field_name='annual_number',
            field_value='1',
            source=self.content_source,
            confidence=0.9
        )

        view = BookRenamerView()

        # Test series analysis
        analysis = view._analyze_comic_series_completion()

        self.assertIsNotNone(analysis)
        self.assertEqual(analysis['total_series'], 1)

        # Find the Spider-Man series in the analysis
        spider_man_series = None
        for series in analysis['all_series']:
            if series['name'] == 'Spider-Man':
                spider_man_series = series
                break

        self.assertIsNotNone(spider_man_series)
        self.assertEqual(spider_man_series['main_series_count'], 3)
        self.assertEqual(spider_man_series['annuals_count'], 1)
        self.assertTrue(spider_man_series['is_complete'])  # Issues 1-3 should be complete

    @patch('books.views.BookRenamerView._analyze_comic_series_completion')
    def test_comic_filter_by_issue_type(self, mock_analysis):
        """Test filtering comics by issue type"""
        # Setup mock analysis
        mock_analysis.return_value = {
            'all_series': [],
            'complete_series': [],
            'incomplete_series': [],
            'total_series': 0,
            'complete_count': 0,
            'incomplete_count': 0
        }

        # Create comics of different types
        main_issue = self.create_comic_book(
            "spider-man-001.cbz",
            "Spider-Man",
            "main_series",
            1
        )

        annual = self.create_comic_book(
            "spider-man-annual-1.cbz",
            "Spider-Man",
            "annual"
        )

        special = self.create_comic_book(
            "spider-man-special.cbz",
            "Spider-Man",
            "special"
        )

        # Test view with issue_type filter
        view = BookRenamerView()
        view.request = MagicMock()

        # Filter for main series only
        view.request.GET.get.side_effect = lambda key, default='': {
            'issue_type': 'main_series'
        }.get(key, default)

        queryset = view.get_queryset()

        # Should only contain the main series issue
        self.assertIn(main_issue, queryset)
        self.assertNotIn(annual, queryset)
        self.assertNotIn(special, queryset)
