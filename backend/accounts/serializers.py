from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from organizations.models import Organization, normalize_slug

from .models import CustomUser

RESERVED_SLUGS = frozenset(
    {"admin", "api", "app", "www", "dayflow", "support", "billing", "static", "help"}
)


class CompanySignupSerializer(serializers.Serializer):
    """Creates a brand new organization and its owner account.

    This endpoint used to accept an arbitrary `company_name` and unconditionally
    promote the caller to ADMIN of whatever tenant that string matched, which made
    every customer's data reachable by anyone who knew their company name
    (audit V-01). Signup now *creates* a tenant; it can never join one. Joining an
    existing organization happens only by invitation from its admin.
    """

    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    company_name = serializers.CharField(max_length=150, min_length=2)
    timezone = serializers.CharField(max_length=64, required=False, default="UTC")

    def validate_email(self, value):
        value = value.strip().lower()
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_timezone(self, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        value = (value or "UTC").strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, ModuleNotFoundError):
            raise serializers.ValidationError(f"'{value}' is not a known IANA timezone.")
        return value

    def validate_company_name(self, value):
        value = " ".join(value.split())
        slug = normalize_slug(value)
        if not slug:
            raise serializers.ValidationError(
                "Company name must contain at least one letter or number."
            )
        if slug in RESERVED_SLUGS:
            raise serializers.ValidationError("That company name is reserved.")
        if Organization.objects.filter(slug=slug).exists():
            # Deliberately does not confirm or deny anything about the existing
            # organization beyond the fact that the name is taken.
            raise serializers.ValidationError(
                "That company is already registered on DayFlow. "
                "Ask an administrator at your company to invite you."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        from .utils import generate_owner_login_id

        try:
            organization = Organization.objects.create(
                name=validated_data["company_name"],
                slug=normalize_slug(validated_data["company_name"]),
                timezone=validated_data.get("timezone", "UTC"),
            )
        except IntegrityError:
            # Lost a race with a concurrent signup for the same name.
            raise serializers.ValidationError(
                {"company_name": "That company is already registered on DayFlow."}
            )

        owner = CustomUser.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            login_id=generate_owner_login_id(organization),
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            organization=organization,
            role="ADMIN",
            is_staff=False,
            is_approved=True,
            must_change_password=False,
        )
        organization.owner = owner
        organization.save(update_fields=["owner", "updated_at"])

        # A trial is a real Subscription row, so `is_entitled` is the single
        # question asked everywhere -- no "have they paid yet?" special case.
        from billing.services import start_trial

        start_trial(organization)
        return owner


class EmployeeListSerializer(serializers.ModelSerializer):
    """The employee directory.

    `salary` is deliberately absent: it used to be returned to every ADMIN and HR
    user in the directory payload and written into the export spreadsheet
    (audit V-18). Compensation is served only by the payroll endpoints.
    """

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "login_id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "organization_name",
            "role",
            "date_of_joining",
            "department",
            "employment_type",
            "is_active",
            "is_approved",
        )
        read_only_fields = fields

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.login_id


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    """Company configuration. Replaces the old CompanyConfig + CompanyLogo pair."""

    departments = serializers.ListField(child=serializers.CharField(max_length=100), required=False)
    roles = serializers.ListField(child=serializers.CharField(max_length=20), required=False)
    employment_types = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False
    )

    class Meta:
        model = Organization
        fields = (
            "name",
            "slug",
            "timezone",
            "logo_url",
            "departments",
            "roles",
            "employment_types",
            "bypass_attendance",
            "updated_at",
        )
        read_only_fields = ("slug", "updated_at")

    def _normalize_list(self, values):
        cleaned, seen = [], set()
        for item in values or []:
            value = (item or "").strip()
            if not value or value.lower() in seen:
                continue
            seen.add(value.lower())
            cleaned.append(value)
        return cleaned

    def validate_departments(self, value):
        return self._normalize_list(value)

    def validate_employment_types(self, value):
        return self._normalize_list(value)

    def validate_logo_url(self, value):
        """Only absolute https URLs.

        This value was interpolated unescaped into an HTML attribute on the salary
        slip, so `" onerror="...` escaped the attribute without needing a script tag
        (audit V-09). The slip is a template now, but the field is still validated.
        """
        value = (value or "").strip()
        if value and not value.lower().startswith("https://"):
            raise serializers.ValidationError("Logo URL must be an absolute https:// URL.")
        return value

    def validate_timezone(self, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, ModuleNotFoundError):
            raise serializers.ValidationError(f"'{value}' is not a known IANA timezone.")
        return value

    def validate_roles(self, value):
        allowed = {"EMP": "EMP", "EMPLOYEE": "EMP", "INT": "INT", "INTERN": "INT", "HR": "HR"}
        codes = []
        for role in self._normalize_list(value):
            mapped = allowed.get(role.upper())
            if not mapped:
                raise serializers.ValidationError(
                    "Roles can only include EMP/Employee, INT/Intern, or HR."
                )
            if mapped not in codes:
                codes.append(mapped)
        return codes

    def validate(self, attrs):
        """Refuse changes that would orphan existing employees (audit V-25)."""
        org = self.instance
        if org is None:
            return attrs

        if "roles" in attrs:
            in_use = set(
                org.members.exclude(role="ADMIN")
                .filter(is_active=True)
                .values_list("role", flat=True)
            )
            removed = in_use - set(attrs["roles"])
            if removed:
                raise serializers.ValidationError(
                    {"roles": f"Still assigned to active employees: {', '.join(sorted(removed))}."}
                )

        if "departments" in attrs:
            in_use = {
                d
                for d in org.members.filter(is_active=True).values_list("department", flat=True)
                if d
            }
            kept = {d.lower() for d in attrs["departments"]}
            removed = {d for d in in_use if d.lower() not in kept}
            if removed:
                raise serializers.ValidationError(
                    {"departments": f"Still assigned to active employees: {', '.join(sorted(removed))}."}
                )

        return attrs
