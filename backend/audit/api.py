from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOrganizationOwner
from core.pagination import DefaultPagination
from organizations.scoping import organization_of

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListAPIView(APIView):
    """Read the organization's audit trail. Owner only."""

    permission_classes = [IsAuthenticated, IsOrganizationOwner]

    def get(self, request):
        queryset = AuditLog.objects.filter(organization=organization_of(request.user))

        action = request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action.upper())

        actor = request.query_params.get("actor")
        if actor:
            queryset = queryset.filter(actor_label__icontains=actor)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)
