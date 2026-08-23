"""Billing state transitions.

Everything that changes a Subscription goes through here, so the rules live in
one place and every change is audited.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from audit.services import record

from .models import Plan, Subscription

logger = logging.getLogger("dayflow.billing")

#: Stripe subscription status -> our own. Identical today, mapped explicitly so a
#: new Stripe status cannot silently become an entitlement.
STATUS_MAP = {
    "trialing": Subscription.Status.TRIALING,
    "active": Subscription.Status.ACTIVE,
    "past_due": Subscription.Status.PAST_DUE,
    "canceled": Subscription.Status.CANCELED,
    "unpaid": Subscription.Status.UNPAID,
    "incomplete": Subscription.Status.INCOMPLETE,
    "incomplete_expired": Subscription.Status.INCOMPLETE_EXPIRED,
    "paused": Subscription.Status.PAUSED,
}


def default_plan():
    return Plan.objects.filter(is_active=True, is_default=True).first() or Plan.objects.filter(
        is_active=True
    ).first()


def start_trial(organization) -> Subscription:
    """Give a newly created organization its trial.

    Called from signup. A trial is a real Subscription row, so entitlement has
    exactly one code path whether or not money has changed hands yet.
    """
    trial_days = getattr(settings, "BILLING_TRIAL_DAYS", 14)
    subscription, created = Subscription.objects.get_or_create(
        organization=organization,
        defaults={
            "plan": default_plan(),
            "status": Subscription.Status.TRIALING,
            "trial_end": timezone.now() + timedelta(days=trial_days),
        },
    )
    if created:
        logger.info(
            "trial started org=%s days=%s plan=%s",
            organization.slug,
            trial_days,
            subscription.plan.code if subscription.plan else "none",
        )
    return subscription


def get_or_create_subscription(organization) -> Subscription:
    subscription = Subscription.objects.filter(organization=organization).first()
    return subscription or start_trial(organization)


def _as_datetime(epoch):
    if not epoch:
        return None
    from datetime import datetime, timezone as dt_timezone

    return datetime.fromtimestamp(int(epoch), tz=dt_timezone.utc)


def _stripe_get(obj, *path, default=None):
    """Read a nested value from a Stripe object or plain dict."""
    current = obj
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return default if current is None else current


@transaction.atomic
def apply_stripe_subscription(subscription: Subscription, stripe_subscription, actor=None):
    """Write Stripe's view of a subscription onto the local row.

    Stripe is authoritative. The local row is a cache; nothing here trusts input
    that came from a browser.
    """
    before = {
        "status": subscription.status,
        "plan": subscription.plan.code if subscription.plan else None,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
    }

    raw_status = _stripe_get(stripe_subscription, "status", default="")
    mapped = STATUS_MAP.get(raw_status)
    if mapped is None:
        # Unknown status: refuse to guess. Treat as unentitled and shout.
        logger.error(
            "unknown stripe subscription status %r for org=%s",
            raw_status,
            subscription.organization.slug,
        )
        mapped = Subscription.Status.INCOMPLETE
    subscription.status = mapped

    subscription.stripe_subscription_id = (
        _stripe_get(stripe_subscription, "id", default="") or subscription.stripe_subscription_id
    )
    customer_id = _stripe_get(stripe_subscription, "customer")
    if isinstance(customer_id, str):
        subscription.stripe_customer_id = customer_id

    subscription.current_period_end = _as_datetime(
        _stripe_get(stripe_subscription, "current_period_end")
    )
    subscription.trial_end = _as_datetime(_stripe_get(stripe_subscription, "trial_end"))
    subscription.cancel_at_period_end = bool(
        _stripe_get(stripe_subscription, "cancel_at_period_end", default=False)
    )
    subscription.canceled_at = _as_datetime(_stripe_get(stripe_subscription, "canceled_at"))

    # Resolve the plan from the Stripe Price, falling back to metadata.
    price_id = _stripe_get(stripe_subscription, "items", "data", default=None)
    if isinstance(price_id, list) and price_id:
        price_id = _stripe_get(price_id[0], "price", "id")
    else:
        price_id = None

    plan = None
    if price_id:
        plan = Plan.objects.filter(stripe_price_id=price_id).first()
    if plan is None:
        plan_code = _stripe_get(stripe_subscription, "metadata", "plan_code")
        if plan_code:
            plan = Plan.objects.filter(code=plan_code).first()
    if plan is not None:
        subscription.plan = plan

    subscription.save()

    after = {
        "status": subscription.status,
        "plan": subscription.plan.code if subscription.plan else None,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
    }
    if before != after:
        record(
            organization=subscription.organization,
            actor=actor,
            action=AuditLog.Action.SUBSCRIPTION_CHANGED,
            target=subscription,
            label=subscription.organization.slug,
            changes={
                key: {"from": before[key], "to": after[key]}
                for key in after
                if before[key] != after[key]
            },
        )
    logger.info(
        "subscription synced org=%s status=%s plan=%s",
        subscription.organization.slug,
        subscription.status,
        subscription.plan.code if subscription.plan else "none",
    )
    return subscription


def seat_check(organization, *, adding=1):
    """Whether the organization may activate `adding` more employees.

    Returns (allowed, message).
    """
    subscription = get_or_create_subscription(organization)
    limit = subscription.seat_limit
    if limit is None:
        return True, ""

    in_use = subscription.seats_in_use()
    if in_use + adding <= limit:
        return True, ""

    plan_name = subscription.plan.name if subscription.plan else "your plan"
    return False, (
        f"{plan_name} includes {limit} employee seats and {in_use} are in use. "
        "Upgrade your plan to add more."
    )
