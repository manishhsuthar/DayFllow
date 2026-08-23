"""Create the default USD plans, and optionally create matching Stripe Prices.

    python manage.py seed_plans                # local rows only
    python manage.py seed_plans --sync-stripe  # also create Products/Prices in Stripe

Re-running is safe: plans are matched by `code` and updated in place, and Stripe
objects are only created for plans that do not already have a price id.
"""

from django.core.management.base import BaseCommand

from billing.models import Plan

DEFAULT_PLANS = [
    {
        "code": "starter",
        "name": "Starter",
        "description": "For small teams getting started with DayFlow.",
        "amount_cents": 1900,
        "seat_limit": 10,
        "sort_order": 1,
        "is_default": True,
        "features": [
            "Up to 10 employees",
            "Attendance tracking and reports",
            "Leave requests and approvals",
            "Employee directory",
            "Payroll runs and salary slips",
            "Email support",
        ],
    },
    {
        "code": "growth",
        "name": "Growth",
        "description": "For growing teams that need more capacity and history.",
        "amount_cents": 4900,
        "seat_limit": 50,
        "sort_order": 2,
        "features": [
            "Up to 50 employees",
            "Everything in Starter",
            "Expense claims and approvals",
            "Full audit trail",
            "Spreadsheet exports",
            "Priority email support",
        ],
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Unlimited seats with onboarding support.",
        "amount_cents": 14900,
        "seat_limit": None,
        "sort_order": 3,
        "features": [
            "Unlimited employees",
            "Everything in Growth",
            "Multi-timezone organizations",
            "Guided onboarding",
            "Dedicated support contact",
        ],
    },
]


class Command(BaseCommand):
    help = "Create or update the default USD subscription plans."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-stripe",
            action="store_true",
            help="Create a Stripe Product and Price for any plan missing one.",
        )

    def handle(self, *args, **options):
        for spec in DEFAULT_PLANS:
            plan, created = Plan.objects.update_or_create(
                code=spec["code"],
                defaults={**spec, "currency": "usd", "interval": Plan.Interval.MONTH},
            )
            self.stdout.write(
                f"{'created' if created else 'updated'} {plan.code}: "
                f"{plan.price_display}/{plan.interval}, "
                f"seats={plan.seat_limit if plan.seat_limit is not None else 'unlimited'}"
            )

        if not options["sync_stripe"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo Stripe prices created. Plans without a stripe_price_id cannot be "
                    "checked out.\nRe-run with --sync-stripe once STRIPE_SECRET_KEY is set."
                )
            )
            return

        from billing import stripe_gateway

        if not stripe_gateway.is_configured():
            self.stderr.write(self.style.ERROR("STRIPE_SECRET_KEY is not set."))
            return

        import stripe

        from django.conf import settings

        stripe.api_key = settings.STRIPE_SECRET_KEY

        for plan in Plan.objects.filter(stripe_price_id=""):
            product = stripe.Product.create(
                name=f"DayFlow {plan.name}",
                description=plan.description,
                metadata={"plan_code": plan.code},
            )
            price = stripe.Price.create(
                product=product["id"],
                unit_amount=plan.amount_cents,
                currency=plan.currency,
                recurring={"interval": plan.interval},
                metadata={"plan_code": plan.code},
            )
            plan.stripe_price_id = price["id"]
            plan.save(update_fields=["stripe_price_id", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"  stripe price for {plan.code}: {price['id']}"))
