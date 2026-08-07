from typing import Any

from rest_framework.permissions import BasePermission

from .models import (
    Artifact,
    Case,
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
    can_access_project,
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Catálogos globais: leitura para todo autenticado, escrita só de admin. Não são de projeto e por
# isso não entram em `PROJECT_OF` — o objeto não pendura em lugar nenhum, é config da casa.
# `blueprint` cobre o bloco e a variante dele, como `journey` cobre a fase e o entregável.
CATALOG = {"service", "vertical", "blueprint"}

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
    # O case é prova social, mas nasce de um projeto e herda a fronteira dele: a Entrega lê o case
    # dos projetos de que participa e não a vitrine inteira da casa (ADR 0010, FDD 027).
    Case: lambda obj: obj.project,
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
        if resource in CATALOG:
            return request.method in SAFE_METHODS
        if request.user.role == User.Role.SALES:
            # `case` só-leitura para Vendas: quem mais usa o case é o comercial, e ainda assim
            # revisar, consentir e publicar são atos de admin — é ele que carrega a
            # responsabilidade pelo que a casa afirma sobre um cliente (FDD 027).
            # `invoice` só-leitura para Vendas (FDD 028): quem acompanha o recebível do próprio
            # cliente é o comercial, mas emitir, baixar e cancelar são atos de admin — é dinheiro,
            # e a responsabilidade por afirmar que ele entrou não se delega.
            if resource in {"project", "project_phase", "project_deliverable",
                            "digital_employee", "project_member", "risk", "health", "case",
                            "invoice"}:
                return request.method in SAFE_METHODS
            return resource in {"client", "contact", "opportunity", "document", "lead",
                                "analytics", "artifact"}
        if request.user.role == User.Role.DELIVERY:
            if resource in {"client", "contact", "opportunity", "project_member",
                            "risk", "health", "case"}:
                return request.method in SAFE_METHODS
            # Projeto não nasce nem morre pela mão da Entrega: vem da conversão comercial ou
            # do admin. Editar o que é seu, sim — e o objeto abaixo decide qual é o seu.
            # O corte é por *ação*, não por método: as ações de detalhe (assistente, resumo,
            # próximos passos, avançar fase) também são POST e precisam continuar passando.
            if resource == "project":
                return getattr(view, "action", None) not in {"create", "destroy"}
            # `invoice` **não aparece em nenhum dos dois conjuntos**, e é assim que a FDD 028 pede:
            # a Entrega não alcança rota de fatura nenhuma, nem de leitura, nem em projeto de que
            # participa. Quem produz o 403 é o `return False` abaixo — o mesmo mecanismo que fecha
            # `lead` e `analytics`, e a melhor propriedade deste modelo de permissão: recurso novo
            # nasce fechado sem uma linha de código.
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
            # Catálogo global não é objeto de projeto e cairia no `return False` do fim — a Entrega
            # lia a lista e tomava 403 no detalhe. Já valia para `/services/{id}/` e só não
            # aparecia porque a tela de Serviços usa a listagem; com a Biblioteca (FDD 026) o
            # detalhe passa a ser caminho de verdade, porque é dela que sai a instanciação.
            if getattr(view, "resource", "") in CATALOG:
                return request.method in SAFE_METHODS
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
    return can_access_project(user, project)
