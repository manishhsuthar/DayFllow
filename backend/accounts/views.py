import logging
from datetime import datetime

from django.db import transaction
from django.http import HttpResponse
from openpyxl import Workbook
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog
from audit.services import diff, record
from organizations.scoping import organization_of

from .models import CustomUser
from .permissions import IsManagement, IsOrganizationOwner, can_manage_target, is_owner
from .serializers import (
    CompanySignupSerializer,
    EmployeeListSerializer,
    OrganizationSettingsSerializer,
)

logger = logging.getLogger(__name__)


def get_employee_queryset_for_request(request):
    """Every employee visible to the caller, scoped to their organization.

    HR no longer sees ADMIN rows by default. The old implementation gated only the
    `scope=non_admin` parameter on ADMIN, so HR could omit it and receive the
    company owner's record -- and then delete it (audit V-17).
    """
    user = request.user
    organization = organization_of(user)

    queryset = CustomUser.objects.filter(organization=organization).select_related(
        "organization"
    )

    if not is_owner(user):
        queryset = queryset.exclude(role="ADMIN")

    scope = request.query_params.get("scope")
    if scope == "non_admin":
        queryset = queryset.exclude(role="ADMIN")
    elif scope == "employees_only":
        queryset = queryset.filter(role="EMP")

    role = request.query_params.get("role")
    if role:
        queryset = queryset.filter(role=role)

    # Deactivated employees are retained for payroll history but hidden by default.
    if request.query_params.get("include_inactive") != "true":
        queryset = queryset.filter(is_active=True)

    return queryset.order_by("date_of_joining", "id")


class CompanySignupView(generics.CreateAPIView):
    """Create a new organization and its owner account.

    Public, rate limited, and it can only ever *create* a tenant. The previous
    version accepted any company name and promoted the caller to ADMIN of the
    matching tenant, which was an unauthenticated takeover of any customer
    (audit V-01).
    """

    serializer_class = CompanySignupSerializer
    permission_classes = (AllowAny,)
    throttle_scope = "signup"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = serializer.save()

        logger.info(
            "Organization created: slug=%s owner=%s",
            owner.organization.slug,
            owner.login_id,
        )
        return Response(
            {
                "message": "Company created successfully.",
                "login_id": owner.login_id,
                "email": owner.email,
                "organization": {
                    "name": owner.organization.name,
                    "slug": owner.organization.slug,
                    "timezone": owner.organization.timezone,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class EmployeeListAPIView(generics.ListAPIView):
    serializer_class = EmployeeListSerializer
    permission_classes = (IsAuthenticated, IsManagement)

    def get_queryset(self):
        return get_employee_queryset_for_request(self.request)


class EmployeeDetailAPIView(generics.RetrieveDestroyAPIView):
    serializer_class = EmployeeListSerializer
    permission_classes = (IsAuthenticated, IsManagement)

    def get_queryset(self):
        # Detail lookups reach deactivated employees too; get_object() below does
        # the per-object authorization.
        return CustomUser.objects.filter(organization=organization_of(self.request.user))

    def get_object(self):
        organization = organization_of(self.request.user)
        obj = generics.get_object_or_404(
            CustomUser, pk=self.kwargs["pk"], organization=organization
        )
        if not can_manage_target(self.request.user, obj):
            raise PermissionDenied("You do not have permission to manage this employee.")
        return obj

    def perform_destroy(self, instance):
        """Deactivate. Never delete.

        This used to be a hard delete that first removed the employee's
        EmployeeSalary and every PayrollRecord -- including records already marked
        PAID -- specifically defeating the on_delete=PROTECT that was there to stop
        it (audit V-16). Payroll data carries statutory retention requirements; it
        does not get deleted because someone left.
        """
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("You cannot deactivate your own account.")

        organization = instance.organization
        if organization and organization.owner_id == instance.pk:
            raise PermissionDenied(
                "This account owns the organization. Transfer ownership before deactivating it."
            )

        with transaction.atomic():
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            record(
                organization=organization,
                actor=self.request.user,
                action=AuditLog.Action.EMPLOYEE_DEACTIVATED,
                target=instance,
                label=instance.login_id,
                changes={"is_active": {"from": True, "to": False}},
            )


class EmployeeReactivateAPIView(APIView):
    permission_classes = (IsAuthenticated, IsManagement)

    def post(self, request, pk):
        organization = organization_of(request.user)
        employee = generics.get_object_or_404(CustomUser, pk=pk, organization=organization)
        if not can_manage_target(request.user, employee):
            raise PermissionDenied("You do not have permission to manage this employee.")

        with transaction.atomic():
            employee.is_active = True
            employee.save(update_fields=["is_active", "updated_at"])
            record(
                organization=organization,
                actor=request.user,
                action=AuditLog.Action.EMPLOYEE_REACTIVATED,
                target=employee,
                label=employee.login_id,
                changes={"is_active": {"from": False, "to": True}},
            )
        return Response(EmployeeListSerializer(employee).data, status=status.HTTP_200_OK)


class EmployeeExportAPIView(APIView):
    permission_classes = (IsAuthenticated, IsManagement)
    throttle_scope = "export"

    def get(self, request):
        queryset = get_employee_queryset_for_request(request)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Employees"
        # Salary is intentionally not exported (audit V-18).
        worksheet.append(
            [
                "Employee ID",
                "First Name",
                "Last Name",
                "Email",
                "Role",
                "Department",
                "Employment Type",
                "Status",
                "Date Of Joining",
            ]
        )

        for user in queryset:
            worksheet.append(
                [
                    user.login_id or "",
                    user.first_name or "",
                    user.last_name or "",
                    user.email or "",
                    user.role or "",
                    user.department or "",
                    user.employment_type or "",
                    "Active" if user.is_active else "Inactive",
                    user.date_of_joining.isoformat() if user.date_of_joining else "",
                ]
            )

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        response["Content-Disposition"] = f'attachment; filename="employees_{timestamp}.xlsx"'
        workbook.save(response)
        return response


class OrganizationSettingsAPIView(generics.GenericAPIView):
    """Read and update the caller's own organization settings."""

    serializer_class = OrganizationSettingsSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), IsManagement()]
        return [IsAuthenticated(), IsOrganizationOwner()]

    def get_object(self):
        return organization_of(self.request.user)

    def get(self, request):
        return Response(self.get_serializer(self.get_object()).data)

    def put(self, request):
        organization = self.get_object()
        tracked = ("name", "timezone", "logo_url", "departments", "roles",
                   "employment_types", "bypass_attendance")
        before = {field: getattr(organization, field) for field in tracked}

        serializer = self.get_serializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            organization = serializer.save()
            after = {field: getattr(organization, field) for field in tracked}
            changed = diff(before, after)
            if changed:
                record(
                    organization=organization,
                    actor=request.user,
                    action=AuditLog.Action.SETTINGS_CHANGED,
                    target=organization,
                    label=organization.slug,
                    changes=changed,
                )
        return Response(serializer.data, status=status.HTTP_200_OK)
