def ensure_data_sources():
    from books.models import DataSource

    sources = [
        (DataSource.FILENAME, 0.3),
        (DataSource.EPUB_INTERNAL, 0.8),
        (DataSource.MOBI_INTERNAL, 0.8),
        (DataSource.PDF_INTERNAL, 0.6),
        (DataSource.OPF_FILE, 0.9),
        (DataSource.OPEN_LIBRARY, 0.95),
        (DataSource.GOOGLE_BOOKS, 0.9),
        (DataSource.OPEN_LIBRARY_COVERS, 0.75),
        (DataSource.GOOGLE_BOOKS_COVERS, 0.7),
        (DataSource.ORIGINAL_SCAN, 0.5),
        (DataSource.MANUAL, 1.0),
    ]

    for name, trust in sources:
        DataSource.objects.get_or_create(
            name=name,
            defaults={"trust_level": trust}
        )
