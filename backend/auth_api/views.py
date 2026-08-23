from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer
from rest_framework.permissions import AllowAny, IsAuthenticated
from .serializers import ChangePasswordSerializer
from .serializers import CreateEmployeeSerializer


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "must_change_password": user.must_change_password,
            "role": user.role,
            "login_id": user.login_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "company_name": user.company_name,
            "date_of_joining": user.date_of_joining,
            "department": user.department,
            "employment_type": user.employment_type,
            "salary": user.salary,
        }, status=status.HTTP_200_OK)
    
class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"detail": "Old password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save()

        return Response(
            {"detail": "Password changed successfully"},
            status=status.HTTP_200_OK
        )

class CreateEmployeeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ["ADMIN", "HR"]:
            return Response(
                {"detail": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CreateEmployeeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user, temp_password = serializer.save()

        return Response({
            "login_id": user.login_id,
            "temporary_password": temp_password,
            "message": "Employee created successfully"
        }, status=status.HTTP_201_CREATED)
