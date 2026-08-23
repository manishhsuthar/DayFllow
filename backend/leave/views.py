"""Leave requests and approval.

Approving leave used to call `Attendance.objects.update_or_create(..., defaults=
{"status": "LEAVE"})` over the whole range, which overwrote days the employee had
actually worked -- leaving a row that claimed status LEAVE *and* nine hours worked,
and removing those days from payroll's `PRESENT` count. An approved leave request
silently cut the employee's pay for days they were at work (audit V-06).
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsManagement, can_manage_target
from attendance.models import Attendance
from attendance.views import apply_date_filters
from audit.models import AuditLog
from audit.services import record
from core.pagination import DefaultPagination
from organizations.scoping import organization_of

from .models import LeaveRequest
from .serializers import LeaveRequestSerializer

logger = logging.getLogger("dayflow.audit")


def worked_days_in_range(user, start, end):
    """Days in the range with a recorded check-in."""
    return set(
        Attendance.objects.filter(
            user=user, date__gte=start, date__lte=end, check_in__isnull=False
        ).values_list("date", flat=True)
    )


class ApplyLeaveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LeaveRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        start = serializer.validated_data["start_date"]
        end = serializer.validated_data["end_date"]

        overlap = LeaveRequest.objects.filter(
            user=request.user,
            start_date__lte=end,
            end_date__gte=start,
            status__in=["PENDING", "APPROVED"],
        ).exists()
        if overlap:
            return Response(
                {"detail": "You already have a leave request covering some of these dates."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        worked = worked_days_in_range(request.user, start, end)
        if worked:
            listed = ", ".join(d.isoformat() for d in sorted(worked)[:5])
            return Response(
                {
                    "detail": (
                        "You have recorded attendance on these dates, so they cannot be "
                        f"covered by leave: {listed}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        leave = serializer.save(user=request.user)
        return Response(
            {"message": "Leave applied successfully", "leave": LeaveRequestSerializer(leave).data},
            status=status.HTTP_201_CREATED,
        )


class MyLeavesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = LeaveRequest.objects.filter(user=request.user).order_by("-start_date")

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(LeaveRequestSerializer(page, many=True).data)


class AllLeavesAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagement]

    def get(self, request):
        queryset = LeaveRequest.objects.filter(
            user__organization=organization_of(request.user)
        ).select_related("user")

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        employee_id = request.query_params.get("employee_id")
        if employee_id:
            queryset = queryset.filter(user_id=employee_id)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-created_at"), request, view=self
        )
        return paginator.get_paginated_response(LeaveRequestSerializer(page, many=True).data)


class ApproveRejectLeaveAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagement]

    def post(self, request, leave_id):
        action = (request.data.get("action") or "").upper()
        if action not in ("APPROVE", "REJECT"):
            return Response(
                {"detail": "Action must be APPROVE or REJECT."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            leave = (
                LeaveRequest.objects.select_for_update()
                .filter(id=leave_id, user__organization=organization_of(request.user))
                .select_related("user", "user__organization")
                .first()
            )
            if not leave:
                return Response(
                    {"detail": "Leave request not found."}, status=status.HTTP_404_NOT_FOUND
                )

            if not can_manage_target(request.user, leave.user):
                return Response(
                    {"detail": "You do not have permission to act on this request."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if leave.user_id == request.user.id:
                return Response(
                    {"detail": "You cannot approve your own leave request."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if leave.status != "PENDING":
                return Response(
                    {"detail": f"This request was already {leave.status.lower()}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if action == "REJECT":
                leave.status = "REJECTED"
                leave.save(update_fields=["status"])
                record(
                    organization=leave.user.organization,
                    actor=request.user,
                    action=AuditLog.Action.LEAVE_REJECTED,
                    target=leave,
                    label=f"{leave.user.login_id} {leave.start_date}..{leave.end_date}",
                    changes={"leave_type": leave.leave_type},
                )
                logger.info(
                    "leave rejected id=%s employee=%s by=%s",
                    leave.id,
                    leave.user.login_id,
                    request.user.login_id,
                )
                return Response({"message": "Leave rejected successfully"})

            # Approving must never overwrite a day the employee actually worked.
            worked = worked_days_in_range(leave.user, leave.start_date, leave.end_date)
            if worked:
                listed = ", ".join(d.isoformat() for d in sorted(worked)[:5])
                return Response(
                    {
                        "detail": (
                            "This employee has recorded attendance within the requested "
                            f"range, so approving it would overwrite worked days: {listed}."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            leave.status = "APPROVED"
            leave.save(update_fields=["status"])

            marked = 0
            current = leave.start_date
            while current <= leave.end_date:
                # Clear the time fields too: a LEAVE row must never keep stale
                # check-in/check-out values from an earlier state.
                Attendance.objects.update_or_create(
                    user=leave.user,
                    date=current,
                    defaults={
                        "status": "LEAVE",
                        "check_in": None,
                        "check_out": None,
                        "total_hours": 0.0,
                    },
                )
                marked += 1
                current += timedelta(days=1)

            record(
                organization=leave.user.organization,
                actor=request.user,
                action=AuditLog.Action.LEAVE_APPROVED,
                target=leave,
                label=f"{leave.user.login_id} {leave.start_date}..{leave.end_date}",
                changes={"leave_type": leave.leave_type, "days_marked": marked},
            )

        logger.info(
            "leave approved id=%s employee=%s by=%s days=%s",
            leave.id,
            leave.user.login_id,
            request.user.login_id,
            marked,
        )
        return Response({"message": "Leave approved successfully", "days_marked": marked})
