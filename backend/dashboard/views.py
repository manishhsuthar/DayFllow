from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from datetime import date
from django.utils import timezone

from attendance.models import Attendance
from leave.models import LeaveRequest
from accounts.models import CustomUser
from payroll.models import PayrollRecord
from organizations.scoping import organization_of

class EmployeeDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        payroll_month = today.replace(day=1)

        today_attendance = Attendance.objects.filter(
            user=request.user,
            date=today
        ).first()

        month_attendance = Attendance.objects.filter(
            user=request.user,
            date__month=today.month,
            date__year=today.year
        )
        payroll = PayrollRecord.objects.filter(
            employee=request.user,
            month=payroll_month,
        ).first()

        data = {
            "today_status": today_attendance.status if today_attendance else "PENDING",
            "today_check_in": today_attendance.check_in if today_attendance else None,
            "today_check_out": today_attendance.check_out if today_attendance else None,
            "present_days": month_attendance.filter(status="PRESENT").count(),
            "leave_days": month_attendance.filter(status="LEAVE").count(),
            "payroll_status": payroll.status if payroll else "PENDING",
            "pending_leaves": LeaveRequest.objects.filter(
                user=request.user,
                status="PENDING"
            ).count()
        }

        return Response(data)

class AdminDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ["ADMIN", "HR"]:
            return Response(
                {"detail": "Permission denied"},
                status=403
            )

        today = date.today()

        data = {
            "total_employees": CustomUser.objects.filter(
                organization=organization_of(request.user)
            ).exclude(role="ADMIN").count(),
            "present_today": Attendance.objects.filter(
                date=today,
                status="PRESENT",
                user__organization=organization_of(request.user),
            ).count(),
            "absent_today": Attendance.objects.filter(
                date=today,
                status="ABSENT",
                user__organization=organization_of(request.user),
            ).count(),
            "on_leave_today": Attendance.objects.filter(
                date=today,
                status="LEAVE",
                user__organization=organization_of(request.user),
            ).count(),
            "pending_leaves": LeaveRequest.objects.filter(
                status="PENDING",
                user__organization=organization_of(request.user),
            ).count(),
            "pending_payrolls": PayrollRecord.objects.filter(
                employee__organization=organization_of(request.user),
                status="PENDING",
            ).count(),
        }

        return Response(data)


class DashboardNotificationsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _relative_time(self, value):
        if not value:
            return "Just now"

        now = timezone.now()
        delta = now - value
        seconds = int(max(delta.total_seconds(), 0))

        if seconds < 60:
            return "Just now"
        if seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        if seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"

    def get(self, request):
        user = request.user
        items = []

        if user.role in ["ADMIN", "HR"]:
            pending_payrolls = PayrollRecord.objects.filter(
                employee__organization=organization_of(user),
                status="PENDING",
            ).count()
            if pending_payrolls > 0:
                items.append(
                    {
                        "id": "pending-payrolls",
                        "title": "Pending payroll credits",
                        "message": f"{pending_payrolls} payroll record(s) are pending salary credit.",
                        "time": "Updated now",
                        "tone": "warning",
                        "read": False,
                    }
                )

            pending_leaves = LeaveRequest.objects.filter(
                status="PENDING",
                user__organization=organization_of(user),
            ).count()
            if pending_leaves > 0:
                items.append(
                    {
                        "id": "pending-leaves",
                        "title": "Pending leave requests",
                        "message": f"{pending_leaves} leave request(s) are waiting for review.",
                        "time": "Updated now",
                        "tone": "warning",
                        "read": False,
                    }
                )

            latest_leaves = LeaveRequest.objects.filter(
                user__organization=organization_of(user),
            ).select_related("user").order_by("-created_at")[:3]
            for leave in latest_leaves:
                name = (
                    f"{leave.user.first_name} {leave.user.last_name}".strip()
                    if leave.user
                    else "Employee"
                ) or "Employee"
                items.append(
                    {
                        "id": f"leave-{leave.id}",
                        "title": f"{name} submitted a {leave.leave_type.lower()} leave",
                        "message": f"{leave.start_date} to {leave.end_date}",
                        "time": self._relative_time(leave.created_at),
                        "tone": "info" if leave.status == "PENDING" else "success",
                        "read": leave.status != "PENDING",
                    }
                )
        else:
            latest_my_leaves = LeaveRequest.objects.filter(user=user).order_by("-created_at")[:5]
            for leave in latest_my_leaves:
                if leave.status == "APPROVED":
                    tone = "success"
                    title = "Leave request approved"
                elif leave.status == "REJECTED":
                    tone = "warning"
                    title = "Leave request rejected"
                else:
                    tone = "info"
                    title = "Leave request pending"

                items.append(
                    {
                        "id": f"my-leave-{leave.id}",
                        "title": title,
                        "message": f"{leave.leave_type.title()} leave: {leave.start_date} to {leave.end_date}",
                        "time": self._relative_time(leave.created_at),
                        "tone": tone,
                        "read": leave.status != "PENDING",
                    }
                )

            latest_salary_credits = PayrollRecord.objects.filter(
                employee=user,
                status="PAID",
            ).order_by("-credited_at", "-updated_at")[:5]
            for payroll in latest_salary_credits:
                credited_time = payroll.credited_at or payroll.updated_at
                is_recent = bool(credited_time) and (timezone.now() - credited_time).days < 7
                items.append(
                    {
                        "id": f"salary-{payroll.id}",
                        "title": "Salary credited",
                        "message": f"{payroll.month:%B %Y} salary of {payroll.net_salary} has been credited.",
                        "time": self._relative_time(credited_time),
                        "tone": "success",
                        "read": not is_recent,
                    }
                )

            today_attendance = Attendance.objects.filter(user=user, date=date.today()).first()
            if not today_attendance:
                items.insert(
                    0,
                    {
                        "id": "attendance-reminder",
                        "title": "Attendance reminder",
                        "message": "No attendance entry found for today.",
                        "time": "Today",
                        "tone": "warning",
                        "read": False,
                    },
                )

        return Response({"items": items})
