from django.urls import path

from .views import (
    CompanySignupView,
    EmployeeDetailAPIView,
    EmployeeExportAPIView,
    EmployeeListAPIView,
    EmployeeReactivateAPIView,
    OrganizationSettingsAPIView,
)

urlpatterns = [
    path("register/", CompanySignupView.as_view(), name="company-signup"),
    path("employees/", EmployeeListAPIView.as_view(), name="employee-list"),
    path("employees/<int:pk>/", EmployeeDetailAPIView.as_view(), name="employee-detail"),
    path(
        "employees/<int:pk>/reactivate/",
        EmployeeReactivateAPIView.as_view(),
        name="employee-reactivate",
    ),
    path("employees/export/", EmployeeExportAPIView.as_view(), name="employee-export"),
    # Kept at the old path so existing clients keep working.
    path("company-config/", OrganizationSettingsAPIView.as_view(), name="organization-settings"),
]
