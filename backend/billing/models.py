"""Subscription billing.

Before this app, `POST /api/accounts/payments/razorpay/verify/` returned
``{"message": "Payment verified successfully."}`` and wrote nothing to the
database. There was no Plan model and no Subscription model, so a successful
payment granted nothing and skipping checkout entirely cost nothing -- the whole
paid tier was decorative (audit V-10).

Two rules hold everything together:

* **Stripe is the source of truth for subscription state.** Local rows are a
  cache, updated by webhook. The browser never tells the API what was paid.
* **Money amounts are integer cents.** Floats do not represent currency.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """A purchasable tier. Mirrors a Stripe Price."""

    class Interval(models.TextChoices):
        MONTH = "month", "Monthly"
        YEAR = "year", "Yearly"

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True, default="")

    #: Integer cents, e.g. 1900 == $19.00.
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="usd")
    interval = models.CharField(max_length=8, choices=Interval.choices, default=Interval.MONTH)

    #: Null means unlimited.
    seat_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Maximum active employees. Blank means unlimited."
    )
    features = models.JSONField(default=list, blank=True)

    #: The Stripe Price id. Blank while running without Stripe configured.
    stripe_price_id = models.CharField(max_length=255, blank=True, default="", db_index=True)

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False, help_text="Assigned to new organizations during their trial."
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "amount_cents")

    def __str__(self):
        return f"{self.name} ({self.price_display}/{self.interval})"

    @property
    def price_display(self) -> str:
        return f"${Decimal(self.amount_cents) / 100:.2f}"

    def allows_seats(self, count: int) -> bool:
        return self.seat_limit is None or count <= self.seat_limit


class Subscription(models.Model):
    """One organization's billing state. A local cache of Stripe."""

    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        UNPAID = "unpaid", "Unpaid"
        INCOMPLETE = "incomplete", "Incomplete"
        INCOMPLETE_EXPIRED = "incomplete_expired", "Incomplete (expired)"
        PAUSED = "paused", "Paused"

    #: Statuses that entitle the organization to use the product.
    ENTITLED_STATUSES = frozenset({Status.TRIALING, Status.ACTIVE, Status.PAST_DUE})

    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions", null=True, blank=True
    )

    status = models.CharField(max_length=24, choices=Status.choices, default=Status.TRIALING)

    stripe_customer_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stripe_subscription_id = models.CharField(
        max_length=255, blank=True, default="", db_index=True
    )

    trial_end = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.organization.slug}: {self.plan.code if self.plan else 'none'} ({self.status})"

    @property
    def is_entitled(self) -> bool:
        """Whether the organization may currently use the product.

        `past_due` is included deliberately: a failed card should prompt the
        customer, not lock them out of their own payroll on the same day.
        """
        if self.status not in self.ENTITLED_STATUSES:
            return False
        if self.status == self.Status.TRIALING and self.trial_end:
            return timezone.now() <= self.trial_end
        return True

    @property
    def seat_limit(self):
        return self.plan.seat_limit if self.plan else None

    def seats_in_use(self) -> int:
        return self.organization.members.filter(is_active=True).exclude(role="ADMIN").count()

    def has_seat_available(self) -> bool:
        limit = self.seat_limit
        return limit is None or self.seats_in_use() < limit


class WebhookEvent(models.Model):
    """Every Stripe event we have processed, for idempotency.

    Stripe retries on any non-2xx and can deliver the same event more than once;
    without this an upgrade could be applied twice.
    """

    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)

    def __str__(self):
        return f"{self.event_type} {self.stripe_event_id}"
