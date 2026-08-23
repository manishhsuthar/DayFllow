"""The only module that talks to Stripe.

Isolated so that every other part of billing is testable without network access,
and so that swapping providers touches one file.

When `STRIPE_SECRET_KEY` is unset the gateway runs in **stub mode**: it raises a
clear error on any call that would need Stripe rather than pretending to succeed.
Production settings refuse to boot without a key unless the operator has
explicitly opted out.
"""

import logging

from django.conf import settings

logger = logging.getLogger("dayflow.billing")


class BillingNotConfigured(RuntimeError):
    """Raised when a Stripe call is attempted without credentials."""


def is_configured() -> bool:
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


def _client():
    if not is_configured():
        raise BillingNotConfigured(
            "Stripe is not configured. Set STRIPE_SECRET_KEY to enable billing."
        )
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    if getattr(settings, "STRIPE_API_VERSION", ""):
        stripe.api_version = settings.STRIPE_API_VERSION
    return stripe


def ensure_customer(organization, subscription, billing_email):
    """Find or create the Stripe Customer for an organization."""
    stripe = _client()

    if subscription.stripe_customer_id:
        return subscription.stripe_customer_id

    customer = stripe.Customer.create(
        email=billing_email,
        name=organization.name,
        # Lets a webhook resolve the organization even if local state is lost.
        metadata={"organization_id": str(organization.id), "organization_slug": organization.slug},
        idempotency_key=f"customer-{organization.id}",
    )
    subscription.stripe_customer_id = customer["id"]
    subscription.save(update_fields=["stripe_customer_id", "updated_at"])
    logger.info("stripe customer created org=%s id=%s", organization.slug, customer["id"])
    return customer["id"]


def create_checkout_session(*, organization, subscription, plan, billing_email, quantity=1):
    """A Stripe Checkout session for a subscription.

    Checkout is hosted by Stripe, so card details never reach this server.
    """
    stripe = _client()
    customer_id = ensure_customer(organization, subscription, billing_email)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": plan.stripe_price_id, "quantity": quantity}],
        success_url=f"{settings.BILLING_SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=settings.BILLING_CANCEL_URL,
        client_reference_id=str(organization.id),
        subscription_data={
            "metadata": {
                "organization_id": str(organization.id),
                "plan_code": plan.code,
            }
        },
        metadata={"organization_id": str(organization.id), "plan_code": plan.code},
        allow_promotion_codes=True,
    )
    logger.info(
        "checkout session created org=%s plan=%s id=%s",
        organization.slug,
        plan.code,
        session["id"],
    )
    return session


def create_portal_session(*, subscription, return_url):
    """Stripe's hosted billing portal: payment method, invoices, cancellation."""
    stripe = _client()
    if not subscription.stripe_customer_id:
        raise BillingNotConfigured("This organization has no Stripe customer yet.")
    return stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id, return_url=return_url
    )


def retrieve_subscription(stripe_subscription_id):
    return _client().Subscription.retrieve(stripe_subscription_id)


def construct_event(payload: bytes, signature: str):
    """Verify a webhook signature and return the event.

    Raises if the signature does not match, which is what stops anyone from
    POSTing a fake "payment succeeded" event to the endpoint.
    """
    stripe = _client()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise BillingNotConfigured(
            "STRIPE_WEBHOOK_SECRET is not set; webhook signatures cannot be verified."
        )
    return stripe.Webhook.construct_event(
        payload, signature, settings.STRIPE_WEBHOOK_SECRET
    )
