"""Billing endpoints.

The old flow had the browser call an unauthenticated `verify/` endpoint, which
returned success and stored nothing (audit V-10). Here the browser can only ask
for a Checkout session; what the customer actually bought arrives by
signature-verified webhook, straight from Stripe.
"""

import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOrganizationOwner
from organizations.models import Organization
from organizations.scoping import organization_of

from . import stripe_gateway
from .models import Plan, Subscription, WebhookEvent
from .serializers import CheckoutSerializer, PlanSerializer, SubscriptionSerializer
from .services import apply_stripe_subscription, get_or_create_subscription

logger = logging.getLogger("dayflow.billing")

#: Events that change entitlement. Anything else is acknowledged and ignored.
HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
}


class PlanListAPIView(APIView):
    """The public pricing table."""

    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True)
        return Response(
            {
                "currency": settings.BILLING_CURRENCY,
                "trial_days": settings.BILLING_TRIAL_DAYS,
                "billing_enabled": stripe_gateway.is_configured(),
                "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
                "plans": PlanSerializer(plans, many=True).data,
            }
        )


class SubscriptionAPIView(APIView):
    """The caller's own subscription state."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = get_or_create_subscription(organization_of(request.user))
        return Response(SubscriptionSerializer(subscription).data)


class CheckoutSessionAPIView(APIView):
    """Start a Stripe Checkout session. Owner only."""

    permission_classes = [IsAuthenticated, IsOrganizationOwner]
    throttle_scope = "billing"

    def post(self, request):
        if not stripe_gateway.is_configured():
            return Response(
                {"detail": "Billing is not configured on this deployment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = organization_of(request.user)
        subscription = get_or_create_subscription(organization)

        try:
            session = stripe_gateway.create_checkout_session(
                organization=organization,
                subscription=subscription,
                plan=serializer.context["plan"],
                billing_email=request.user.email,
            )
        except stripe_gateway.BillingNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {"checkout_url": session["url"], "session_id": session["id"]},
            status=status.HTTP_200_OK,
        )


class PortalSessionAPIView(APIView):
    """Open Stripe's hosted billing portal. Owner only."""

    permission_classes = [IsAuthenticated, IsOrganizationOwner]
    throttle_scope = "billing"

    def post(self, request):
        subscription = get_or_create_subscription(organization_of(request.user))
        if not subscription.stripe_customer_id:
            return Response(
                {"detail": "No billing account yet. Choose a plan first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            session = stripe_gateway.create_portal_session(
                subscription=subscription,
                return_url=request.data.get("return_url") or settings.FRONTEND_BASE_URL,
            )
        except stripe_gateway.BillingNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"portal_url": session["url"]}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookAPIView(APIView):
    """Stripe's callback. The only writer of subscription state.

    Unauthenticated by necessity -- Stripe cannot hold a JWT -- but every request
    must carry a valid `Stripe-Signature`, so the endpoint is not open in any
    meaningful sense.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        if not signature:
            return Response(
                {"detail": "Missing signature."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            event = stripe_gateway.construct_event(request.body, signature)
        except stripe_gateway.BillingNotConfigured as exc:
            logger.error("webhook rejected: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            # Bad signature, malformed body, replayed timestamp.
            logger.warning("webhook signature verification failed: %s", exc)
            return Response(
                {"detail": "Signature verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_id = event["id"]
        event_type = event["type"]

        # Idempotency: Stripe retries on any non-2xx and may deliver twice.
        record_obj, created = WebhookEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults={"event_type": event_type, "payload": json.loads(json.dumps(event, default=str))},
        )
        if not created and record_obj.processed_at:
            return Response({"detail": "Already processed."}, status=status.HTTP_200_OK)

        if event_type not in HANDLED_EVENTS:
            record_obj.processed_at = timezone.now()
            record_obj.save(update_fields=["processed_at"])
            return Response({"detail": "Ignored."}, status=status.HTTP_200_OK)

        try:
            with transaction.atomic():
                self._handle(event_type, event["data"]["object"])
                record_obj.processed_at = timezone.now()
                record_obj.error = ""
                record_obj.save(update_fields=["processed_at", "error"])
        except Exception as exc:
            logger.exception("webhook handling failed event=%s type=%s", event_id, event_type)
            WebhookEvent.objects.filter(pk=record_obj.pk).update(error=str(exc)[:2000])
            # 500 makes Stripe retry, which is what we want for a transient fault.
            return Response(
                {"detail": "Handler failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"detail": "OK"}, status=status.HTTP_200_OK)

    # -- handlers ---------------------------------------------------------

    def _resolve_subscription(self, obj):
        """Find the local Subscription for a Stripe object, several ways round."""
        organization_id = (obj.get("metadata") or {}).get("organization_id") or obj.get(
            "client_reference_id"
        )
        if organization_id:
            organization = Organization.objects.filter(pk=organization_id).first()
            if organization:
                return get_or_create_subscription(organization)

        customer_id = obj.get("customer")
        if isinstance(customer_id, str):
            existing = Subscription.objects.filter(stripe_customer_id=customer_id).first()
            if existing:
                return existing

        subscription_id = obj.get("subscription") or obj.get("id")
        if isinstance(subscription_id, str):
            existing = Subscription.objects.filter(
                stripe_subscription_id=subscription_id
            ).first()
            if existing:
                return existing
        return None

    def _handle(self, event_type, obj):
        subscription = self._resolve_subscription(obj)
        if subscription is None:
            logger.warning("webhook %s could not be matched to an organization", event_type)
            return

        if event_type == "checkout.session.completed":
            stripe_subscription_id = obj.get("subscription")
            if not stripe_subscription_id:
                return
            # Re-fetch from Stripe rather than trusting the session payload.
            apply_stripe_subscription(
                subscription, stripe_gateway.retrieve_subscription(stripe_subscription_id)
            )
            return

        if event_type.startswith("customer.subscription."):
            if event_type.endswith(".deleted"):
                subscription.status = Subscription.Status.CANCELED
                subscription.canceled_at = timezone.now()
                subscription.save(update_fields=["status", "canceled_at", "updated_at"])
                return
            apply_stripe_subscription(subscription, obj)
            return

        if event_type in ("invoice.payment_succeeded", "invoice.payment_failed"):
            stripe_subscription_id = obj.get("subscription")
            if stripe_subscription_id:
                apply_stripe_subscription(
                    subscription, stripe_gateway.retrieve_subscription(stripe_subscription_id)
                )
