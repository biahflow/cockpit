"""Kickoff automático na conversão de oportunidade em projeto (RFC 0002, FDD 008).

Ao converter uma oportunidade ganha em projeto, semeamos um cronograma inicial
(marcos + tarefas de um template) dentro da transação e, após o commit, disparamos os
efeitos externos best-effort: pasta no Drive (se ligado), e-mail e notificação de kickoff.
Nada aqui bloqueia a conversão — os efeitos externos são tolerantes a falha.

Desde o DAP `dap-engagement-r3` há **dois** chamadores, e não um: a conversão de uma oportunidade
ganha e a criação direta a partir de um `Engagement` (`POST /engagements/{id}/create-project/`).
O cronograma é o mesmo nos dois; o que muda é a origem que o `finalize` anuncia.

Desde a ADR 0061 são **três**, e o terceiro não tem gente na frente: o cliente marca a sessão de
Discovery pelo link do convite e o projeto nasce dali. É por isso que `criar_projeto_do_mandato`
existe — o ato "nasce um projeto do mandato" é um só, e duas cópias dele divergiriam na primeira
vez que alguém mexesse numa.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.mail import send_mail
from django.db import transaction

from . import drive, notifications, whatsapp

# `Service` no topo, e não no corpo como `Milestone`/`Task`: `DEGRAUS_SEM_GRUPO_DE_WHATSAPP` é
# constante de módulo e precisa do enum na importação. Não fecha ciclo — `models` não importa
# este módulo, e o import local ali embaixo existe por causa de `discovery_booking`, não de
# `models`.
from .models import Service

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import Engagement, Project

# Cronograma padrão: cada marco tem um deslocamento em dias a partir do início e suas tarefas.
KICKOFF_TEMPLATE: list[dict] = [
    {"title": "Kickoff e alinhamento", "offset": 7,
     "tasks": ["Agendar reunião de kickoff", "Compartilhar plano de trabalho"]},
    {"title": "Descoberta e planejamento", "offset": 21,
     "tasks": ["Levantar requisitos", "Detalhar cronograma"]},
    {"title": "Execução", "offset": 60, "tasks": ["Iniciar entregas do escopo"]},
    {"title": "Encerramento", "offset": 90,
     "tasks": ["Revisar entregáveis", "Coletar feedback do cliente"]},
]

# Um cronograma por degrau da escada FDE: a Qualification Call dura dias e não merece os 90
# do PROVE. Projetos sem nível (ou de serviço avulso) caem no template padrão.
#
# Os textos carregam a metodologia (ADR 0030, `docs/metodologia-fde.md`), e há três lugares em
# que isso não é decoração:
#
# - o Discovery Sprint **termina em Executive Readout**, porque é lá que o custo do estado
#   atual e o ranking por Opportunity Score chegam ao cliente. Sprint pago sem readout é
#   trabalho feito que ninguém viu;
# - a Feasibility define a **meta antes** de rodar a amostra, e o PROVE registra baseline e
#   critérios **antes** de construir. Critério definido depois do resultado não é critério, é
#   narrativa — e é a regra que dá credibilidade ao método inteiro;
# - o gate de saída é tarefa explícita nos dois, com as saídas nomeadas — e são **vocabulários
#   diferentes** (ADR 0053): a Feasibility responde "a tecnologia consegue?" (GO / CONDITIONAL GO
#   / REDESIGN / NO-GO) e o PROVE responde "funcionou em produção controlada?" (SCALE / ITERATE /
#   STOP). O template do PROVE já dizia isso antes de a rota aceitar; desde a ADR 0053 as duas
#   coisas concordam. Gate que não vira item de trabalho é gate que não acontece.
#
# O template padrão continua genérico: serviço avulso não é PROVE.
#
# **Uma tarefa do Discovery Sprint tem nome de constante**, e é a única — porque é a única que outro
# módulo precisa reencontrar depois de semeada. Quando o cliente já marcou a sessão pelo link do
# convite (ADR 0061), a automação acabou de fazer o que ela pede, e `discovery_booking` a resolve
# junto com o projeto. Casar por string mágica lá seria acoplamento que quebra calado: alguém
# reescreve o texto do template, a tarefa passa a nascer pendente para sempre e nada fica vermelho.
TAREFA_DE_AGENDAR_O_DISCOVERY = "Agendar a sessão de discovery"

KICKOFF_TEMPLATES: dict[str, list[dict]] = {
    "qualification_call": [
        {"title": "Qualification Call", "offset": 3,
         "tasks": ["Realizar a call de qualificação (30–45 min)",
                   "Registrar o fit e o próximo passo (avançar para Discovery ou NO-GO)"]},
    ],
    "discovery_sprint": [
        {"title": "Discovery", "offset": 3,
         "tasks": [TAREFA_DE_AGENDAR_O_DISCOVERY, "Mapear o processo com o P-S-D-T-E-R",
                   "Registrar a transcrição da reunião"]},
        {"title": "Baseline e priorização", "offset": 5,
         "tasks": ["Apurar o custo do estado atual",
                   "Rotular os achados (fato / hipótese / desconhecido)",
                   "Calcular o Opportunity Score de cada processo"]},
        {"title": "Executive Readout", "offset": 7,
         "tasks": ["Apresentar o custo do estado atual e o ranking por Opportunity Score",
                   "Registrar o próximo passo recomendado (Feasibility ou PROVE)"]},
    ],
    "feasibility": [
        {"title": "Definição do teste", "offset": 5,
         "tasks": ["Definir a meta **antes** de rodar a amostra",
                   "Selecionar uma amostra real representativa"]},
        {"title": "Execução e classificação", "offset": 15,
         "tasks": ["Rodar a tecnologia contra a amostra",
                   "Classificar cada falha em E1–E5",
                   "Calcular o Ceiling de Input"]},
        {"title": "Decision gate", "offset": 21,
         "tasks": ["Avaliar o T.O.E. pelo elo mais fraco, não pela média",
                   "Registrar o gate (GO / CONDITIONAL GO / REDESIGN / NO-GO)"]},
    ],
    "prove": [
        {"title": "Charter e baseline", "offset": 7,
         "tasks": ["Registrar o baseline e os critérios de sucesso antes de construir",
                   "Definir a meta por KPI e o sentido (menor é melhor?)"]},
        {"title": "Construção", "offset": 30,
         "tasks": ["Construir o piloto", "Integrar com a operação"]},
        {"title": "Produção controlada", "offset": 60,
         "tasks": ["Rodar em produção controlada",
                   "Registrar ao menos 10 casos reais (abaixo disso o scorecard não decide)"]},
        {"title": "Decision gate", "offset": 90,
         "tasks": ["Preencher o scorecard (baseline · meta · medido)",
                   "Registrar a decisão SCALE / ITERATE / STOP",
                   "Coletar feedback do cliente"]},
    ],
    "scale": [
        {"title": "Plano de escala", "offset": 14,
         "tasks": ["Definir o escopo de expansão a partir do que o PROVE sustentou",
                   "Dimensionar operação e suporte"]},
        {"title": "Rollout", "offset": 60,
         "tasks": ["Colocar em produção plena", "Treinar a operação"]},
        {"title": "Captura de valor", "offset": 120,
         "tasks": ["Atualizar o Value Ledger do cliente",
                   "Registrar o caso na biblioteca (prova social para vender o próximo)"]},
    ],
    "transformation": [
        {"title": "Onboarding da parceria", "offset": 14,
         "tasks": ["Definir o ritmo da Monthly Transformation Review",
                   "Abrir o Opportunity Backlog da conta"]},
        {"title": "Primeira revisão mensal", "offset": 30,
         "tasks": ["Revisar o Value Ledger com o cliente",
                   "Priorizar a próxima oportunidade da conta"]},
    ],
}


def template_for(project: Project) -> list[dict]:
    """Escolhe o cronograma inicial pelo nível de produto do projeto."""
    tier = project.service.tier if project.service else ""
    return KICKOFF_TEMPLATES.get(tier, KICKOFF_TEMPLATE)


def seed_work_items(project: Project) -> tuple[int, int]:
    """Cria marcos e tarefas do template, com prazos limitados à janela do projeto."""
    from .models import Milestone, Task

    milestones = tasks = 0
    for spec in template_for(project):
        due = min(project.start_date + timedelta(days=spec["offset"]), project.due_date)
        milestone = Milestone.objects.create(
            project=project, title=spec["title"], owner=project.owner, due_date=due
        )
        milestones += 1
        for task_title in spec["tasks"]:
            Task.objects.create(
                project=project, title=task_title, owner=project.owner,
                due_date=due, milestone=milestone,
            )
            tasks += 1
    return milestones, tasks


def criar_projeto_do_mandato(engagement: Engagement, salvar: Callable[[], Project]) -> Project:
    """Faz nascer um projeto do mandato: trava, grava e semeia tudo o que vem junto.

    **Uma definição só do ato**, e é a razão de esta função existir. Dois caminhos criam projeto a
    partir de um `Engagement` — o botão (`POST /engagements/{id}/create-project/`) e a rota pública
    em que o cliente marca a sessão de Discovery (ADR 0061) —, e repetir o corpo da transação no
    segundo produziria duas definições que divergem na primeira manutenção: alguém acrescenta um
    passo de semeadura num lugar, e o projeto nascido pelo outro caminho sai incompleto sem nada
    ficar vermelho. Regressão:
    `tests/regression/test_a_rota_publica_e_o_botao_criam_o_projeto_igual.py`.

    O que fica **de fora**, de propósito: a validação de quem chamou (papel, mandato encerrado,
    degrau de aquisição, serializer) — porque ela é diferente nos dois — e o `finalize`, que é
    efeito externo e roda depois do commit, na mão de quem chamou.

    `salvar` é quem monta o projeto, e é parâmetro porque as duas origens montam de formas
    legítimas e diferentes: a action grava o que o `ProjectSerializer` validou, e a rota pública
    deriva tudo da sessão marcada, sem `request.user` nenhum. O que esta função garante é o que
    tem de valer nas duas: a trava, a ordem e a semeadura em volta.

    **A trava não é a mesma da conversão**, e a diferença é sutil (FDD 046, emenda de 02/09): lá o
    `select_for_update` sustenta um "converte uma vez só"; aqui não há o que impedir — um mandato
    origina vários projetos por desenho (ADR 0050). Ela existe porque `seed_work_items` **não** é
    idempotente: serializa duas requisições simultâneas para que o duplo clique produza dois
    pedidos em fila, e não dois cronogramas gravados um por cima do outro.
    """
    # Local, e não no topo: `discovery_booking` importa este módulo (ele lê
    # `TAREFA_DE_AGENDAR_O_DISCOVERY`), então o import no topo fecharia um ciclo. `invoices` vem
    # junto pela vizinhança, não por necessidade.
    from . import discovery_booking, invoices
    from .models import Engagement as EngagementModel

    with transaction.atomic():
        # O valor não interessa — o efeito é a linha do mandato ficar bloqueada até o fim da
        # transação, e é só disso que a serialização precisa.
        EngagementModel.objects.select_for_update().get(pk=engagement.pk)
        project = salvar()
        seed_work_items(project)
        # Depois de semear, porque é a tarefa semeada que ela resolve — e dentro da transação pela
        # mesma razão das faturas: é escrita no banco, não efeito externo. Sem isto o projeto nasce
        # dizendo "Próxima reunião: A agendar" com a sessão já marcada pelo cliente, e com a tarefa
        # de agendar pendente logo depois de a automação a ter feito.
        discovery_booking.registrar_sessao_no_projeto(project, engagement)
        # Dentro da transação pela razão da conversão: é escrita no banco, não efeito externo.
        # Devolve 0 quando o valor contratado é zero — o Design Partner recebe o degrau sem
        # cobrança —, e isso é o cronograma correto, não uma falha.
        invoices.seed_invoices(project)
    return project


# De onde o projeto veio, em uma oração — e é **parâmetro** desde que o mandato passou a originar
# projeto sozinho (DAP `dap-engagement-r3`, decisão D1). Cravada no texto, a frase afirmava uma
# venda que, no caminho novo, não existe: o Design Partner não passa por oportunidade nenhuma, e
# o e-mail do kickoff seria a primeira coisa que a casa diz ao dono do projeto sobre uma origem
# inventada. O default é o texto anterior, palavra por palavra, para a conversão não mudar.
ORIGEM_PADRAO = "a partir de uma oportunidade ganha"


# Os degraus que **não** ganham grupo de WhatsApp no kickoff (issue #110, decisão de 03/09/2026).
# Um lugar só: reexpressar o critério na chamada produziria a segunda definição do alcance, e as
# duas divergiriam na primeira vez que a escada mudasse.
#
# **Projeto sem serviço, ou com `tier` vazio, ganha grupo — e isso é o default, não esquecimento.**
# O único degrau excluído pela decisão foi a Qualification Call: uma conversa de trinta a quarenta
# e cinco minutos não precisa de canal dedicado. Serviço avulso é trabalho de entrega de verdade,
# e inverter este default "arrumando" o código seis meses depois tiraria o grupo justamente de
# quem o usaria.
DEGRAUS_SEM_GRUPO_DE_WHATSAPP = frozenset({Service.Tier.QUALIFICATION_CALL})


def _participantes_do_grupo(project: Project) -> list[str]:
    """Os contatos vivos da conta que têm telefone — quem entra no grupo do cliente.

    Arquivado não entra: `archive()` é como a casa demite um contato, e um contato arquivado num
    grupo de cliente é acesso que ninguém pretendeu conceder. A conta canônica é
    `engagement.account` — `Project.client` não existe desde a Fase 6.
    """
    return list(
        project.engagement.account.contacts.filter(archived_at__isnull=True)
        .exclude(phone="")
        .values_list("phone", flat=True)
    )


def abrir_grupo_de_whatsapp(project: Project) -> str:
    """Abre o grupo do cliente no WhatsApp e guarda a referência no projeto; devolve o convite.

    O que volta é o **link de convite** (`""` quando não há grupo), porque é o único pedaço da
    referência que se entrega a uma pessoa: o e-mail e a notificação do kickoff o levam quando ele
    existe, e não mencionam grupo nenhum quando não existe.

    A gravação é daqui porque `finalize` roda **depois** do commit da criação do projeto: não há
    transação aberta para carregar o campo junto, e ninguém salva o projeto por nós.
    """
    if not whatsapp.is_enabled():
        # Sai calado: `whatsapp.create_group` já registra a intenção quando a flag está desligada,
        # e repetir a linha aqui só dobraria o log de toda instalação sem WhatsApp.
        return ""
    tier = project.service.tier if project.service else ""
    if tier in DEGRAUS_SEM_GRUPO_DE_WHATSAPP:
        logger.info(
            "kickoff: projeto %s é do degrau '%s' e não ganha grupo de WhatsApp", project.pk, tier
        )
        return ""
    if project.whatsapp_group_id:
        # **A guarda que impede o erro caro.** `finalize` é best-effort e pode ser reexecutado (a
        # conversão que repete, o retry de quem opera); sem ela, a segunda execução cria o
        # **segundo grupo** com o mesmo cliente — que é literalmente o duplicado que a issue #111
        # nomeia. O link já conhecido volta: o grupo existe, e é ele que se entrega.
        logger.info("kickoff: projeto %s já tem grupo de WhatsApp", project.pk)
        return project.whatsapp_group_invite_url
    participantes = _participantes_do_grupo(project)
    if not participantes:
        # "Cala quando não sabe", o mesmo de `receives_billing`: sem nenhum telefone não há grupo
        # a criar, e um grupo só com a casa dentro seria um canal que o cliente nunca vê.
        logger.info(
            "kickoff: conta do projeto %s não tem contato com telefone; grupo não criado",
            project.pk,
        )
        return ""
    nome = f"{project.engagement.account.name} · {project.name}"
    result = whatsapp.create_group(nome, participantes)
    if result.status is not whatsapp.Delivery.DELIVERED:
        logger.warning(
            "kickoff: grupo de WhatsApp do projeto %s ficou em '%s' (%s)",
            project.pk, result.status.value, result.detail or "sem detalhe",
        )
        if result.status is whatsapp.Delivery.UNCERTAIN:
            # (a) `UNCERTAIN` é o único estado em que ninguém sabe se o cliente recebeu o grupo E o
            # produto decidiu não tentar de novo — a dívida que a ADR 0062 nomeou e que o primeiro
            # chamador (#110) não fechou. (b) Quando o status chega até aqui, a reconciliação da
            # ADR 0064 já rodou dentro de `whatsapp.create_group` e não resolveu — não há checagem
            # extra a fazer. (c) `REFUSED`/`UNAVAILABLE` não avisam: certeza de não-entrega não cria
            # grupo órfão, só `UNCERTAIN` cria (issue #117).
            notifications.notify(
                [project.owner], "whatsapp",
                f"A criação do grupo de WhatsApp do projeto '{project.name}' ficou incerta — pode "
                "haver um grupo criado sem referência. Confira a lista de grupos no WhatsApp antes "
                "de tentar de novo.",
                f"/projetos/{project.id}",
                project=project,
            )
        return ""
    project.whatsapp_group_id = result.group_id
    project.whatsapp_group_invite_url = result.invite_url
    project.save(
        update_fields=["whatsapp_group_id", "whatsapp_group_invite_url", "updated_at"]
    )
    logger.info(
        # Telefone em log é dado pessoal: quem identifica o suficiente são os quatro últimos
        # dígitos, e `whatsapp._mask` é a única definição desse corte.
        "kickoff: grupo de WhatsApp do projeto %s criado por %s com %s",
        project.pk, result.provider, ", ".join(whatsapp._mask(p) for p in participantes),
    )
    return result.invite_url


def _send_kickoff_email(project: Project, origem: str, convite_do_grupo: str = "") -> None:
    recipient = project.owner.email
    if not recipient:
        return
    # A linha do grupo só existe quando o grupo existe. "Grupo: —" seria pior do que o silêncio:
    # anuncia um canal e não entrega nenhum. Parametrizado pela razão de `origem`.
    grupo = f"\nGrupo do cliente no WhatsApp: {convite_do_grupo}\n" if convite_do_grupo else ""
    send_mail(
        f"Kickoff do projeto {project.name}",
        f"O projeto '{project.name}' foi criado {origem}.\n\n"
        f"Cliente: {project.engagement.account.name}\n"
        f"Período: {project.start_date} a {project.due_date}\n"
        f"{grupo}\n"
        f"Um cronograma inicial de marcos e tarefas já foi criado para revisão.",
        None,
        [recipient],
        fail_silently=True,
    )


def finalize(project: Project, origem: str = ORIGEM_PADRAO) -> None:
    """Efeitos externos best-effort do kickoff (executar após o commit da criação do projeto).

    `origem` é a oração que diz de onde o projeto nasceu, e ela chega dos dois chamadores porque
    são duas origens de verdade — a conversão de uma oportunidade ganha e a criação direta a
    partir do mandato. Uma frase só serve às duas mensagens (e-mail e notificação) de propósito:
    duas variantes do mesmo fato divergiriam na primeira edição.

    O grupo do cliente no WhatsApp entra **antes** do e-mail, e a ordem é o requisito: é o e-mail
    que entrega o convite, e ele não pode sair antes de o link existir.
    """
    try:
        drive.ensure_project_folder(project)
    except Exception:  # noqa: BLE001 - best-effort: o kickoff não falha porque o Drive caiu
        # Best-effort é a decisão certa; o `pass` mudo é que não era. Sem log, o projeto ficava
        # **sem pasta e ninguém sabendo** — e a pasta é onde a entrega guarda tudo depois.
        logger.exception("kickoff: pasta do Drive não criada para o projeto %s", project.pk)
    convite_do_grupo = ""
    try:
        convite_do_grupo = abrir_grupo_de_whatsapp(project)
    except Exception:  # noqa: BLE001 - best-effort: o kickoff não falha porque o WhatsApp caiu
        # Mesmo desenho do Drive acima, e pela mesma razão de não ser `pass`: sem log, o projeto
        # nasceria sem canal com o cliente e ninguém saberia por quê.
        logger.exception("kickoff: grupo de WhatsApp não criado para o projeto %s", project.pk)
    _send_kickoff_email(project, origem, convite_do_grupo)
    grupo = f" Grupo do cliente no WhatsApp: {convite_do_grupo}" if convite_do_grupo else ""
    notifications.notify(
        [project.owner], "kickoff",
        f"Projeto '{project.name}' criado {origem}.{grupo}",
        f"/projetos/{project.id}",
        # No-op aqui pelo invariante `_owner_is_always_a_member`, mas a regra é "URL de projeto ⇒
        # guarda": exceção que depende de um invariante alheio é o que apodrece primeiro.
        project=project,
    )
