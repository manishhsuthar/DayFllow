"""Helpers for keeping every query inside one tenant.

The audit found the same shape of bug repeated across five apps: a queryset that
either forgot its tenant filter or applied it inconsistently. These helpers exist
so tenant scoping is one call that is hard to get wrong, rather than a
`filter(company_name=...)` clause copy-pasted into every view.
"""

from rest_framework.exceptions import PermissionDenied


def organization_of(user):
    """The caller's organization, or 403.

    A user with no organization is a platform superuser created by
    `createsuperuser`, or an account left over from before the tenancy
    migration. Either way they have no tenant data to see, and must not fall
    through to an unscoped queryset.
    """
    org = getattr(user, "organization", None)
    if org is None:
        raise PermissionDenied(
            "This account is not linked to an organization. "
            "Sign in with a company account, or ask an administrator to invite you."
        )
    return org


def scope_to_organization(queryset, user, path="organization"):
    """Restrict `queryset` to the caller's organization.

    `path` is the ORM lookup that reaches Organization from this model, e.g.
    "organization" on CustomUser, "user__organization" on Attendance,
    "employee__organization" on PayrollRecord.
    """
    return queryset.filter(**{path: organization_of(user)})
