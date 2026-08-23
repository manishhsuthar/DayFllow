import logging

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from openpyxl import Workbook
from datetime import datetime
import base64
import hashlib
import hmac
import json
from urllib import error, request as urllib_request
from .serializers import (
    UserRegistrationSerializer,
    EmployeeListSerializer,
    CompanyConfigSerializer,
)
from .models import CustomUser, CompanyConfig, CompanyLogo
from .company_table_service import (
    ensure_company_table,
    insert_company_user_row,
    delete_company_user_row,
)

logger = logging.getLogger(__name__)


def get_employee_queryset_for_request(request):
    user = request.user
    if user.role not in ["ADMIN", "HR"]:
        raise PermissionDenied("Permission denied")

    queryset = CustomUser.objects.filter(company_name=user.company_name)
    scope = request.query_params.get("scope")

    if scope == "non_admin":
        if user.role != "ADMIN":
            raise PermissionDenied("Permission denied")
        queryset = queryset.exclude(role="ADMIN")
    elif scope == "employees_only":
        queryset = queryset.filter(role="EMP")

    role = request.query_params.get("role")
    if role:
        queryset = queryset.filter(role=role)

    return queryset.order_by("date_of_joining", "id")

class UserRegistrationView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = (AllowAny,)
    throttle_scope = "signup"

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                user = serializer.save()

                # Company signup account is the company admin.
                user.role = "ADMIN"
                user.is_staff = True
                user.is_approved = True
                user.save()

                company_table_name = ensure_company_table(user.company_name)
                insert_company_user_row(
                    company_name=user.company_name,
                    user=user,
                    created_by_user_id=None,
                )
        except Exception:
            # Let core.exceptions.exception_handler log this with a correlation id
            # and return an opaque error. Returning the traceback disclosed absolute
            # paths, the dependency tree and SQL fragments to anonymous callers.
            logger.exception("Company registration failed")
            raise
        return Response(
            {
                "user": UserRegistrationSerializer(
                    user, context=self.get_serializer_context()
                ).data,
                "company_table": company_table_name,
                "message": "Company admin account created successfully.",
            },
            status=status.HTTP_201_CREATED,
        )


class EmployeeListAPIView(generics.ListAPIView):
    serializer_class = EmployeeListSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return get_employee_queryset_for_request(self.request)


class EmployeeDetailAPIView(generics.RetrieveDestroyAPIView):
    serializer_class = EmployeeListSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return get_employee_queryset_for_request(self.request)

    def perform_destroy(self, instance):
        from payroll.models import PayrollRecord, EmployeeSalary
        # Delete related records
        PayrollRecord.objects.filter(employee=instance).delete()
        EmployeeSalary.objects.filter(employee=instance).delete()

        # Clean up company table row
        delete_company_user_row(instance.company_name, instance.id)

        # Delete CustomUser
        instance.delete()


class EmployeeExportAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "export"

    def get(self, request):
        queryset = get_employee_queryset_for_request(request)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Employees"

        headers = [
            "Employee ID",
            "First Name",
            "Last Name",
            "Email",
            "Role",
            "Department",
            "Employment Type",
            "Salary",
            "Status",
            "Date Of Joining",
        ]
        worksheet.append(headers)

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
                    float(user.salary) if user.salary is not None else "",
                    "Active" if user.is_active else "Inactive",
                    user.date_of_joining.isoformat() if user.date_of_joining else "",
                ]
            )

        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        response["Content-Disposition"] = (
            f'attachment; filename="employees_{timestamp}.xlsx"'
        )
        workbook.save(response)
        return response


class CompanyConfigAPIView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = CompanyConfigSerializer

    def get_object(self):
        company_name = getattr(self.request.user, "company_name", "")
        if not company_name:
            raise PermissionDenied("Company is not set for this user.")

        return CompanyConfig.objects.filter(company_name=company_name).first()

    def get(self, request):
        if request.user.role not in ["ADMIN", "HR"]:
            raise PermissionDenied("Permission denied")

        instance = self.get_object()
        logo = CompanyLogo.objects.filter(company_name=request.user.company_name).first()
        logo_url = logo.logo_url if logo else ""
        if not instance:
            return Response(
                {
                    "company_name": request.user.company_name,
                    "departments": [],
                    "roles": [],
                    "employment_types": [],
                    "bypass_attendance": False,
                    "logo_url": logo_url,
                    "updated_at": None,
                },
                status=status.HTTP_200_OK,
            )

        serializer = self.get_serializer(instance)
        response_data = serializer.data
        response_data["logo_url"] = logo_url
        return Response(response_data, status=status.HTTP_200_OK)

    def put(self, request):
        if request.user.role != "ADMIN":
            raise PermissionDenied("Only admin can update company configuration.")

        logo_url = (request.data.get("logo_url") or "").strip()
        existing_logo = CompanyLogo.objects.filter(company_name=request.user.company_name).first()

        instance = self.get_object()

        payload = request.data.copy()
        payload.pop("logo_url", None)
        if instance:
            serializer = self.get_serializer(instance, data=payload, partial=True)
        else:
            serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)

        if instance:
            config = serializer.save(updated_by=request.user)
        else:
            config = serializer.save(
                company_name=request.user.company_name,
                created_by=request.user,
                updated_by=request.user,
            )

        if logo_url:
            defaults = {
                "logo_url": logo_url,
                "updated_by": request.user,
            }
            if not existing_logo:
                defaults["created_by"] = request.user
            CompanyLogo.objects.update_or_create(
                company_name=request.user.company_name,
                defaults=defaults,
            )
        elif existing_logo:
            existing_logo.delete()

        refreshed_logo = CompanyLogo.objects.filter(company_name=request.user.company_name).first()
        response_data = self.get_serializer(config).data
        response_data["logo_url"] = refreshed_logo.logo_url if refreshed_logo else ""
        return Response(response_data, status=status.HTTP_200_OK)


PLAN_AMOUNTS = {
    "starter": 49900,
    "enterprise": 149900,
}


class RazorpayCreateOrderAPIView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "billing"

    def post(self, request):
        plan = request.data.get("plan")
        amount = PLAN_AMOUNTS.get(plan)
        if not amount:
            return Response(
                {"detail": "Plan must be either starter or enterprise."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"dayflow_{plan}_{int(datetime.now().timestamp())}",
            "payment_capture": 1,
        }
        credentials = f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()
        encoded_credentials = base64.b64encode(credentials).decode()
        razorpay_request = urllib_request.Request(
            "https://api.razorpay.com/v1/orders",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib_request.urlopen(razorpay_request, timeout=15) as response:
                order = json.loads(response.read().decode())
        except error.HTTPError as exc:
            detail = exc.read().decode() or "Unable to create payment order."
            return Response({"detail": detail}, status=status.HTTP_502_BAD_GATEWAY)
        except error.URLError:
            return Response(
                {"detail": "Payment service is unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "key_id": settings.RAZORPAY_KEY_ID,
                "plan": plan,
                "amount": amount,
                "currency": "INR",
                "order_id": order.get("id"),
            },
            status=status.HTTP_200_OK,
        )


class RazorpayVerifyPaymentAPIView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "billing"

    def post(self, request):
        order_id = request.data.get("razorpay_order_id", "")
        payment_id = request.data.get("razorpay_payment_id", "")
        signature = request.data.get("razorpay_signature", "")

        if not order_id or not payment_id or not signature:
            return Response(
                {"detail": "Payment verification details are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = f"{order_id}|{payment_id}".encode()
        expected_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            return Response(
                {"detail": "Invalid payment signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"message": "Payment verified successfully."},
            status=status.HTTP_200_OK,
        )
