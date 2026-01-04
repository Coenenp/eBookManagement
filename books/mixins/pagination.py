"""
Pagination mixin for consistent pagination across views
"""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

from books.constants import PAGINATION


class StandardPaginationMixin:
    """Reusable pagination logic"""

    paginate_by = PAGINATION["default"]

    def get_paginated_context(self, queryset, page_number):
        """Get paginated context data"""
        paginator = Paginator(queryset, self.paginate_by)

        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return {
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": paginator.num_pages > 1,
        }
