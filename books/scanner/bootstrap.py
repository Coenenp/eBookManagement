"""Data source bootstrapping utilities.

This module ensures that default data sources are created in the database
with appropriate confidence levels for metadata extraction.
"""


def ensure_data_sources():
    from books.models import DataSource

    # Hierarchical trust levels for predictable metadata resolution
    # 1.0 = Manual (Human verified)
    # 0.95 = Open Library (Highly curated database)
    # 0.9 = OPF Files (Official book metadata files)
    # 0.85 = Content Scan (Direct from book content, high reliability)
    # 0.8 = EPUB Internal (Well-structured format)
    # 0.75 = MOBI Internal (Good format, some limitations)
    # 0.7 = Google Books (Good but less curated than Open Library)
    # 0.65 = Open Library Covers (Cover images from Open Library)
    # 0.6 = PDF Internal (Limited metadata in PDFs)
    # 0.55 = Google Books Covers (Cover images from Google Books)
    # 0.5 = Original Scan (Fallback source)
    # 0.2 = Filename (Last resort, low reliability)

    sources = [
        (DataSource.MANUAL, 1.0),              # Highest - Human verification
        (DataSource.OPEN_LIBRARY, 0.95),      # Very High - Curated database
        (DataSource.COMICVINE, 0.9),          # Very High - Professional comic database
        (DataSource.OPF_FILE, 0.9),           # High - Official metadata files
        (DataSource.CONTENT_SCAN, 0.85),      # High - Direct from book content
        (DataSource.EPUB_INTERNAL, 0.8),      # Good - Well-structured format
        (DataSource.MOBI_INTERNAL, 0.75),     # Good - Some format limitations
        (DataSource.GOOGLE_BOOKS, 0.7),       # Good - Less curated than Open Library
        (DataSource.OPEN_LIBRARY_COVERS, 0.65),  # Moderate - Cover images
        (DataSource.PDF_INTERNAL, 0.6),       # Moderate - Limited PDF metadata
        (DataSource.GOOGLE_BOOKS_COVERS, 0.55),  # Moderate - Cover images
        (DataSource.ORIGINAL_SCAN, 0.5),      # Low - Fallback source
        (DataSource.FILENAME, 0.2),           # Very Low - Last resort
    ]

    for name, trust in sources:
        DataSource.objects.get_or_create(
            name=name,
            defaults={"trust_level": trust}
        )
