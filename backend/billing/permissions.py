"""Entitlement.

Payment previously granted nothing and non-payment cost nothing (audit V-10).
This is the gate that makes a subscription mean something.

It is deliberately narrow. Read access and the billing endpoints stay open when a
subscription lapses, so a customer whose card expired can still see their data,
export it, and fix their payment method. What closes is the ability to create new
work in the product.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .services import get_or_create_subscription


class HasActiveSubscription(BasePermission):
    """Require an entitled subscription for state-changing requests."""

    message = (
        "Your DayFlow subscription is not active. "
        "Renew or choose a plan in Billing to continue."
    )

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        organization = getattr(user, "organization", None)
        if organization is None:
            return False
        return get_or_create_subscription(organization).is_entitled


class HasSeatAvailable(BasePermission):
    """Require a free seat before another employee is added."""

    message = "You have used every employee seat on your plan. Upgrade to add more."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        organization = getattr(getattr(request, "user", None), "organization", None)
        if organization is None:
            return False

        from .services import seat_check

        allowed, message = seat_check(organization, adding=1)
        if not allowed:
            self.message = message
        return allowed
