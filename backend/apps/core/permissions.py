from rest_framework.permissions import BasePermission

from .models import Artifact, Document, Opportunity, Project, User


class RolePermission(BasePermission):
    """Coarse role policy; object ownership stays centralized in the API."""

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_admin_role:
            return True
        resource = getattr(view, "resource", "")
        if resource in {"service", "risk", "health"}:  # leitura para todos; escrita só admin
            return request.method in {"GET", "HEAD", "OPTIONS"}
        if request.user.role == User.Role.SALES:
            if resource in {"project", "project_phase", "project_deliverable", "digital_employee"}:
                return request.method in {"GET", "HEAD", "OPTIONS"}
            return resource in {"client", "contact", "opportunity", "document", "lead",
                                "analytics", "artifact"}
        if request.user.role == User.Role.DELIVERY:
            if resource in {"client", "contact"}:
                return request.method in {"GET", "HEAD", "OPTIONS"}
            if resource in {"project", "milestone", "task", "document", "dashboard",
                            "meeting", "pendencia", "project_phase", "project_deliverable",
                            "digital_employee", "artifact"}:
                return True
            return resource == "opportunity" and request.method in {"GET", "HEAD", "OPTIONS"}
        return False

    def has_object_permission(self, request, view, obj) -> bool:  # type: ignore[no-untyped-def]
        if request.user.is_admin_role:
            return True
        if request.user.role == User.Role.SALES:
            if isinstance(obj, Project):
                return request.method in {"GET", "HEAD", "OPTIONS"}
            return True
        if request.user.role == User.Role.DELIVERY:
            if getattr(view, "resource", "") in {"client", "contact"}:
                return request.method in {"GET", "HEAD", "OPTIONS"}
            if isinstance(obj, Opportunity):
                return obj.is_won and request.method in {"GET", "HEAD", "OPTIONS"}
            # As duas camadas precisam concordar: o queryset já esconde o que é comercial,
            # e aqui a permissão de objeto diz o mesmo, para um caminho novo não reabrir o
            # que o outro fechou. Ver FDD 017 / ADR 0009.
            if isinstance(obj, Document):
                return obj.project_id is not None
            if isinstance(obj, Artifact):
                return obj.project_id is not None
            return True
        return False
