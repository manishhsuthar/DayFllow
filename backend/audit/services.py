"""The single entry point for writing audit entries."""

import logging
from decimal import Decimal

from .models import AuditLog

logger = logging.getLogger("dayflow.audit")


def _jsonable(value):
    """Coerce a value into something the JSONField will accept.

    Recurses: change maps are nested as {"field": {"from": x, "to": y}}, and x/y
    are routinely Decimals and datetimes.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record(*, organization, actor, action, target=None, changes=None, label=""):
    """Write one audit entry.

    Call inside the transaction that performs the action, so the entry exists if
    and only if the action committed.
    """
    if organization is None:
        return None

    target_type = target_id = target_label = ""
    if target is not None:
        target_type = target.__class__.__name__
        target_id = str(getattr(target, "pk", "") or "")
        target_label = label or str(target)[:255]
    elif label:
        target_label = label[:255]

    entry = AuditLog.objects.create(
        organization=organization,
        actor=actor if getattr(actor, "pk", None) else None,
        actor_label=getattr(actor, "login_id", "") or "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        changes={k: _jsonable(v) for k, v in (changes or {}).items()},
    )
    logger.info(
        "%s org=%s actor=%s target=%s:%s",
        action,
        organization.slug,
        entry.actor_label or "system",
        target_type or "-",
        target_id or "-",
    )
    return entry


def diff(before: dict, after: dict) -> dict:
    """A {"field": {"from": x, "to": y}} map of what actually changed."""
    return {
        key: {"from": _jsonable(before.get(key)), "to": _jsonable(after.get(key))}
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    }
