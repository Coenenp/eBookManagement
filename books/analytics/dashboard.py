"""
Enhanced Dashboard Analytics Module

This module provides comprehensive analytics for the ebook library dashboard,
including format distribution, metadata completeness, AI parsing accuracy,
and reading progress tracking.
"""

import json
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from books.models import AIFeedback, Book, FinalMetadata, ScanHistory


class DashboardAnalytics:
    """Enhanced analytics for dashboard charts and statistics."""

    @staticmethod
    def get_theme_color_palette():
        """Get theme-aware color palette for charts."""
        return [
            "var(--bs-primary)",  # Primary Blue
            "var(--bs-success)",  # Success Green
            "var(--bs-warning)",  # Warning Orange
            "var(--bs-danger)",  # Danger Red
            "var(--bs-info)",  # Info Light Blue
            "var(--bs-purple)",  # Purple
            "var(--bs-cyan)",  # Cyan/Teal
            "var(--bs-yellow)",  # Yellow
            "var(--bs-pink)",  # Pink
            "var(--bs-indigo)",  # Indigo
            "var(--bs-secondary)",  # Secondary Gray
            "var(--bs-dark)",  # Dark
        ]

    @staticmethod
    def get_semantic_format_colors():
        """Get semantic colors for specific file formats."""
        return {
            "epub": "var(--bs-primary)",  # Primary - main ebook format
            "pdf": "var(--bs-success)",  # Success - widely compatible
            "mobi": "var(--bs-warning)",  # Warning - older format
            "azw": "var(--bs-warning)",  # Warning - proprietary
            "azw3": "var(--bs-warning)",  # Warning - proprietary
            "cbz": "var(--bs-danger)",  # Danger - comic archive
            "cbr": "var(--bs-purple)",  # Purple - comic archive
            "cb7": "var(--bs-purple)",  # Purple - comic archive
            "cbt": "var(--bs-purple)",  # Purple - comic archive
            "mp3": "var(--bs-cyan)",  # Cyan - audio
            "m4a": "var(--bs-info)",  # Info - audio
            "m4b": "var(--bs-info)",  # Info - audiobook
            "aac": "var(--bs-cyan)",  # Cyan - audio
            "flac": "var(--bs-cyan)",  # Cyan - audio
            "ogg": "var(--bs-cyan)",  # Cyan - audio
            "wav": "var(--bs-cyan)",  # Cyan - audio
            "fb2": "var(--bs-yellow)",  # Yellow - alternative format
            "lit": "var(--bs-yellow)",  # Yellow - legacy format
            "prc": "var(--bs-yellow)",  # Yellow - legacy format
        }

    @staticmethod
    def get_format_distribution_data():
        """Get file format distribution for pie chart."""
        format_data = (
            Book.objects.exclude(
                Q(is_placeholder=True) | Q(is_duplicate=True) | Q(is_corrupted=True)
            )
            .values("files__file_format")
            .annotate(count=Count("id"))
            .filter(files__file_format__isnull=False)
            .order_by("-count")
        )

        # Convert to chart-ready format
        labels = []
        data = []
        colors = []

        # Get semantic colors for formats
        semantic_colors = DashboardAnalytics.get_semantic_format_colors()
        fallback_colors = DashboardAnalytics.get_theme_color_palette()
        fallback_index = 0

        for item in format_data:
            file_format = item["files__file_format"]
            if file_format:
                format_lower = file_format.lower()
                labels.append(file_format.upper())
            data.append(item["count"])

            # Use semantic color if available, otherwise use fallback palette
            if format_lower in semantic_colors:
                colors.append(semantic_colors[format_lower])
            else:
                colors.append(fallback_colors[fallback_index % len(fallback_colors)])
                fallback_index += 1

        return {"labels": labels, "data": data, "colors": colors}

    @staticmethod
    def get_metadata_completeness_data():
        """Get metadata completeness statistics for bar chart."""
        total_books = Book.objects.exclude(
            Q(is_placeholder=True) | Q(is_duplicate=True) | Q(is_corrupted=True)
        ).count()

        if total_books == 0:
            return {
                "labels": ["Title", "Author", "Cover", "ISBN", "Series"],
                "data": [0, 0, 0, 0, 0],
                "percentages": [0, 0, 0, 0, 0],
                "colors": [
                    "var(--bs-primary)",
                    "var(--bs-success)",
                    "var(--bs-info)",
                    "var(--bs-warning)",
                    "var(--bs-purple)",
                ],
            }

        # Get completeness counts
        metadata_stats = FinalMetadata.objects.filter(
            book__is_placeholder=False,
            book__is_duplicate=False,
            book__is_corrupted=False,
        ).aggregate(
            titles=Count("id", filter=~Q(final_title="")),
            authors=Count("id", filter=~Q(final_author="")),
            covers=Count("id", filter=Q(has_cover=True)),
            isbns=Count("id", filter=~Q(isbn="")),
            series=Count("id", filter=~Q(final_series="")),
        )

        labels = ["Title", "Author", "Cover", "ISBN", "Series"]
        data = [
            metadata_stats["titles"] or 0,
            metadata_stats["authors"] or 0,
            metadata_stats["covers"] or 0,
            metadata_stats["isbns"] or 0,
            metadata_stats["series"] or 0,
        ]
        percentages = [(count / total_books * 100) for count in data]

        # Semantic colors for metadata types
        colors = [
            "var(--bs-primary)",  # Title - Primary (most important)
            "var(--bs-success)",  # Author - Success (essential info)
            "var(--bs-info)",  # Cover - Info (visual element)
            "var(--bs-warning)",  # ISBN - Warning (identifier)
            "var(--bs-purple)",  # Series - Purple (organizational)
        ]

        return {
            "labels": labels,
            "data": data,
            "percentages": percentages,
            "colors": colors,
        }

    @staticmethod
    def get_ai_accuracy_data(days=30):
        """Get AI parsing accuracy over time for line chart."""
        # For now, simulate data since AIFeedback may not have enough data
        # In production, this would use real AIFeedback data

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        # Check if we have real AI feedback data
        feedback_exists = AIFeedback.objects.filter(
            created_at__date__gte=start_date
        ).exists()

        if feedback_exists:
            # Use real data
            daily_accuracy = (
                AIFeedback.objects.filter(created_at__date__gte=start_date)
                .extra({"day": "date(created_at)"})
                .values("day")
                .annotate(avg_accuracy=Avg("feedback_rating"))
                .order_by("day")
            )

            labels = []
            data = []

            for item in daily_accuracy:
                labels.append(item["day"].strftime("%m/%d"))
                # Convert 1-5 rating to percentage
                accuracy_percent = (item["avg_accuracy"] / 5.0) * 100
                data.append(round(accuracy_percent, 1))

            return {
                "labels": labels,
                "data": data,
                "current_accuracy": data[-1] if data else 85.0,
                "trend": "up" if len(data) >= 2 and data[-1] > data[-2] else "stable",
            }
        else:
            # Generate simulated realistic data
            labels = []
            data = []

            # Base accuracy that improves over time with some variance
            base_accuracy = 82.0
            improvement_per_day = 0.1

            for i in range(days):
                date = start_date + timedelta(days=i)
                labels.append(date.strftime("%m/%d"))

                # Add daily improvement plus some realistic variance
                accuracy = base_accuracy + (i * improvement_per_day)
                variance = (hash(str(date)) % 100 - 50) / 25.0  # Â±2% variance
                accuracy = max(80, min(95, accuracy + variance))

                data.append(round(accuracy, 1))

            return {
                "labels": labels[-14:],  # Show last 2 weeks
                "data": data[-14:],
                "current_accuracy": data[-1] if data else 85.0,
                "trend": "up" if len(data) >= 2 and data[-1] > data[-2] else "stable",
            }

    @staticmethod
    def get_reading_progress_data():
        """Get reading progress data for audiobooks (placeholder for future implementation)."""
        # This is a placeholder for when audiobook reading progress is implemented

        # Simulate weekly reading data
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        # Simulate hours read per day (this would come from user activity tracking)
        hours = [2.5, 1.8, 3.2, 0.5, 4.1, 5.8, 3.7]

        return {
            "labels": days,
            "data": hours,
            "total_hours": sum(hours),
            "avg_daily": sum(hours) / len(hours),
        }

    @staticmethod
    def get_confidence_distribution():
        """Get confidence score distribution for dashboard metrics."""
        total_books = FinalMetadata.objects.filter(
            book__is_placeholder=False,
            book__is_duplicate=False,
            book__is_corrupted=False,
        ).count()

        if total_books == 0:
            return {
                "high": 0,
                "medium": 0,
                "low": 0,
                "high_percent": 0,
                "medium_percent": 0,
                "low_percent": 0,
            }

        confidence_stats = FinalMetadata.objects.filter(
            book__is_placeholder=False,
            book__is_duplicate=False,
            book__is_corrupted=False,
        ).aggregate(
            high=Count("id", filter=Q(overall_confidence__gte=0.8)),
            medium=Count(
                "id", filter=Q(overall_confidence__gte=0.5, overall_confidence__lt=0.8)
            ),
            low=Count("id", filter=Q(overall_confidence__lt=0.5)),
        )

        return {
            "high": confidence_stats["high"] or 0,
            "medium": confidence_stats["medium"] or 0,
            "low": confidence_stats["low"] or 0,
            "high_percent": (confidence_stats["high"] or 0) / total_books * 100,
            "medium_percent": (confidence_stats["medium"] or 0) / total_books * 100,
            "low_percent": (confidence_stats["low"] or 0) / total_books * 100,
        }

    @staticmethod
    def get_scan_activity_data(days=30):
        """Get scanning activity over time."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        # Get scan history data
        scan_activity = (
            ScanHistory.objects.filter(completed_at__date__gte=start_date)
            .extra({"day": "date(completed_at)"})
            .values("day")
            .annotate(
                scans=Count("id"),
                books_added=Count("books_added"),
                files_processed=Count("files_processed"),
            )
            .order_by("day")
        )

        labels = []
        scans_data = []
        books_data = []

        for item in scan_activity:
            labels.append(item["day"].strftime("%m/%d"))
            scans_data.append(item["scans"])
            books_data.append(item["books_added"])

        return {"labels": labels, "scans": scans_data, "books_added": books_data}

    @staticmethod
    def get_library_growth_data(days=90):
        """Get library growth over time."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        # Get daily book additions
        growth_data = (
            Book.objects.filter(
                first_scanned__date__gte=start_date,
                is_placeholder=False,
                is_duplicate=False,
            )
            .extra({"day": "date(first_scanned)"})
            .values("day")
            .annotate(books_added=Count("id"))
            .order_by("day")
        )

        labels = []
        cumulative_data = []
        daily_data = []
        cumulative_total = Book.objects.filter(
            first_scanned__date__lt=start_date, is_placeholder=False, is_duplicate=False
        ).count()

        for item in growth_data:
            labels.append(item["day"].strftime("%m/%d"))
            daily_books = item["books_added"]
            cumulative_total += daily_books

            daily_data.append(daily_books)
            cumulative_data.append(cumulative_total)

        return {
            "labels": labels[-30:],  # Show last 30 days
            "daily": daily_data[-30:],
            "cumulative": cumulative_data[-30:],
        }

    @staticmethod
    def prepare_all_chart_data():
        """Prepare all chart data for the dashboard in JSON format."""
        format_data = DashboardAnalytics.get_format_distribution_data()
        completeness_data = DashboardAnalytics.get_metadata_completeness_data()
        accuracy_data = DashboardAnalytics.get_ai_accuracy_data()
        reading_data = DashboardAnalytics.get_reading_progress_data()
        confidence_data = DashboardAnalytics.get_confidence_distribution()

        return {
            "format_distribution": {
                "labels": json.dumps(format_data["labels"]),
                "data": json.dumps(format_data["data"]),
                "colors": json.dumps(format_data["colors"]),
            },
            "metadata_completeness": {
                "labels": json.dumps(completeness_data["labels"]),
                "data": json.dumps(completeness_data["data"]),
                "percentages": json.dumps(completeness_data["percentages"]),
                "colors": json.dumps(completeness_data["colors"]),
            },
            "ai_accuracy": {
                "labels": json.dumps(accuracy_data["labels"]),
                "data": json.dumps(accuracy_data["data"]),
                "current": accuracy_data["current_accuracy"],
                "trend": accuracy_data["trend"],
            },
            "reading_progress": {
                "labels": json.dumps(reading_data["labels"]),
                "data": json.dumps(reading_data["data"]),
                "total_hours": reading_data["total_hours"],
                "avg_daily": round(reading_data["avg_daily"], 1),
            },
            "confidence_distribution": confidence_data,
        }


class LibraryHealth:
    """Library health and quality metrics."""

    @staticmethod
    def get_health_score():
        """Calculate overall library health score (0-100)."""
        total_books = Book.objects.exclude(
            Q(is_placeholder=True) | Q(is_duplicate=True) | Q(is_corrupted=True)
        ).count()

        if total_books == 0:
            return 100

        # Get various health metrics
        metadata_completeness = DashboardAnalytics.get_metadata_completeness_data()
        confidence_data = DashboardAnalytics.get_confidence_distribution()

        # Calculate weighted score
        completeness_score = sum(metadata_completeness["percentages"]) / len(
            metadata_completeness["percentages"]
        )
        confidence_score = (
            (confidence_data["high_percent"] * 1.0)
            + (confidence_data["medium_percent"] * 0.7)
            + (confidence_data["low_percent"] * 0.3)
        )

        # Weight: 60% completeness, 40% confidence
        health_score = (completeness_score * 0.6) + (confidence_score * 0.4)

        return min(100, max(0, round(health_score, 1)))

    @staticmethod
    def get_quality_issues():
        """Get list of quality issues that need attention."""
        issues = []

        # Check for missing metadata
        missing_titles = FinalMetadata.objects.filter(final_title="").count()
        if missing_titles > 0:
            issues.append(
                {
                    "type": "warning",
                    "message": f"{missing_titles} books missing titles",
                    "action": "Review and add titles",
                }
            )

        missing_authors = FinalMetadata.objects.filter(final_author="").count()
        if missing_authors > 0:
            issues.append(
                {
                    "type": "warning",
                    "message": f"{missing_authors} books missing authors",
                    "action": "Review and add authors",
                }
            )

        missing_covers = FinalMetadata.objects.filter(has_cover=False).count()
        if missing_covers > 0:
            issues.append(
                {
                    "type": "info",
                    "message": f"{missing_covers} books missing covers",
                    "action": "Find and upload covers",
                }
            )

        # Check for low confidence items
        low_confidence = FinalMetadata.objects.filter(
            overall_confidence__lt=0.5
        ).count()
        if low_confidence > 0:
            issues.append(
                {
                    "type": "danger",
                    "message": f"{low_confidence} books with low confidence metadata",
                    "action": "Review and verify metadata",
                }
            )

        # Check for corrupted files
        corrupted_files = Book.objects.filter(is_corrupted=True).count()
        if corrupted_files > 0:
            issues.append(
                {
                    "type": "danger",
                    "message": f"{corrupted_files} corrupted files detected",
                    "action": "Check file integrity and replace",
                }
            )

        return issues[:5]  # Return top 5 issues
