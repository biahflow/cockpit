"""Health Score do projeto — a saúde da relação, explicável e sem ML.

É o inverso do risco de atraso (`risk.py`): aqui **100 = saudável** e cada sinal ruim
**subtrai** pontos, para a equipe saber onde agir antes de o cliente reclamar. Cada sinal
traz seu peso (quanto tirou), preservando a explicabilidade.

Só usa sinais com dado real no domínio: entregas atrasadas/fora do prazo, reuniões não
realizadas, decisões pendentes (pesa mais quando o cliente é quem trava), ROI negativo e
insatisfação **declarada** do cliente (FDD 037). Bugs e "acessos liberados" ficam de fora até
existir onde registrá-los.

Os cinco primeiros medem o **nosso** trabalho; o sexto é o único que depende de o cliente ter
dito alguma coisa — e por isso ele lê só `fonte=declared`. Ver `assess_project_health`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from typing import TYPE_CHECKING, Any

from . import satisfacao as satisfacao_module

if TYPE_CHECKING:
    from .models import Milestone, Pendencia, Project, SatisfactionRecord, Task

#: Os três níveis, **do pior para o melhor**. Constantes e não literais porque o nível atravessa
#: para fora daqui: a régua de cobrança troca de escada quando encontra `CRITICAL` (FDD 038) e o
#: painel mostra o pior nível do cliente. Um `"crítico"` digitado do outro lado seria uma segunda
#: definição do vocabulário — e a que erra o acento não fica vermelha, ela só nunca casa.
LEVELS_WORST_FIRST = ("crítico", "atenção", "saudável")
CRITICAL = LEVELS_WORST_FIRST[0]


def _level(score: int) -> str:
    if score >= 75:
        return LEVELS_WORST_FIRST[2]
    if score >= 50:
        return LEVELS_WORST_FIRST[1]
    return CRITICAL


def worst_level(levels: Iterable[str]) -> str | None:
    """O pior nível de um conjunto, ou `None` quando o conjunto é vazio.

    Mora aqui, e não em quem pergunta, porque a ordem entre os níveis é parte da definição deles.
    Quem tem dois projetos, um crítico e um saudável, não tem "meia saúde": tem um projeto em
    frangalhos — e uma tela que mostrasse o saudável estaria contradizendo a régua, que já reagiu
    ao crítico.
    """
    presentes = set(levels)
    return next((level for level in LEVELS_WORST_FIRST if level in presentes), None)


def assess_project_health(
    project: Project,
    *,
    milestones: Sequence[Milestone] | None = None,
    tasks: Sequence[Task] | None = None,
    missed_meetings: int | None = None,
    open_pendencias: Sequence[Pendencia] | None = None,
    satisfacoes: Sequence[SatisfactionRecord] | None = None,
) -> dict[str, Any]:
    """Avalia a saúde de um projeto. Os argumentos nomeados aceitam dado já carregado.

    Omitidos, a função consulta o banco — cinco queries, irrelevantes no detalhe de um
    projeto. Quem avalia uma lista usa `assess_projects_health` (FDD 022).

    `satisfacoes` é **sequência, e não `SatisfactionRecord | None`**, ao contrário do que a forma
    do argumento sugeriria para um sinal que é no máximo um registro. Aqui `None` já significa
    "consulte o banco", como nos outros quatro; se o tipo fosse o registro, "não há satisfação
    registrada" e "consulte o banco" seriam o mesmo valor, e o lote não teria como dizer o
    primeiro. `[]` diz "nenhuma" sem ambiguidade.
    """
    from .models import Meeting, Milestone, Pendencia, SatisfactionRecord, Task, WorkItem

    today = date.today()
    signals: list[dict[str, Any]] = []
    score = 100

    if milestones is None:
        milestones = list(Milestone.objects.filter(project=project, archived_at__isnull=True))
    if tasks is None:
        tasks = list(Task.objects.filter(project=project, archived_at__isnull=True))
    items: list[Any] = [*milestones, *tasks]
    overdue = [item for item in items if item.is_overdue]
    if overdue:
        weight = min(30, len(overdue) * 8)
        score -= weight
        signals.append({"label": "Entregas atrasadas", "detail": f"{len(overdue)} item(ns) vencido(s)", "weight": weight})

    late_done = [
        item for item in items if item.completed_at and item.completed_at.date() > item.due_date
    ]
    if late_done:
        weight = min(12, len(late_done) * 3)
        score -= weight
        signals.append({"label": "Entregues fora do prazo", "detail": f"{len(late_done)} item(ns) concluído(s) com atraso", "weight": weight})

    missed = missed_meetings
    if missed is None:
        missed = Meeting.objects.filter(
            project=project, archived_at__isnull=True,
            status=Meeting.Status.SCHEDULED, date__lt=today,
        ).count()
    if missed:
        weight = min(20, missed * 10)
        score -= weight
        signals.append({"label": "Reuniões não realizadas", "detail": f"{missed} reunião(ões) agendada(s) e vencida(s)", "weight": weight})

    if open_pendencias is None:
        open_pendencias = list(
            Pendencia.objects.filter(
                project=project, archived_at__isnull=True, status=Pendencia.Status.OPEN
            )
        )
    if open_pendencias:
        blocking_client = sum(1 for pendencia in open_pendencias if pendencia.party == WorkItem.Party.CLIENT)
        weight = min(25, len(open_pendencias) * 5 + blocking_client * 3)
        score -= weight
        detail = f"{len(open_pendencias)} em aberto"
        if blocking_client:
            detail += f" · {blocking_client} aguardando o cliente"
        signals.append({"label": "Decisões pendentes", "detail": detail, "weight": weight})

    if project.cost and (project.actual_value - project.cost) < 0:
        weight = 15
        score -= weight
        signals.append({"label": "ROI negativo", "detail": "custo acima do valor entregue até aqui", "weight": weight})

    # O sexto sinal, e o único que não mede o nosso próprio trabalho (FDD 037, ADR 0032).
    #
    # **Só a fonte `declarada` subtrai.** A `percebida` — a leitura de quem entrega — aparece na
    # tela e no contexto do agente, e não move número nenhum. Sem essa separação, o sinal do
    # cliente vira a opinião do time sobre si mesmo com aparência de medição: o escore passaria a
    # descontar 20 pontos por palpite, e um número errado é consultado com a mesma confiança de um
    # número certo. É a decisão central da fatia, e tem regressão dedicada.
    #
    # Só o nível `insatisfeito` pesa. Promotor **não soma**: o escore parte de 100 e só subtrai, e
    # um sinal que somasse faria "100" deixar de significar "nenhum problema conhecido" — os cinco
    # sinais acima teriam de ser reescritos para conviver com isso.
    if satisfacoes is None:
        account_id = project.engagement.account_id
        satisfacoes = satisfacao_module.registros_vigentes_por_cliente(
            [account_id], today
        ).get(account_id, [])
    insatisfacao = satisfacao_module.vigente(
        satisfacoes, today, fonte=SatisfactionRecord.Fonte.DECLARED
    )
    if insatisfacao is not None and insatisfacao.nivel == SatisfactionRecord.Nivel.DISSATISFIED:
        weight = 20
        score -= weight
        signals.append({
            "label": "Cliente insatisfeito",
            "detail": f"declarada em {insatisfacao.happened_on.strftime('%d/%m/%Y')}",
            "weight": weight,
        })

    score = max(0, min(score, 100))
    return {
        "project_id": project.pk,
        "name": project.name,
        "score": score,
        "level": _level(score),
        "signals": signals,
    }


def assess_projects_health(projects: Iterable[Project]) -> list[dict[str, Any]]:
    """Avalia a saúde de uma lista com um número **constante** de queries.

    São cinco modelos por projeto (marco, tarefa, reunião perdida, pendência aberta e satisfação
    do cliente): a versão projeto a projeto custava a `/health/` e à visão multi-cliente cinco
    queries por projeto da casa. Aqui são cinco no total, distribuídas em memória (FDD 022).

    A quinta entrou com a FDD 037 e é **por cliente**, não por projeto: dois projetos do mesmo
    cliente leem o mesmo registro, porque a satisfação é da relação e não da entrega.
    """
    from .models import Meeting, Milestone, Pendencia, Task

    items = list(projects)
    if not items:
        return []
    today = date.today()
    ids = [project.pk for project in items]

    milestones: dict[int, list[Milestone]] = defaultdict(list)
    for milestone in Milestone.objects.filter(project_id__in=ids, archived_at__isnull=True):
        milestones[milestone.project_id].append(milestone)
    tasks: dict[int, list[Task]] = defaultdict(list)
    for task in Task.objects.filter(project_id__in=ids, archived_at__isnull=True):
        tasks[task.project_id].append(task)
    missed: dict[int, int] = defaultdict(int)
    for project_id in Meeting.objects.filter(
        project_id__in=ids, archived_at__isnull=True,
        status=Meeting.Status.SCHEDULED, date__lt=today,
    ).values_list("project_id", flat=True):
        missed[project_id] += 1
    pendencias: dict[int, list[Pendencia]] = defaultdict(list)
    for pendencia in Pendencia.objects.filter(
        project_id__in=ids, archived_at__isnull=True, status=Pendencia.Status.OPEN
    ):
        pendencias[pendencia.project_id].append(pendencia)
    satisfacoes = satisfacao_module.registros_vigentes_por_cliente(
        {project.engagement.account_id for project in items}, today
    )

    return [
        assess_project_health(
            project,
            milestones=milestones[project.pk],
            tasks=tasks[project.pk],
            missed_meetings=missed[project.pk],
            open_pendencias=pendencias[project.pk],
            # `[]` e não `None`: cliente sem registro tem "nenhuma satisfação", não "vá ao banco
            # descobrir" — e é essa distinção que mantém a contagem de queries constante.
            satisfacoes=satisfacoes.get(project.engagement.account_id, []),
        )
        for project in items
    ]
