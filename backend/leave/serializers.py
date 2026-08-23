from datetime import timedelta

from rest_framework import serializers

from .models import LeaveRequest

#: Longest single leave request. The old code had no bound at all, so a ten-year
#: request was accepted and its approval then wrote ~3,650 attendance rows in one
#: request cycle (audit V-05).
MAX_LEAVE_DAYS = 90

#: How far back a request may reach. Backdating is allowed for genuine cases
#: (sick leave recorded on return) but not indefinitely.
MAX_BACKDATE_DAYS = 30


class LeaveRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)
    user_role = serializers.SerializerMethodField(read_only=True)
    total_days = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = (
            "id",
            "user",
            "user_name",
            "user_role",
            "leave_type",
            "start_date",
            "end_date",
            "total_days",
            "reason",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "user", "status", "created_at")

    def get_user_name(self, obj):
        return obj.user.full_name if obj.user else ""

    def get_user_role(self, obj):
        return obj.user.role if obj.user else None

    def get_total_days(self, obj):
        if not obj.start_date or not obj.end_date:
            return 0
        return (obj.end_date - obj.start_date).days + 1

    def validate_reason(self, value):
        value = (value or "").strip()
        if len(value) < 3:
            raise serializers.ValidationError("Please give a reason of at least 3 characters.")
        return value

    def validate(self, attrs):
        """All the bounds the original had none of (audit V-05)."""
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if not start or not end:
            return attrs

        if end < start:
            raise serializers.ValidationError(
                {"end_date": "End date must not be before the start date."}
            )

        duration = (end - start).days + 1
        if duration > MAX_LEAVE_DAYS:
            raise serializers.ValidationError(
                {
                    "end_date": (
                        f"A single leave request may not exceed {MAX_LEAVE_DAYS} days "
                        f"(this one is {duration}). Split it into separate requests."
                    )
                }
            )

        user = self.context["request"].user
        organization = getattr(user, "organization", None)
        today = organization.today() if organization else start

        if start < today - timedelta(days=MAX_BACKDATE_DAYS):
            raise serializers.ValidationError(
                {
                    "start_date": (
                        f"Leave may not be backdated more than {MAX_BACKDATE_DAYS} days. "
                        "Ask an administrator to record older leave for you."
                    )
                }
            )

        if start > today + timedelta(days=365):
            raise serializers.ValidationError(
                {"start_date": "Leave may not be requested more than a year in advance."}
            )

        return attrs
