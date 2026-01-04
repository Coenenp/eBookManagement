"""
Filtering mixins for book queries
"""

from django.db.models import Q


class BookFilterMixin:
    """Reusable book filtering logic"""

    def apply_search_filters(self, queryset, search_params):
        """Apply common search filters to book queryset"""
        search_query = search_params.get("search_query")
        if search_query:
            queryset = queryset.filter(
                Q(finalmetadata__final_title__icontains=search_query)
                | Q(finalmetadata__final_author__icontains=search_query)
                | Q(finalmetadata__final_series__icontains=search_query)
            )

        language = search_params.get("language")
        if language:
            queryset = queryset.filter(finalmetadata__language=language)

        file_format = search_params.get("file_format")
        if file_format:
            queryset = queryset.filter(files__file_format=file_format)

        confidence_level = search_params.get("confidence_level")
        if confidence_level == "high":
            queryset = queryset.filter(finalmetadata__overall_confidence__gte=0.8)
        elif confidence_level == "medium":
            queryset = queryset.filter(
                finalmetadata__overall_confidence__gte=0.5,
                finalmetadata__overall_confidence__lt=0.8,
            )
        elif confidence_level == "low":
            queryset = queryset.filter(finalmetadata__overall_confidence__lt=0.5)

        is_reviewed = search_params.get("is_reviewed")
        if is_reviewed == "true":
            queryset = queryset.filter(finalmetadata__is_reviewed=True)
        elif is_reviewed == "false":
            queryset = queryset.filter(finalmetadata__is_reviewed=False)

        return queryset
