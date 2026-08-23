from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from datetime import timedelta, date

from .models import LeaveRequest
from .serializers import LeaveRequestSerializer
from attendance.models import Attendance
from organizations.scoping import organization_of

#Employee applies for leave
class ApplyLeaveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LeaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        start = serializer.validated_data["start_date"]
        end = serializer.validated_data["end_date"]

        overlap = LeaveRequest.objects.filter(
            user=request.user,
            start_date__lte=end,
            end_date__gte=start,
            status__in=["PENDING", "APPROVED"]
        ).exists()

        if overlap:
            return Response(
                {"detail": "Overlapping leave already exists"},
                status=400
            )

        leave = serializer.save(user=request.user)
        return Response(
            {"message": "Leave applied successfully"},
            status=201
        )

#View My Leave Requests
class MyLeavesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        leaves = LeaveRequest.objects.filter(user=request.user)
        serializer = LeaveRequestSerializer(leaves, many=True)
        return Response(serializer.data)

#View all Leaves - Admin Only
class AllLeavesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ["ADMIN", "HR"]:
            return Response(
                {"detail": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        leaves = LeaveRequest.objects.filter(
            user__organization=organization_of(request.user)
        ).select_related("user", "user__organization")
        serializer = LeaveRequestSerializer(leaves, many=True)
        return Response(serializer.data)

#Approve or Reject Leave - Admin Only
class ApproveRejectLeaveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, leave_id):
        if request.user.role not in ["ADMIN", "HR"]:
            return Response(
                {"detail": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        action = request.data.get("action")

        if action not in ["APPROVE", "REJECT"]:
            return Response(
                {"detail": "Invalid action"},
                status=status.HTTP_400_BAD_REQUEST
            )

        leave = LeaveRequest.objects.filter(
            id=leave_id,
            user__organization=organization_of(request.user),
        ).select_related("user").first()
        if not leave:
            return Response(
                {"detail": "Leave request not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        leave.status = "APPROVED" if action == "APPROVE" else "REJECTED"
        leave.save()

        # If approved → mark attendance as LEAVE
        if leave.status == "APPROVED":
            current = leave.start_date
            while current <= leave.end_date:
                Attendance.objects.update_or_create(
                    user=leave.user,
                    date=current,
                    defaults={"status": "LEAVE"}
                )
                current += timedelta(days=1)

        return Response({"message": f"Leave {leave.status.lower()} successfully"})
