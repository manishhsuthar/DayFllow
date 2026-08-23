"""Attendance.

Two defects shaped this rewrite:

* Check-out subtracted a possibly-`None` `check_in`, raising an unhandled
  TypeError (audit V-04). Approved leave creates rows with no check-in, so any
  employee could trigger a 500.
* The whole app mixed `timezone.now()` (aware, UTC) with `date.today()` (the
  *server's* local date). With `TIME_ZONE = "UTC"` those disagree for part of
  every day on a non-UTC host, and neither reflects the employee's own working
  day (audit V-26). The day boundary now comes from the organization's timezone.
"""

from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsManagement
from core.pagination import DefaultPagination
from leave.models import LeaveRequest
from organizations.scoping import organization_of

from .models import Attendance
from .serializers import AttendanceListSerializer, AttendanceSerializer
from .utils import calculate_status

#: The furthest back a history query may reach in one request.
MAX_HISTORY_DAYS = 366


def workday_for(user):
    """Today's date in the user's organization timezone."""
    organization = getattr(user, "organization", None)
    if organization is not None:
        return organization.today()
    return timezone.localdate()


def _parse_date(raw, field):
    from rest_framework.exceptions import ValidationError

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError({field: "Expected a date in YYYY-MM-DD format."})


def apply_date_filters(queryset, request, default_days=90):
    """Bound a history query.

    These endpoints previously returned every attendance row the tenant had ever
    recorded, unpaginated, on every dashboard load -- and a WebSocket refetched
    them on any database change (audit V-28, V-29).
    """
    from rest_framework.exceptions import ValidationError

    today = workday_for(request.user)
    start_raw = request.query_params.get("start_date")
    end_raw = request.query_params.get("end_date")

    end = _parse_date(end_raw, "end_date") if end_raw else today
    start = _parse_date(start_raw, "start_date") if start_raw else end - timedelta(days=default_days)

    if start > end:
        raise ValidationError({"start_date": "start_date must not be after end_date."})
    if (end - start).days > MAX_HISTORY_DAYS:
        raise ValidationError(
            {"start_date": f"Range must not exceed {MAX_HISTORY_DAYS} days."}
        )

    return queryset.filter(date__gte=start, date__lte=end)


class CheckInAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        today = workday_for(request.user)

        on_leave = LeaveRequest.objects.filter(
            user=request.user,
            status="APPROVED",
            start_date__lte=today,
            end_date__gte=today,
        ).exists()
        if on_leave:
            return Response(
                {"detail": "You are on approved leave today."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            attendance, _ = Attendance.objects.select_for_update().get_or_create(
                user=request.user, date=today, defaults={"status": "PRESENT"}
            )
            if attendance.check_in:
                return Response(
                    {"detail": "Already checked in today."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            attendance.check_in = timezone.now()
            attendance.status = "PRESENT"
            attendance.save(update_fields=["check_in", "status"])

        return Response(
            {"detail": "Check-in successful", "check_in": attendance.check_in},
            status=status.HTTP_200_OK,
        )


class CheckOutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        today = workday_for(request.user)

        with transaction.atomic():
            attendance = (
                Attendance.objects.select_for_update()
                .filter(user=request.user, date=today)
                .first()
            )
            if attendance is None:
                return Response(
                    {"detail": "No check-in found for today."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # The guard that was missing: a row can exist with no check-in, because
            # approving leave creates one.
            if attendance.check_in is None:
                return Response(
                    {"detail": "You have not checked in today, so there is nothing to check out of."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if attendance.check_out:
                return Response(
                    {"detail": "Already checked out today."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()
            if now < attendance.check_in:
                return Response(
                    {"detail": "Check-out cannot precede check-in."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            attendance.check_out = now
            hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600
            attendance.total_hours = round(hours, 2)
            attendance.status = calculate_status(attendance.total_hours)
            attendance.save(update_fields=["check_out", "total_hours", "status"])

        return Response(
            {
                "detail": "Check-out successful",
                "check_out": attendance.check_out,
                "total_hours": attendance.total_hours,
                "status": attendance.status,
            },
            status=status.HTTP_200_OK,
        )


class MyAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = apply_date_filters(
            Attendance.objects.filter(user=request.user), request
        ).order_by("-date")

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AttendanceSerializer(page, many=True).data)


class AllAttendanceAPIView(APIView):
    """Every employee's attendance for the caller's organization.

    Admins are no longer excluded: the old `.exclude(user__role="ADMIN")` meant an
    admin's own attendance was invisible to the company and admins were exempt
    from the oversight everyone else was subject to (audit V-28).
    """

    permission_classes = [IsAuthenticated, IsManagement]

    def get(self, request):
        queryset = Attendance.objects.filter(
            user__organization=organization_of(request.user)
        ).select_related("user")

        employee_id = request.query_params.get("employee_id")
        if employee_id:
            queryset = queryset.filter(user_id=employee_id)

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        queryset = apply_date_filters(queryset, request).order_by("-date", "user_id")

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            AttendanceListSerializer(page, many=True).data
        )
