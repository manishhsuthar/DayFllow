"""Identifier and credential generation.

The previous implementations had two problems (audit V-11):

* `generate_login_id` derived its serial from ``CustomUser.objects.filter(
  date_of_joining__year=year).count() + 1`` -- a **global** counter. Tenant A's
  first hire got serial 0001 and an unrelated tenant B's first hire got 0002, so
  every customer's login ids leaked the platform-wide employee count. It was also
  a read-modify-write with no lock, so two concurrent hires computed the same id
  and one insert died on the unique constraint.

* `generate_temp_password` used ``random.choices``. The Mersenne Twister is not
  cryptographically secure and must never generate credentials.
"""

import secrets
import string

from django.db import IntegrityError, transaction

# Ambiguous characters removed: temporary passwords get read aloud and retyped.
_PASSWORD_ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI"
)


def generate_temp_password(length: int = 16) -> str:
    """A cryptographically secure temporary password."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _compose(organization, first_name: str, last_name: str, serial: int) -> str:
    prefix = (organization.slug[:3] or "org").upper()
    fn = (first_name or "X")[:2].upper().ljust(2, "X")
    ln = (last_name or "X")[:2].upper().ljust(2, "X")
    return f"{prefix}{fn}{ln}{serial:05d}"


def generate_login_id(organization, first_name: str, last_name: str) -> str:
    """A login id unique within `organization`, allocated from its own sequence.

    The sequence is reserved under ``SELECT FOR UPDATE`` so concurrent hires
    cannot collide. The retry loop covers the remaining case where a historical
    id from before the tenancy migration already occupies the slot.
    """
    from .models import CustomUser

    for _ in range(25):
        serial = organization.next_employee_number()
        candidate = _compose(organization, first_name, last_name, serial)
        if not CustomUser.objects.filter(login_id=candidate).exists():
            return candidate

    # Exhausted the retries: fall back to an opaque id rather than failing a hire.
    return f"{(organization.slug[:3] or 'org').upper()}{secrets.token_hex(5).upper()}"


def generate_owner_login_id(organization) -> str:
    """The login id for the account that creates an organization."""
    from .models import CustomUser

    base = f"{(organization.slug[:8] or 'org').upper()}-OWNER"
    if not CustomUser.objects.filter(login_id=base).exists():
        return base
    return f"{base}-{secrets.token_hex(3).upper()}"


def create_employee_with_login_id(organization, **fields):
    """Create an employee, retrying once if a login id race slips through."""
    from .models import CustomUser

    last_error = None
    for _ in range(5):
        login_id = generate_login_id(
            organization, fields.get("first_name", ""), fields.get("last_name", "")
        )
        try:
            with transaction.atomic():
                return CustomUser.objects.create(
                    login_id=login_id, organization=organization, **fields
                )
        except IntegrityError as exc:
            last_error = exc
    raise last_error
