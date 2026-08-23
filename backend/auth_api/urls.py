from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordAPIView,
    CreateEmployeeAPIView,
    CurrentUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    PasswordResetConfirmAPIView,
    PasswordResetRequestAPIView,
)

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="login"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", CurrentUserAPIView.as_view(), name="current_user"),
    path("change-password/", ChangePasswordAPIView.as_view(), name="change_password"),
    path("password-reset/", PasswordResetRequestAPIView.as_view(), name="password_reset"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmAPIView.as_view(),
        name="password_reset_confirm",
    ),
    path("create-employee/", CreateEmployeeAPIView.as_view(), name="create-employee"),
]
