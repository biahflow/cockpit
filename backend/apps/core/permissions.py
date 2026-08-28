from typing import Any

from rest_framework.permissions import BasePermission

from .models import (
    Artifact,
    Case,
    Decisao,
    DigitalEmployee,
    Document,
    EngineeringHandoff,
    Evidencia,
    GithubDeliveryProjection,
    Meeting,
    Milestone,
    Opportunity,
    Pendencia,
    Processo,
    ProcessoEtapa,
    Project,
    ProjectChecklistItem,
    ProjectDeliverable,
    ProjectMember,
    ProjectPhase,
    Risco,
    Satisfacao,
    Task,
    User,
    can_access_project,
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Catálogos globais: leitura para todo autenticado, escrita só de admin. Não são de projeto e por
# isso não entram em `PROJECT_OF` — o objeto não pendura em lugar nenhum, é config da casa.
# `blueprint` cobre o bloco e a variante dele, como `journey` cobre a fase e o entregável.
CATALOG = {"service", "vertical", "blueprint", "knowledge_area"}

# Recursos que vivem dentro de um projeto: a permissão de objeto deles é uma pergunta só —
# a pessoa participa do projeto? O caminho até o projeto varia por modelo.
PROJECT_OF = {
    Project: lambda obj: obj,
    Milestone: lambda obj: obj.project,
    Task: lambda obj: obj.project,
    Meeting: lambda obj: obj.project,
    Pendencia: lambda obj: obj.project,
    Decisao: lambda obj: obj.project,
    Risco: lambda obj: obj.project,
    DigitalEmployee: lambda obj: obj.project,
    ProjectPhase: lambda obj: obj.project,
    ProjectDeliverable: lambda obj: obj.project_phase.project,
    ProjectChecklistItem: lambda obj: obj.project_phase.project,
    ProjectMember: lambda obj: obj.project,
    Document: lambda obj: obj.project,
    Artifact: lambda obj: obj.project,
    EngineeringHandoff: lambda obj: obj.project,
    GithubDeliveryProjection: lambda obj: obj.project,
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
            # `cobranca` só-leitura ao lado de `invoice`, e pela mesma razão (FDD 036): o comercial
            # acompanha o que a casa disse ao cliente dele, mas mandar cobrança é ato de admin.
            # As rotas de rascunhar e enviar ficam na `InvoiceViewSet`, e por isso já caem no
            # `invoice` acima — o 403 de Vendas no envio vem de graça, sem regra nova.
            if resource in {"project", "project_phase", "project_deliverable",
                            "project_checklist_item", "digital_employee", "project_member",
                            "risk", "health", "case", "invoice", "cobranca"}:
                return request.method in SAFE_METHODS
            if resource == "knowledge":
                return request.method in SAFE_METHODS or getattr(view, "action", None) == "verify"
            # `cobranca_suspensao` é o único recurso financeiro em que Vendas **escreve**, e a
            # assimetria é deliberada: suspender é decisão de relação, e quem a carrega é quem
            # responde pelo cliente. Emitir, baixar e cobrar seguem de admin, porque são dinheiro.
            # `satisfacao` é escrita pelos **dois** papéis (FDD 037), e é a diferença dela para
            # os dois vizinhos: `risco` é só de Entrega e `activity` é escrita por Vendas e só
            # lida por Entrega. Quem conversa com o cliente é de ambas as áreas, e um registro
            # que só metade da casa pode fazer é um registro que não acontece.
            # `processo`, `processo_etapa` e `evidencia` (FDD 039) são escritos pelos **dois**
            # papéis, pelo argumento que a FDD 037 usou para `satisfacao` logo acima: quem conduz
            # Discovery é de ambas as áreas — o comercial levanta a operação na venda, a entrega
            # continua levantando dentro do projeto —, e um registro que só metade da casa pode
            # fazer é um registro que não acontece.
            # `qualification` (ADR 0049) entra ao lado de `lead`, e **não** aparece em
            # nenhum conjunto da Entrega logo abaixo: a avaliação é ato comercial e não
            # atravessa para o portal do cliente (mapa de linguagem §3). O 403 dela vem do
            # `return False` do fim, sem regra nova — recurso novo nasce fechado.
            return resource in {"client", "contact", "opportunity", "document", "lead",
                                "analytics", "artifact", "activity", "cobranca_suspensao",
                                "satisfacao", "processo", "processo_etapa", "evidencia",
                                "qualification"}
        if request.user.role == User.Role.DELIVERY:
            if resource in {"client", "contact", "opportunity", "project_member",
                            "risk", "health", "case", "activity"}:
                return request.method in SAFE_METHODS
            # Conhecimento: **todo mundo lê**, e o dono da área verifica. O dono pode ser de
            # qualquer papel, e avisá-lo sobre uma peça que ele não consegue abrir — ou não pode
            # marcar como conferida — seria um laço quebrado (FDD 029). Quem barra o não-dono é a
            # própria ação, que confere a área.
            if resource == "knowledge":
                return request.method in SAFE_METHODS or getattr(view, "action", None) == "verify"
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
            # `cobranca` e `cobranca_suspensao` (FDD 036) seguem a fatura e também **não aparecem
            # em nenhum dos dois conjuntos**: quem não alcança o recebível não alcança o que a casa
            # disse sobre ele. É o mesmo `return False` abaixo, e é a melhor propriedade deste
            # modelo de permissão — recurso novo nasce fechado sem uma linha de código.
            # `risco` (o registro declarado da FDD 034) entra aqui, ao lado de `pendencia`, e
            # **não** se confunde com `risk` lá em cima: aquele é a avaliação calculada, só de
            # leitura para quem não é admin. Nomes vizinhos, recursos diferentes.
            # Os três recursos do Discovery estruturado (FDD 039) entram aqui pelo mesmo motivo
            # que estão no conjunto de Vendas: o levantamento é feito pelas duas áreas. O objeto
            # abaixo decide qual cliente é o seu, e a âncora é o cliente — não o projeto.
            return resource in {"milestone", "task", "document", "dashboard", "meeting",
                                "pendencia", "decisao", "risco", "project_phase",
                                "project_deliverable", "project_checklist_item",
                                "digital_employee", "artifact", "satisfacao",
                                "processo", "processo_etapa", "evidencia",
                                "engineering_handoff", "github_projection"}
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
            if getattr(view, "resource", "") in {"client", "contact", "activity"}:
                return request.method in SAFE_METHODS
            # Conhecimento não é objeto de projeto e cairia no `return False` do fim — a Entrega
            # leria a lista e tomaria 403 no detalhe e no `verify`. É exatamente o defeito que a
            # FDD 026 achou no catálogo, agora previsto em vez de descoberto: o dono de uma área
            # pode ser da Entrega, e é dele que se espera o ato de verificar.
            if getattr(view, "resource", "") == "knowledge":
                return request.method in SAFE_METHODS or getattr(view, "action", None) == "verify"
            if isinstance(obj, Satisfacao):
                # **Não entra em `PROJECT_OF`**, e não por esquecimento: o `project` aqui é
                # opcional, e um mapa que resolvesse `obj.project` devolveria `None` para o
                # registro de cliente sem projeto — a Entrega tomaria 403 no detalhe de um
                # registro que a listagem dela mostra. A pergunta certa é a do cliente, e ela sai
                # de `visible_to`, a única expressão da regra (ADR 0010), nunca reescrita à mão.
                return Project.objects.visible_to(request.user).filter(client=obj.client).exists()
            if isinstance(obj, Processo | ProcessoEtapa | Evidencia):
                # Mesma pergunta da `Satisfacao` acima, e **também fora de `PROJECT_OF`** — aqui
                # não por o projeto ser opcional, mas por não existir: o processo mapeado é do
                # cliente e sobrevive à venda que o descobriu (FDD 039). A etapa e a evidência
                # chegam ao cliente pelo processo pai, que é o mesmo caminho da queryset delas.
                client = obj.client if isinstance(obj, Processo) else obj.processo.client
                return Project.objects.visible_to(request.user).filter(client=client).exists()
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
