from django.urls import path

from .api import AuditLogListAPIView

urlpatterns = [
    path("", AuditLogListAPIView.as_view(), name="audit-log"),
]
