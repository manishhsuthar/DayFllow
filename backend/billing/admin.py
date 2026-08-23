from django.contrib import admin

from .models import Plan, Subscription, WebhookEvent


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "price_display", "interval", "seat_limit", "is_active", "is_default")
    list_filter = ("is_active", "interval")
    search_fields = ("code", "name", "stripe_price_id")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "plan")
    search_fields = ("organization__name", "organization__slug", "stripe_customer_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "stripe_event_id", "received_at", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("stripe_event_id",)
    readonly_fields = ("stripe_event_id", "event_type", "payload", "received_at", "processed_at", "error")

    def has_add_permission(self, request):
        return False
