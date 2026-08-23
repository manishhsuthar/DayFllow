import logging

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomUser
from accounts.permissions import IsManagement
from audit.models import AuditLog
from billing.permissions import HasActiveSubscription, HasSeatAvailable
from audit.services import record

from .serializers import ChangePasswordSerializer, CreateEmployeeSerializer, LoginSerializer

logger = logging.getLogger("dayflow.security")
reset_token_generator = PasswordResetTokenGenerator()


def _session_payload(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "must_change_password": user.must_change_password,
        "user": _user_payload(user),
    }


def _user_payload(user):
    organization = user.organization
    return {
        "id": user.id,
        "login_id": user.login_id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "department": user.department,
        "employment_type": user.employment_type,
        "date_of_joining": user.date_of_joining,
        "must_change_password": user.must_change_password,
        "organization": (
            {
                "name": organization.name,
                "slug": organization.slug,
                "timezone": organization.timezone,
                "logo_url": organization.logo_url,
            }
            if organization
            else None
        ),
    }


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        logger.info("login succeeded login_id=%s", user.login_id)
        return Response(_session_payload(user), status=status.HTTP_200_OK)


class CurrentUserAPIView(APIView):
    """Server-authoritative identity.

    The frontend used to read its role out of localStorage, which the user
    controls, so editing one key revealed the whole admin interface (audit V-24).
    Clients read their role from here instead.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user), status=status.HTTP_200_OK)


class LogoutAPIView(APIView):
    """Blacklist the refresh token.

    Logout used to just clear localStorage, leaving the token valid server-side
    for up to seven days (audit V-23).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw = request.data.get("refresh")
        if not raw:
            return Response(
                {"detail": "A refresh token is required to log out."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(raw).blacklist()
        except TokenError:
            # Already expired or blacklisted: the session is gone either way.
            pass
        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)


class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            logger.warning("change-password rejected login_id=%s reason=bad_old", user.login_id)
            return Response(
                {"detail": "Old password is incorrect"}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        logger.info("password changed login_id=%s", user.login_id)

        # Issue a fresh session so the caller is not left holding a token minted
        # under the old password.
        return Response(
            {"detail": "Password changed successfully", **_session_payload(user)},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestSerializer(drf_serializers.Serializer):
    email = drf_serializers.EmailField()


class PasswordResetRequestAPIView(APIView):
    """Start a password reset (audit V-27: there was no recovery route at all)."""

    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = reset_token_generator.make_token(user)
            link = f"{settings.FRONTEND_BASE_URL}/#/reset-password?uid={uid}&token={token}"
            send_mail(
                subject="Reset your DayFlow password",
                message=(
                    f"Hello {user.first_name or user.login_id},\n\n"
                    f"Use this link to choose a new password:\n{link}\n\n"
                    f"It expires in {settings.PASSWORD_RESET_TIMEOUT // 60} minutes. "
                    "If you did not request this, you can ignore this email.\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info("password reset requested login_id=%s", user.login_id)

        # Always the same response, so the endpoint cannot enumerate accounts.
        return Response(
            {"detail": "If that email is registered, a reset link has been sent."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmSerializer(drf_serializers.Serializer):
    uid = drf_serializers.CharField()
    token = drf_serializers.CharField()
    new_password = drf_serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        validate_password(value)
        return value


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
            user = CustomUser.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            user = None

        if user is None or not reset_token_generator.check_token(
            user, serializer.validated_data["token"]
        ):
            return Response(
                {"detail": "This reset link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        logger.info("password reset completed login_id=%s", user.login_id)
        return Response({"detail": "Password has been reset."}, status=status.HTTP_200_OK)


class CreateEmployeeAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsManagement,
        HasActiveSubscription,
        HasSeatAvailable,
    ]

    def post(self, request):
        serializer = CreateEmployeeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user, temp_password = serializer.save()

        record(
            organization=user.organization,
            actor=request.user,
            action=AuditLog.Action.EMPLOYEE_CREATED,
            target=user,
            label=user.login_id,
            changes={"role": user.role, "department": user.department},
        )
        logger.info(
            "employee created login_id=%s by=%s org=%s",
            user.login_id,
            request.user.login_id,
            user.organization.slug,
        )
        return Response(
            {
                "login_id": user.login_id,
                "temporary_password": temp_password,
                "message": "Employee created successfully",
            },
            status=status.HTTP_201_CREATED,
        )
