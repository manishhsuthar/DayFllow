from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from datetime import date

from .models import Attendance
from .utils import calculate_status
from .serializers import AttendanceSerializer, AttendanceListSerializer
from leave.models import LeaveRequest
from organizations.scoping import organization_of

class CheckOutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        today = date.today()

        try:
            attendance = Attendance.objects.get(
                user=request.user,
                date=today
            )
        except Attendance.DoesNotExist:
            return Response(
                {"detail": "No check-in found"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if attendance.check_out:
            return Response(
                {"detail": "Already checked out"},
                status=status.HTTP_400_BAD_REQUEST
            )

        attendance.check_out = timezone.now()

        delta = attendance.check_out - attendance.check_in
        attendance.total_hours = round(delta.total_seconds() / 3600, 2)
        attendance.status = calculate_status(attendance.total_hours)
        attendance.save()

        return Response({"detail": "Check-out successful"})

class MyAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = Attendance.objects.filter(user=request.user)
        serializer = AttendanceSerializer(records, many=True)
        return Response(serializer.data)

class AllAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ["ADMIN", "HR"]:
            return Response(
                {"detail": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        records = Attendance.objects.filter(
            user__organization=organization_of(request.user)
        ).select_related("user", "user__organization")
        serializer = AttendanceListSerializer(records, many=True)
        return Response(serializer.data)

class CheckInAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        today = date.today()

        # 🚫 BLOCK CHECK-IN IF LEAVE APPROVED
        on_leave = LeaveRequest.objects.filter(
            user=request.user,
            status="APPROVED",
            start_date__lte=today,
            end_date__gte=today
        ).exists()

        if on_leave:
            return Response(
                {"detail": "You are on approved leave today"},
                status=400
            )

        attendance, created = Attendance.objects.get_or_create(
            user=request.user,
            date=today,
            defaults={"status": "PRESENT"},
        )

        if attendance.check_in:
            return Response(
                {"detail": "Already checked in"},
                status=400
            )

        attendance.check_in = timezone.now()
        attendance.status = "PRESENT"
        attendance.save()

        return Response({"detail": "Check-in successful"})
