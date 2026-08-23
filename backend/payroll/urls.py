from django.urls import path

from .views import (
    EmployeeSalaryAPIView,
    ExpenseClaimListCreateAPIView,
    ExpenseClaimReviewAPIView,
    PayrollCreditAPIView,
    PayrollListAPIView,
    PayrollRunAPIView,
    PayrollSlipAPIView,
    PayrollSlipHTMLAPIView,
)

urlpatterns = [
    path("salaries/", EmployeeSalaryAPIView.as_view(), name="payroll-salaries"),
    path("expenses/", ExpenseClaimListCreateAPIView.as_view(), name="payroll-expenses"),
    path(
        "expenses/<int:claim_id>/review/",
        ExpenseClaimReviewAPIView.as_view(),
        name="payroll-expense-review",
    ),
    path("run/", PayrollRunAPIView.as_view(), name="payroll-run"),
    path("records/", PayrollListAPIView.as_view(), name="payroll-records"),
    path("records/<int:payroll_id>/credit/", PayrollCreditAPIView.as_view(), name="payroll-credit"),
    path("slips/<int:payroll_id>/", PayrollSlipAPIView.as_view(), name="payroll-slip"),
    path("slips/<int:payroll_id>/html/", PayrollSlipHTMLAPIView.as_view(), name="payroll-slip-html"),
]
