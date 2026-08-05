from typing import Any

from rest_framework.permissions import BasePermission

from .models import (
    Artifact,
    DigitalEmployee,
    Document,
    Meeting,
    Milestone,
    Opportunity,
    Pendencia,
    Project,
    ProjectDeliverable,
    ProjectMember,
    ProjectPhase,
    Task,
    User,
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Recursos que vivem dentro de um projeto: a permissão de objeto deles é uma pergunta só —
# a pessoa participa do projeto? O caminho até o projeto varia por modelo.
PROJECT_OF = {
    Project: lambda obj: obj,
    Milestone: lambda obj: obj.project,
    Task: lambda obj: obj.project,
    Meeting: lambda obj: obj.project,
    Pendencia: lambda obj: obj.project,
    DigitalEmployee: lambda obj: obj.project,
    ProjectPhase: lambda obj: obj.project,
    ProjectDeliverable: lambda obj: obj.project_phase.project,
    ProjectMember: lambda obj: obj.project,
    Document: lambda obj: obj.project,
    Artifact: lambda obj: obj.project,
}


class RolePermission(BasePermission):
    """Política grossa por papel; o pertencimento ao projeto decide o objeto.

    Entrega vê e escreve apenas dentro dos projetos de que participa (RFC 0003, ADR 0010).
    A camada de objeto abaixo **nega por padrão**: um recurso novo nasce fechado, em vez de
    herdar um `return True` que ninguém lembra de apertar depois.
    """

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_admin_role:
            return True
        resource = getattr(view, "resource", "")
        if resource == "service":  # catálogo: leitura para todos, escrita só admin
            return request.method in SAFE_METHODS
        if request.user.role == User.Role.SALES:
            if resource in {"project", "project_phase", "project_deliverable",
                            "digital_employee", "project_member", "risk", "health"}:
                return request.method in SAFE_METHODS
            return resource in {"client", "contact", "opportunity", "document", "lead",
                                "analytics", "artifact"}
        if request.user.role == User.Role.DELIVERY:
            if resource in {"client", "contact", "opportunity", "project_member",
                            "risk", "health"}:
                return request.method in SAFE_METHODS
            # Projeto não nasce nem morre pela mão da Entrega: vem da conversão comercial ou
            # do admin. Editar o que é seu, sim — e o objeto abaixo decide qual é o seu.
            # O corte é por *ação*, não por método: as ações de detalhe (assistente, resumo,
            # próximos passos, avançar fase) também são POST e precisam continuar passando.
            if resource == "project":
                return getattr(view, "action", None) not in {"create", "destroy"}
            return resource in {"milestone", "task", "document", "dashboard", "meeting",
                                "pendencia", "project_phase", "project_deliverable",
                                "digital_employee", "artifact"}
        return False

    def has_object_permission(self, request, view, obj) -> bool:  # type: ignore[no-untyped-def]
        if request.user.is_admin_role:
            return True
        if request.user.role == User.Role.SALES:
            if isinstance(obj, Project):
                return request.method in SAFE_METHODS
            return True
        if request.user.role == User.Role.DELIVERY:
            if getattr(view, "resource", "") in {"client", "contact"}:
                return request.method in SAFE_METHODS
            if isinstance(obj, Opportunity):
                return obj.is_won and request.method in SAFE_METHODS
            if isinstance(obj, ProjectMember):
                # Ler a equipe do próprio projeto, sim; montá-la é do admin.
                return request.method in SAFE_METHODS and _participates(request.user, obj)
            if type(obj) in PROJECT_OF:
                return _participates(request.user, obj)
            return False
        return False


def _participates(user: User, obj: Any) -> bool:
    """A mesma pergunta do queryset, agora sobre um objeto já carregado."""
    project = PROJECT_OF[type(obj)](obj)
    if project is None:  # documento/artefato de cliente ou oportunidade
        return False
    return Project.objects.visible_to(user).filter(pk=project.pk).exists()
