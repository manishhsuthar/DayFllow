"""Role-based permissions.

ADMIN and HR used to be interchangeable: every check in the codebase read
``role not in ["ADMIN", "HR"]``, so HR could set salaries, run payroll, credit
payments, edit company configuration -- and delete the company owner, which under
the old hard-delete also destroyed their payroll history (audit V-16, V-17).

The matrix below separates "may manage people" from "may move money" and from
"may change how the company works".
"""

from rest_framework.permissions import BasePermission

#: Roles that may see other people's records at all.
MANAGEMENT_ROLES = frozenset({"ADMIN", "HR"})

#: Roles reserved to the organization owner.
OWNER_ROLES = frozenset({"ADMIN"})


def is_management(user) -> bool:
    return getattr(user, "role", None) in MANAGEMENT_ROLES


def is_owner(user) -> bool:
    return getattr(user, "role", None) in OWNER_ROLES


def can_manage_target(actor, target) -> bool:
    """Whether `actor` may read or modify `target`'s employee record.

    Enforces two rules the old code missed:
      * you cannot act on someone in another organization;
      * HR cannot act on an ADMIN -- previously HR simply omitted the
        `scope=non_admin` query parameter and received the owner's row anyway.
    """
    if actor.organization_id is None or actor.organization_id != target.organization_id:
        return False
    if not is_management(actor):
        return False
    if target.role == "ADMIN" and not is_owner(actor):
        return False
    return True


class IsManagement(BasePermission):
    """ADMIN or HR."""

    message = "This action requires an administrator or HR account."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_management(request.user))


class IsOrganizationOwner(BasePermission):
    """ADMIN only. Destructive, financial and configuration actions."""

    message = "This action requires an organization administrator account."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_owner(request.user))
