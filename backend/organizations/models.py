"""The tenant boundary.

Tenancy used to be a plain `company_name` string on the user, compared with
`filter(company_name=request.user.company_name)`. Because public registration
accepted an arbitrary company name and auto-promoted the account to ADMIN,
anyone could type an existing customer's name at signup and take over their
tenant (audit V-01).

An organization is now a real row with a unique slug. It cannot be joined by
typing its name -- only created by its first signup, or joined by invitation.
"""

from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models, transaction
from django.utils.text import slugify


def normalize_slug(name: str) -> str:
    return slugify(name or "")[:100]


class Organization(models.Model):
    """One customer company. The unit of tenancy, billing and data isolation."""

    name = models.CharField(max_length=150, validators=[MinLengthValidator(2)])
    slug = models.SlugField(max_length=100, unique=True, db_index=True)

    #: IANA name. Attendance day boundaries are resolved in this zone rather than
    #: the server's local clock, which used to silently shift them (audit V-26).
    timezone = models.CharField(max_length=64, default="UTC")

    logo_url = models.URLField(max_length=500, blank=True, default="")

    # Folded in from the old CompanyConfig model, which keyed off the same string.
    departments = models.JSONField(default=list, blank=True)
    roles = models.JSONField(default=list, blank=True)
    employment_types = models.JSONField(default=list, blank=True)
    bypass_attendance = models.BooleanField(
        default=False,
        help_text="Pay a full month regardless of recorded attendance.",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_organizations",
    )

    #: Monotonic per-organization counter behind employee login ids. The previous
    #: generator used a global COUNT()+1, which leaked the platform-wide employee
    #: count into every customer's ids and collided under concurrency (audit V-11).
    employee_sequence = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = normalize_slug(self.name)
        super().save(*args, **kwargs)

    @transaction.atomic
    def next_employee_number(self) -> int:
        """Reserve the next employee number, safe against concurrent hires."""
        locked = Organization.objects.select_for_update().get(pk=self.pk)
        locked.employee_sequence += 1
        locked.save(update_fields=["employee_sequence", "updated_at"])
        self.employee_sequence = locked.employee_sequence
        return locked.employee_sequence

    @property
    def tzinfo(self):
        from zoneinfo import ZoneInfo

        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("UTC")

    def today(self):
        """The current date in this organization's timezone."""
        from django.utils import timezone as dj_timezone

        return dj_timezone.now().astimezone(self.tzinfo).date()
