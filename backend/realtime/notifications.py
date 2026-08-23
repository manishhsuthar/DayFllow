import hashlib

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone


def company_group_name(organization_id):
    """Channel group for one organization.

    Hashed rather than used directly so the group name never carries tenant data,
    and so it always satisfies the channel-name charset.
    """
    digest = hashlib.sha256(str(organization_id).encode("utf-8")).hexdigest()[:32]
    return f"org_updates_{digest}"


def get_instance_organization_id(instance):
    """Resolve the owning organization for any tenant-scoped model."""
    if hasattr(instance, "organization_id"):
        return instance.organization_id

    for attr in ("user", "employee", "owner"):
        related = getattr(instance, attr, None)
        if related is not None:
            organization_id = getattr(related, "organization_id", None)
            if organization_id:
                return organization_id

    if instance.__class__.__name__ == "Organization":
        return instance.pk

    return None


def broadcast_data_change(instance, action):
    organization_id = get_instance_organization_id(instance)
    if not organization_id:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    payload = {
        "type": "data_changed",
        "model": instance._meta.label,
        "action": action,
        "record_id": instance.pk,
        "timestamp": timezone.now().isoformat(),
    }

    def send_update():
        async_to_sync(channel_layer.group_send)(
            company_group_name(organization_id),
            {
                "type": "database.change",
                "payload": payload,
            },
        )

    transaction.on_commit(send_update)
