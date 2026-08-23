"""Default pagination.

Every list endpoint used to return an unbounded result set (audit V-29): the
attendance and leave endpoints returned every row the tenant had ever recorded,
on every dashboard load, refetched by a WebSocket on any database change.
"""

from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 200
