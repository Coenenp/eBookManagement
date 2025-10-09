"""Django admin configuration for ebook library management.

This module configures the Django admin interface for all book-related models
including books, authors, publishers, metadata, and scan operations. Provides
comprehensive admin views with filtering, search, and bulk operations.
"""
from django.contrib import admin
from .models import (
    Author, Book, BookAuthor, BookCover, BookFile, BookGenre, BookMetadata, BookSeries, BookTitle, BookPublisher,
    DataSource, FinalMetadata, Genre, Publisher, ScanFolder, ScanLog, ScanStatus, Series
)

# ----------------------
# Inline Admin Classes
# ----------------------


class BookTitleInline(admin.TabularInline):
    model = BookTitle
    extra = 0
    readonly_fields = ('created_at',)


class BookAuthorInline(admin.TabularInline):
    model = BookAuthor
    extra = 0
    readonly_fields = ('created_at',)


class BookSeriesInline(admin.TabularInline):
    model = BookSeries
    extra = 0
    readonly_fields = ('created_at',)


class BookGenreInline(admin.TabularInline):
    model = BookGenre
    extra = 0
    readonly_fields = ('created_at',)


class BookMetadataInline(admin.TabularInline):
    model = BookMetadata
    extra = 0
    readonly_fields = ('created_at',)


class BookCoverInline(admin.TabularInline):
    model = BookCover
    extra = 0
    readonly_fields = ('created_at', 'aspect_ratio', 'resolution_str')


class BookPublisherInline(admin.TabularInline):
    model = BookPublisher
    extra = 0
    readonly_fields = ('created_at',)


class BookFileInline(admin.TabularInline):
    model = BookFile
    extra = 0
    readonly_fields = ('file_path_hash', 'first_scanned', 'file_size_display')
    fields = ('file_path', 'file_format', 'file_size_display', 'opf_path', 'cover_path', 'file_path_hash')

    def file_size_display(self, obj):
        if obj.file_size:
            return f"{obj.file_size // (1024*1024)} MB" if obj.file_size > 1024*1024 else f"{obj.file_size // 1024} KB"
        return "Unknown"
    file_size_display.short_description = 'File Size'


class FinalMetadataInline(admin.StackedInline):
    model = FinalMetadata
    extra = 0
    readonly_fields = (
        'final_title',
        'final_title_confidence',
        'final_author',
        'final_author_confidence',
        'overall_confidence',
        'completeness_score',
        'last_updated',
    )
    fieldsets = (
        ('Final Choices', {
            'fields': ('final_title', 'final_title_confidence', 'final_author', 'final_author_confidence')
        }),
        ('Quality', {
            'fields': ('overall_confidence', 'completeness_score', 'last_updated'),
            'classes': ('collapse',)
        }),
    )

# ----------------------
# Admin Classes
# ----------------------


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_name_display', 'trust_level')
    list_filter = ('trust_level',)
    search_fields = ('name',)
    ordering = ('-trust_level', 'name')


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'name_normalized')
    search_fields = ('first_name', 'last_name', 'name_normalized')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('name', 'name_normalized')


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(ScanFolder)
class ScanFolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'path', 'content_type', 'language', 'created_at', 'is_active', 'last_scanned')
    list_filter = ('content_type', 'language', 'is_active', 'created_at')
    search_fields = ('name', 'path')
    readonly_fields = ('created_at', 'last_scanned')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'path', 'content_type', 'language')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_scanned'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'content_type', 'file_format', 'file_size_mb', 'is_placeholder', 'is_duplicate', 'is_corrupted', 'last_scanned')
    list_filter = ('content_type', 'is_placeholder', 'is_duplicate', 'is_corrupted', 'last_scanned', 'files__file_format')
    search_fields = ('titles__title', 'bookauthor__author__name', 'files__file_path')
    readonly_fields = ('first_scanned', 'last_scanned', 'file_format', 'file_size_mb', 'file_path_display')

    inlines = [
        BookFileInline,
        FinalMetadataInline,
        BookTitleInline,
        BookAuthorInline,
        BookCoverInline,
        BookSeriesInline,
        BookGenreInline,
        BookMetadataInline,
    ]

    def file_format(self, obj):
        """Get file format from first BookFile"""
        first_file = obj.files.first()
        return first_file.file_format if first_file else 'No files'
    file_format.short_description = 'Format'

    def file_size_mb(self, obj):
        """Get file size in MB from first BookFile"""
        first_file = obj.files.first()
        if first_file and first_file.file_size:
            if first_file.file_size >= 1024*1024:
                return f"{first_file.file_size / (1024*1024):.2f} MB"
            else:
                return f"{first_file.file_size / (1024*1024):.2f} MB"
        return "Unknown"
    file_size_mb.short_description = 'File Size'

    def file_path_display(self, obj):
        """Get file path from first BookFile for display"""
        first_file = obj.files.first()
        return first_file.file_path if first_file else 'No files'
    file_path_display.short_description = 'File Path'

    fieldsets = (
        ('Book Information', {
            'fields': ('content_type',)
        }),
        ('File Information', {
            'fields': ('file_format', 'file_size_mb', 'file_path_display'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_placeholder', 'is_duplicate', 'is_corrupted'),
        }),
        ('Scan Information', {
            'fields': ('scan_folder', 'first_scanned', 'last_scanned'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BookTitle)
class BookTitleAdmin(admin.ModelAdmin):
    list_display = ('title', 'book', 'source', 'confidence', 'created_at')
    list_filter = ('source', 'confidence', 'created_at')
    search_fields = ('title', 'book__id')
    readonly_fields = ('created_at',)


@admin.register(BookAuthor)
class BookAuthorAdmin(admin.ModelAdmin):
    list_display = (
        'author_full_name', 'author_first_name', 'author_last_name',
        'book', 'source', 'confidence', 'is_main_author', 'created_at'
    )
    list_filter = ('source', 'confidence', 'is_main_author', 'created_at')
    search_fields = ('author__name', 'author__first_name', 'author__last_name', 'book__files__file_path')
    readonly_fields = ('created_at',)

    def author_full_name(self, obj):
        return obj.author.name
    author_full_name.short_description = 'Author'

    def author_first_name(self, obj):
        return obj.author.first_name
    author_first_name.short_description = 'First Name'

    def author_last_name(self, obj):
        return obj.author.last_name
    author_last_name.short_description = 'Last Name'


@admin.register(BookCover)
class BookCoverAdmin(admin.ModelAdmin):
    list_display = ('book', 'source', 'confidence', 'resolution_str', 'is_high_resolution', 'format', 'created_at')
    list_filter = ('source', 'confidence', 'is_high_resolution', 'format', 'created_at')
    search_fields = ('book__files__file_path', 'cover_path')
    readonly_fields = ('created_at', 'aspect_ratio', 'is_high_resolution', 'resolution_str', 'is_local_file')

    fieldsets = (
        ('Basic Information', {
            'fields': ('book', 'cover_path', 'source', 'confidence')
        }),
        ('Image Properties', {
            'fields': ('width', 'height', 'aspect_ratio', 'file_size', 'format', 'is_high_resolution')
        }),
        ('System', {
            'fields': ('resolution_str', 'is_local_file', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def resolution_str(self, obj):
        return obj.resolution_str
    resolution_str.short_description = 'Resolution'


@admin.register(BookSeries)
class BookSeriesAdmin(admin.ModelAdmin):
    list_display = ('series', 'book', 'series_number', 'source', 'confidence', 'created_at')
    list_filter = ('source', 'confidence', 'created_at')
    search_fields = ('series__name', 'book__files__file_path')
    readonly_fields = ('created_at',)


@admin.register(BookGenre)
class BookGenreAdmin(admin.ModelAdmin):
    list_display = ('genre', 'book', 'source', 'confidence', 'created_at')
    list_filter = ('source', 'confidence', 'created_at')
    search_fields = ('genre__name', 'book__files__file_path')
    readonly_fields = ('created_at',)


@admin.register(BookPublisher)
class BookPublisherAdmin(admin.ModelAdmin):
    list_display = ('book', 'publisher', 'source', 'confidence', 'created_at')
    list_filter = ('source', 'confidence', 'created_at')
    search_fields = ('publisher__name', 'book__files__file_path')
    readonly_fields = ('created_at',)


@admin.register(BookMetadata)
class BookMetadataAdmin(admin.ModelAdmin):
    list_display = ('field_name', 'book', 'source', 'confidence', 'created_at')
    list_filter = ('field_name', 'source', 'confidence', 'created_at')
    search_fields = ('field_name', 'field_value', 'book__files__file_path')
    readonly_fields = ('created_at',)


@admin.register(FinalMetadata)
class FinalMetadataAdmin(admin.ModelAdmin):
    list_display = (
        'book',
        'final_title',
        'final_title_confidence',
        'final_author',
        'final_author_confidence',
        'final_series',
        'final_series_confidence',
        'final_cover_confidence',
        'overall_confidence',
        'completeness_score',
        'is_reviewed',
        'has_cover',
    )
    list_filter = ('is_reviewed', 'has_cover', 'overall_confidence', 'completeness_score', 'language', 'publication_year')
    search_fields = ('final_title', 'final_author', 'book__files__file_path')
    readonly_fields = ('overall_confidence', 'completeness_score', 'last_updated')

    fieldsets = (
        ('Core Metadata', {
            'fields': ('book', 'final_title', 'final_title_confidence', 'final_author', 'final_author_confidence', 'final_publisher', 'final_publisher_confidence')
        }),
        ('Series Information', {
            'fields': ('final_series', 'final_series_number', 'final_series_confidence')
        }),
        ('Cover Information', {
            'fields': ('final_cover_path', 'final_cover_confidence', 'has_cover')
        }),
        ('Publication Information', {
            'fields': ('language', 'isbn', 'publication_year', 'description')
        }),
        ('Quality Metrics', {
            'fields': ('overall_confidence', 'completeness_score', 'is_reviewed'),
            'classes': ('collapse',)
        }),
        ('System', {
            'fields': ('last_updated',),
            'classes': ('collapse',)
        }),
    )


@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'level', 'message_preview', 'file_path', 'scan_folder')
    list_filter = ('level', 'timestamp', 'scan_folder')
    search_fields = ('message', 'file_path')
    readonly_fields = ('timestamp',)

    def message_preview(self, obj):
        return obj.message[:100] + "..." if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message Preview'


@admin.register(ScanStatus)
class ScanStatusAdmin(admin.ModelAdmin):
    list_display = ('status', 'progress', 'message_preview', 'started', 'updated')
    list_filter = ('status', 'started', 'updated')
    search_fields = ('message',)
    readonly_fields = ('started', 'updated')

    def message_preview(self, obj):
        if obj.message:
            return obj.message[:100] + "..." if len(obj.message) > 100 else obj.message
        return "No message"
    message_preview.short_description = 'Message Preview'


@admin.register(BookFile)
class BookFileAdmin(admin.ModelAdmin):
    list_display = ('book', 'file_path_short', 'file_format', 'file_size_display', 'file_hash_short', 'first_scanned')
    list_filter = ('file_format', 'first_scanned')
    search_fields = ('file_path', 'book__titles__title', 'file_path_hash')
    readonly_fields = ('file_path_hash', 'first_scanned', 'file_size_display')

    fieldsets = (
        ('File Information', {
            'fields': ('book', 'file_path', 'file_format', 'file_size', 'file_size_display')
        }),
        ('Associated Files', {
            'fields': ('opf_path', 'cover_path'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('file_path_hash', 'first_scanned', 'last_scanned'),
            'classes': ('collapse',)
        }),
    )

    def file_path_short(self, obj):
        """Show shortened file path for list display"""
        if obj.file_path:
            return obj.file_path if len(obj.file_path) <= 50 else "..." + obj.file_path[-47:]
        return "No path"
    file_path_short.short_description = 'File Path'

    def file_size_display(self, obj):
        """Show file size in human readable format"""
        if obj.file_size:
            if obj.file_size > 1024*1024*1024:
                return f"{obj.file_size / (1024*1024*1024):.1f} GB"
            elif obj.file_size > 1024*1024:
                return f"{obj.file_size // (1024*1024)} MB"
            elif obj.file_size > 1024:
                return f"{obj.file_size // 1024} KB"
            else:
                return f"{obj.file_size} B"
        return "Unknown"
    file_size_display.short_description = 'File Size'

    def file_hash_short(self, obj):
        """Show shortened hash for list display"""
        return obj.file_path_hash[:8] + "..." if obj.file_path_hash else "No hash"
    file_hash_short.short_description = 'Hash'
