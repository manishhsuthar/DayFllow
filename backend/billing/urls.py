from django.urls import path

from .api import (
    CheckoutSessionAPIView,
    PlanListAPIView,
    PortalSessionAPIView,
    StripeWebhookAPIView,
    SubscriptionAPIView,
)

urlpatterns = [
    path("plans/", PlanListAPIView.as_view(), name="billing-plans"),
    path("subscription/", SubscriptionAPIView.as_view(), name="billing-subscription"),
    path("checkout/", CheckoutSessionAPIView.as_view(), name="billing-checkout"),
    path("portal/", PortalSessionAPIView.as_view(), name="billing-portal"),
    path("webhook/", StripeWebhookAPIView.as_view(), name="billing-webhook"),
]
