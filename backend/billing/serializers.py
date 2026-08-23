from rest_framework import serializers

from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    price_display = serializers.CharField(read_only=True)
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = (
            "code",
            "name",
            "description",
            "amount_cents",
            "amount",
            "price_display",
            "currency",
            "interval",
            "seat_limit",
            "features",
            "is_default",
        )
        read_only_fields = fields

    def get_amount(self, obj):
        """Decimal-string major units, for display. Never used for arithmetic."""
        return f"{obj.amount_cents / 100:.2f}"


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    is_entitled = serializers.BooleanField(read_only=True)
    seats_in_use = serializers.SerializerMethodField()
    seat_limit = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Subscription
        fields = (
            "status",
            "plan",
            "is_entitled",
            "seats_in_use",
            "seat_limit",
            "trial_end",
            "current_period_end",
            "cancel_at_period_end",
            "canceled_at",
        )
        read_only_fields = fields

    def get_seats_in_use(self, obj):
        return obj.seats_in_use()


class CheckoutSerializer(serializers.Serializer):
    plan_code = serializers.SlugField()

    def validate_plan_code(self, value):
        plan = Plan.objects.filter(code=value, is_active=True).first()
        if not plan:
            raise serializers.ValidationError("Unknown plan.")
        if not plan.stripe_price_id:
            raise serializers.ValidationError(
                "This plan is not connected to Stripe yet. Contact support."
            )
        self.context["plan"] = plan
        return value
