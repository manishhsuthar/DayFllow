"""Convert the free-text `company_name` tenant key into real Organization rows.

Every distinct non-empty `company_name` becomes one Organization. Users are
linked to it, and the CompanyConfig / CompanyLogo rows that keyed off the same
string are folded into the organization's own fields.

Two cases need care:

* **Slug collisions.** "Acme Corp" and "Acme  Corp." both slugify to `acme-corp`.
  Those are almost certainly the same customer typed twice, so they merge into
  one organization rather than silently splitting a tenant in half.
* **Blank company names.** Superusers created with `createsuperuser` have none.
  They are left unlinked rather than being dropped into an arbitrary tenant;
  `organization` is nullable precisely so this migration never invents tenancy.

Reversible: the reverse pass restores `company_name` from the organization name.
"""

from django.db import migrations
from django.utils.text import slugify


def forwards(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    CompanyConfig = apps.get_model("accounts", "CompanyConfig")
    CompanyLogo = apps.get_model("accounts", "CompanyLogo")
    Organization = apps.get_model("organizations", "Organization")

    names = (
        CustomUser.objects.exclude(company_name="")
        .exclude(company_name=None)
        .values_list("company_name", flat=True)
        .distinct()
    )

    by_slug = {}
    for name in names:
        slug = slugify(name)[:100]
        if not slug:
            continue
        if slug not in by_slug:
            by_slug[slug] = Organization.objects.create(name=name.strip(), slug=slug)

    for name in names:
        slug = slugify(name)[:100]
        org = by_slug.get(slug)
        if not org:
            continue

        members = CustomUser.objects.filter(company_name=name)
        members.update(organization=org)

        # The earliest admin is the closest thing to an owner in the old schema.
        owner = members.filter(role="ADMIN").order_by("date_of_joining", "id").first()
        if owner and org.owner_id is None:
            org.owner_id = owner.id

        config = CompanyConfig.objects.filter(company_name=name).first()
        if config:
            org.departments = config.departments or org.departments
            org.roles = config.roles or org.roles
            org.employment_types = config.employment_types or org.employment_types
            org.bypass_attendance = org.bypass_attendance or config.bypass_attendance

        logo = CompanyLogo.objects.filter(company_name=name).first()
        if logo and not org.logo_url:
            org.logo_url = logo.logo_url

        # Start the per-organization employee counter past everyone already hired,
        # so newly generated login ids cannot collide with existing ones.
        org.employee_sequence = max(org.employee_sequence, members.count())
        org.save()


def backwards(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    for user in CustomUser.objects.exclude(organization=None).select_related("organization"):
        user.company_name = user.organization.name
        user.save(update_fields=["company_name"])
    CustomUser.objects.update(organization=None)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_customuser_organization"),
        ("organizations", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
