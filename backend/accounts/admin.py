from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    ordering = ("login_id",)
    list_display = ("login_id", "email", "organization", "role", "is_active", "is_approved")
    list_filter = ("role", "is_active", "is_approved", "organization")
    search_fields = ("login_id", "email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("login_id", "email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name")}),
        (
            "Organization",
            {"fields": ("organization", "role", "department", "employment_type", "date_of_joining")},
        ),
        (
            "Status",
            {"fields": ("is_active", "is_approved", "must_change_password", "is_staff", "is_superuser")},
        ),
        ("Timestamps", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("login_id", "email", "password1", "password2", "organization", "role"),
            },
        ),
    )
