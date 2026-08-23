from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "timezone", "is_active", "employee_sequence", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active", "timezone")
    readonly_fields = ("created_at", "updated_at", "employee_sequence")
