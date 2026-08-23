from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "action",
            "action_label",
            "actor_label",
            "target_type",
            "target_id",
            "target_label",
            "changes",
            "created_at",
        )
        read_only_fields = fields
