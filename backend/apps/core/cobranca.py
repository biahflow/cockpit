"""A régua de cobrança: que degrau cabe hoje (FDD 036, camada 3 da RFC 0004).

Módulo de funções puras mais um orquestrador, espelhando `invoices.py` — e pela mesma razão: a
regra de dinheiro mora aqui, não na view. O job periódico e a ação humana da tela chamam **as
mesmas funções**, e é isso que faz "a casa só cobra por caminho conhecido" ser verdade em vez de
disciplina.

**A propriedade central: a régua é derivada do estado, nunca uma fila** (ADR 0031). Não existe
mensagem agendada. A cada execução, o job olha o estado **atual** da fatura e pergunta que degrau
cabe hoje. `paid` e `cancelled` são terminais no `INVOICE_TRANSITIONS` (FDD 028) e não têm degrau
— então **o pagamento não precisa cancelar nada**, porque não há nada pendente para cancelar. Uma
fila pode ser ultrapassada pelo pagamento: a baixa entra às 14h, o worker já tinha o e-mail na
mão, e quem pagou de manhã é cobrado à tarde. Isto não tem esse modo de falha, e não o tem por
construção. Quem "otimizar" este módulo para uma tabela de mensagens agendadas reintroduz o
defeito inteiro.

`DunningContact` é só o registro do que **já saiu**, e é dele que vem a idempotência do degrau —
via `UniqueConstraint(invoice, dunning_step)`, no banco, e não via guarda em Python.

O que este módulo deliberadamente **não** faz: decidir. Dar desconto, baixar, renegociar, escalar
e suspender seguem sendo atos humanos (RFC 0004 "Segurança", ADR 0006). O que sai daqui sozinho é
o degrau determinístico, cujo texto é constante revisada em código; o rascunho de IA é pedido na
tela e enviado por gente (ADR 0031).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from . import flags
from . import satisfaction as satisfaction_module
from .dinheiro import dinheiro

if TYPE_CHECKING:
    from .models import (
        Account,
        Activity,
        AiInteraction,
        CobrancaSuspensao,
        Contact,
        DunningContact,
        Invoice,
        SatisfactionRecord,
        User,
    )

logger = logging.getLogger(__name__)

CLIENTE = "cliente"
INTERNO = "interno"


@dataclass(frozen=True)
class DunningStep:
    """Um degrau da escada: quando cabe, para quem vai e o que diz.

    **A `key` é o valor persistido em `DunningContact.dunning_step`**, e as duas metades
    atravessaram juntas na fatia 5.4 da issue #122 (D10): traduzir a coluna sem traduzir estas
    chaves — ou o contrário — faria a régua parar de casar com o banco em silêncio, e o sintoma
    seria um degrau saindo duas vezes por a idempotência nunca mais encontrar o que já foi gasto.

    `de`/`ate` são a **janela em dias** relativa ao vencimento, fechada na esquerda e aberta na
    direita. A janela existe em vez de um simples "offset já passou" por causa de um caso concreto:
    o pré-aviso é D−3, e se a régua não rodou naquele dia (fim de semana, flag desligada, fatura
    emitida em cima da hora), um "sua fatura vence em 3 dias" chegando em D+1 seria mentira escrita
    pela casa. Passada a janela, o degrau simplesmente não cabe mais, e o próximo assume.

    O buraco entre uma janela e a seguinte é a **carência**, e ela não tem entrada nesta tabela de
    propósito: representá-la como um degrau que não faz nada convidaria alguém a preenchê-lo. O
    silêncio é o degrau.
    """

    key: str
    destino: str
    de: int
    ate: int | None
    assunto: str
    corpo: str

    def cabe_em(self, dias: int) -> bool:
        return self.de <= dias and (self.ate is None or dias < self.ate)


# O texto do degrau é **constante de código, revisada uma vez** — e é justamente isso que autoriza
# ele a sair sozinho (ADR 0031). O que o relógio decide é *se* a mensagem cabe hoje, não como ela
# está escrita.
_PRE_NOTICE = DunningStep(
    key="pre_notice",
    destino=CLIENTE,
    de=-3,
    ate=0,
    assunto="Lembrete: fatura {numero} vence em {dias_para_vencer} dia(s)",
    corpo=(
        "Olá,\n\n"
        "Passando só para lembrar que a fatura {numero}, no valor de {valor}, vence em "
        "{vencimento}.\n\n"
        "Se já tiver sido paga, desconsidere esta mensagem.\n\n"
        "Qualquer dúvida, é só responder este e-mail.\n\n"
        "Equipe Biahflow"
    ),
)
_REMINDER = DunningStep(
    key="reminder",
    destino=CLIENTE,
    de=3,
    ate=10,
    assunto="Fatura {numero} em aberto",
    corpo=(
        "Olá,\n\n"
        "A fatura {numero}, no valor de {valor}, venceu em {vencimento} e consta em aberto "
        "por aqui.\n\n"
        "Se o pagamento já foi feito, desconsidere esta mensagem — pode ser só o tempo de "
        "compensação.\n\n"
        "Se algo travou do lado de vocês, responda este e-mail e a gente resolve junto.\n\n"
        "Equipe Biahflow"
    ),
)
_FIRM = DunningStep(
    key="firm",
    destino=CLIENTE,
    de=10,
    ate=20,
    assunto="Fatura {numero} vencida há {dias} dias",
    corpo=(
        "Olá,\n\n"
        "A fatura {numero}, no valor de {valor}, está vencida há {dias} dias "
        "(vencimento em {vencimento}) e segue em aberto.\n\n"
        "Precisamos de uma posição sobre o pagamento. Se houver qualquer impedimento, responda "
        "este e-mail para combinarmos uma alternativa — é melhor tratar agora do que deixar "
        "correr.\n\n"
        "Equipe Biahflow"
    ),
)
# Os dois últimos **não falam com o cliente**. A RFC os descreve como "escalada para humano" e
# "renegociação", e as duas coisas são atos de gente: o que o sistema faz é acordar a pessoa certa
# com o contexto na mão.
_ESCALATION = DunningStep(
    key="escalation",
    destino=INTERNO,
    de=20,
    ate=30,
    assunto="Escalada de cobrança: {cliente}",
    corpo=(
        "A fatura {numero} de {cliente} ({valor}) está vencida há {dias} dias "
        "(vencimento em {vencimento}) e a régua já mandou o que tinha para mandar.\n\n"
        "Daqui em diante é decisão de relação, não de régua: fale com o cliente."
    ),
)
_RENEGOTIATION = DunningStep(
    key="renegotiation",
    destino=INTERNO,
    de=30,
    ate=None,
    assunto="Renegociação a decidir: {cliente}",
    corpo=(
        "A fatura {numero} de {cliente} ({valor}) está vencida há {dias} dias "
        "(vencimento em {vencimento}).\n\n"
        "Renegociar, cancelar ou insistir é decisão humana e continua sendo — o portal não faz "
        "nenhuma das três sozinho."
    ),
)

#: A escada padrão. O buraco entre D+0 e D+3 é a carência.
PADRAO: tuple[DunningStep, ...] = (_PRE_NOTICE, _REMINDER, _FIRM, _ESCALATION, _RENEGOTIATION)

#: Cliente de casa e sem histórico de atraso. **Não é refinamento, é requisito** da seção
#: Segurança da RFC 0004: *"cinco dias de atraso de um cliente antigo não é o mesmo evento que
#: reincidência"*. O lembrete atrasa (D+5), o degrau firme **não existe**, e o caso vai direto à
#: escalada interna — quem conversa com um cliente de anos é gente, não um template. Uma régua que
#: trata os dois casos igual está programada para perder o melhor cliente da carteira por uma
#: fatura.
RELACAO_LONGA: tuple[DunningStep, ...] = (
    _PRE_NOTICE,
    # A **mesma chave** do lembrete padrão, e não uma nova: a idempotência é
    # `UniqueConstraint(invoice, dunning_step)`, e se um cliente mudar de régua entre duas execuções
    # (deixou de ser reincidente, completou um ano) uma chave própria deixaria o mesmo lembrete
    # sair duas vezes. O que muda entre as duas escadas é a janela, não o degrau.
    replace(_REMINDER, de=5, ate=20),
    _ESCALATION,
    _RENEGOTIATION,
)

#: Cliente com insatisfação **declarada** vigente (FDD 037, ADR 0032). A camada 5 da RFC 0004 pede
#: *"travas de relação plugadas nos sinais de saúde e satisfação"*, e a seção Segurança da mesma
#: RFC proíbe o que a leitura ingênua dessa frase produz: *"recuar precisa ser declarado […] nunca
#: um 'pular' silencioso; vira desculpa para nunca cobrar, e o recebível estraga invisível"*.
#:
#: A saída que respeita as duas é esta: a régua **para de endurecer e passa a acordar gente**. O
#: degrau `firme` não existe e a escalada interna ocupa a janela que era dele (D+10) — quem então
#: recua é uma pessoa, declarando a suspensão com dono, prazo e motivo pelo mecanismo que a FDD 036
#: já construiu. O robô nunca fica mudo; a trava existe e tem nome.
#:
#: Como na `RELACAO_LONGA`, os degraus **reusam as chaves existentes**: a idempotência é
#: `UniqueConstraint(invoice, dunning_step)`, e uma chave nova faria o mesmo lembrete sair duas vezes
#: para quem trocasse de escada entre duas execuções — e trocar de escada aqui é fácil, basta
#: alguém registrar a insatisfação de ontem.
RELACAO_TENSA: tuple[DunningStep, ...] = (
    _PRE_NOTICE,
    _REMINDER,
    replace(_ESCALATION, de=10, ate=30),
    _RENEGOTIATION,
)

#: Um ano de casa. Não há nada de mágico no número; o que há é o requisito de existir um corte
#: explícito e testável, em vez de "cliente antigo" virar julgamento de quem estiver de plantão.
RELACAO_LONGA_DIAS = 365

#: Os dois estados em que uma fatura ainda comporta cobrança. `draft` nunca foi cobrado;
#: `paid`, `cancelled` e `renegotiated` são terminais no `INVOICE_TRANSITIONS`. Este conjunto é a
#: primeira guarda de `avaliar`, e é ele que faz "ninguém que pagou é cobrado" ser verdade sem
#: nenhuma rotina de cancelamento.
COBRAVEIS = ("issued", "overdue")

# Por que a régua se calou. Constantes e não literais porque são o resumo que o comando imprime e
# o que os testes nomeiam — um job silencioso cujo silêncio não se explica só pode ser lido como
# quebrado.
SEM_DEGRAU = "sem_degrau"
ESTADO_NAO_COBRAVEL = "estado_nao_cobravel"
SUSPENSA = "suspensa"
DEGRAU_GASTO = "degrau_gasto"
TETO_DE_FREQUENCIA = "teto_de_frequencia"
FIM_DE_SEMANA = "fim_de_semana"
FLAG_DESLIGADA = "flag_desligada"

# Por que a relação está tensa. **Só para exibição** — a escada é a mesma nas três causas, e
# nenhuma delas cala a régua. Constantes pela razão dos motivos de silêncio acima: são o que a tela
# rotula e o que os testes nomeiam. Se elas colapsassem num rótulo só, o painel diria "régua tensa"
# e não diria por quê, e as duas condutas que ele deveria sugerir são diferentes — uma pede
# conversa sobre a relação, a outra pede conserto da entrega.
#
# O identificador chamava-se `TENSAO_SATISFACAO` até a fatia 6 da issue #122 — é nome local, sem
# coinagem. **O valor não muda**: `"satisfacao"` é a chave de payload de `tensao_causa`
# (`docs/ontology/aliases.md`, "Termos ainda sem nome canônico"), e só quem tem canônico atravessa.
TENSAO_SATISFACTION = "satisfacao"
TENSAO_ENTREGA = "entrega"
TENSAO_AMBAS = "ambas"


class SemDestinatarioInterno(Exception):
    """Não há a quem escalar: nenhum admin ativo e nenhum dono ativo do cliente.

    Exceção e não `return None` porque o degrau **não pode ser gasto** neste caso, e porque a
    condição é consertável por gente (basta existir um admin ativo). `executar` a conta como falha
    e a loga; o degrau volta a caber na próxima passada.
    """


@dataclass(frozen=True)
class PainelContexto:
    """Tudo o que `avaliar` pergunta ao banco, carregado em lote e indexado por cliente/fatura.

    Existe pela mesma razão que o `OverviewContext` da FDD 022 e que `assess_projects_health`:
    `avaliar` faz **quatro** perguntas ao banco por fatura — suspensão, reincidência, degrau gasto
    e teto de frequência — e o painel é um laço sobre faturas. Sem pré-carga são quatro N+1 ao
    mesmo tempo, e é literalmente o defeito que a ADR 0014 mediu: `/clients/overview/` ia de 43 a
    169 queries e reprovou no gate de carga. Com o contexto, o painel emite o mesmo número de
    queries para 3 ou 300 faturas.

    **Isto não é uma segunda definição da régua**, e a distinção é a razão de o contexto existir em
    vez de um `painel.py` que recalcula tudo. As guardas continuam sendo as mesmas linhas de
    `avaliar`, na mesma ordem, com as mesmas constantes; o que muda é de onde vem o insumo — o
    mesmo movimento de `assess_project_health(project, milestones=..., tasks=...)`. Uma tela que
    recalculasse a decisão divergiria do relógio no primeiro ajuste, e ninguém veria.

    **Nasce para um dia.** O teto de frequência e a reincidência são recortes de `hoje`; `avaliar`
    recusa um contexto de outro dia em vez de responder errado em silêncio.

    `health_por_cliente` guarda **só o `level`**, nunca o score nem os sinais — a mesma cerca
    comercial de `ai.build_cobranca_context`, aqui porque a linha do painel vai para a tela e "62 de
    100, 2 entregas atrasadas" é a nossa medição da nossa própria falha.

    Ele é **por cliente e não por projeto** desde a FDD 038, e é o pior nível entre os projetos não
    concluídos dele. A chave é a da pergunta: a régua pergunta por cliente, e fatura sem projeto
    existe. Guardá-lo por projeto obrigaria a tela a escolher um — na prática o da fatura — e a
    escolha discordaria da guarda no caso que ela existe para tratar: o cliente com dois projetos,
    um crítico e um saudável, apareceria "saudável" com a régua já tensa.
    """

    hoje: date
    suspensao_por_fatura: dict[int, CobrancaSuspensao] = field(default_factory=dict)
    suspensao_por_cliente: dict[int, CobrancaSuspensao] = field(default_factory=dict)
    degraus_gastos: dict[int, set[str]] = field(default_factory=dict)
    clientes_no_teto: set[int] = field(default_factory=set)
    atrasos_por_cliente: dict[int, set[int]] = field(default_factory=dict)
    recebido_por_cliente: dict[int, Decimal] = field(default_factory=dict)
    health_por_cliente: dict[int, str] = field(default_factory=dict)
    # A última resposta de cobrança que a IA classificou e que **ninguém registrou ainda** (FDD 038,
    # ADR 0032). É leitura, não registro: o painel a mostra para oferecer o atalho, e ela some da
    # linha assim que existir um `SatisfactionRecord` apontando para aquela atividade. Sem a
    # pré-carga seria mais um N+1 por fatura, e por cliente e não por fatura porque a satisfação
    # é da relação.
    sinal_por_cliente: dict[int, Activity] = field(default_factory=dict)
    # Os registros **vigentes**, e não a satisfação já escolhida, porque as duas leituras desta
    # dimensão são diferentes: a linha do painel mostra a vigente de qualquer fonte (a percebida é
    # leitura útil para gente decidir) e a escada só reage à `declarada` (ADR 0032). Guardar uma
    # escolha só faria a segunda leitura se contentar com a sobra — uma percebida anotada depois de
    # uma declarada esconderia a declarada, e a tela passaria a discordar do relógio exatamente no
    # caso que esta fatia existe para tratar.
    satisfaction_records_por_cliente: dict[int, list[SatisfactionRecord]] = field(default_factory=dict)


def contexto_do_painel(invoices: Sequence[Invoice], hoje: date) -> PainelContexto:
    """Uma query por dimensão, e nenhuma dentro do laço.

    Treze consultas no total, independentemente de quantas faturas entrem — cinco delas vindas de
    `health.assess_projects_health`, que já resolveu o mesmo problema para a saúde do projeto.

    A satisfação vigente (FDD 037) é a penúltima, e é consultada aqui mesmo o `health` já tendo
    consultado a sua: aquela é a vigente **declarada** por cliente de projeto, esta é o conjunto
    vigente por cliente de fatura, e nem todo cliente com fatura tem projeto. Reaproveitar uma na
    outra faria a linha do painel depender de o cliente estar em entrega.
    """
    from . import health as health_module
    from .models import Activity, CobrancaSuspensao, DunningContact
    from .models import Invoice as InvoiceModel
    from .models import Project as ProjectModel
    from .models import SatisfactionRecord as SatisfactionRecordModel

    if not invoices:
        return PainelContexto(hoje=hoje)

    ids = [invoice.pk for invoice in invoices]
    clientes = {invoice.account_id for invoice in invoices}

    por_fatura: dict[int, CobrancaSuspensao] = {}
    por_cliente: dict[int, CobrancaSuspensao] = {}
    # A ordenação do modelo é `-until, -id`, então o primeiro de cada chave é o de prazo mais
    # distante — o mesmo que `.first()` escolheria na consulta fatura a fatura.
    for suspensao in (
        CobrancaSuspensao.objects.filter(lifted_at__isnull=True, until__gte=hoje)
        .filter(Q(invoice_id__in=ids) | Q(account_id__in=clientes))
        .select_related("owner")
    ):
        if suspensao.invoice_id is not None:
            por_fatura.setdefault(suspensao.invoice_id, suspensao)
        elif suspensao.account_id is not None:
            por_cliente.setdefault(suspensao.account_id, suspensao)

    gastos: dict[int, set[str]] = defaultdict(set)
    for invoice_id, degrau in DunningContact.objects.filter(invoice_id__in=ids).values_list(
        "invoice_id", "dunning_step"
    ):
        gastos[invoice_id].add(degrau)

    corte = hoje - timedelta(days=settings.DUNNING_MIN_DAYS_BETWEEN_CONTACTS)
    no_teto = set(
        DunningContact.objects.filter(
            account_id__in=clientes, canal=DunningContact.Canal.EMAIL, sent_on__gt=corte
        ).values_list("account_id", flat=True)
    )

    # A **mesma** expressão de `reincidente`, e não uma cópia: `_q_em_atraso` existe para isso.
    atrasos: dict[int, set[int]] = defaultdict(set)
    for account_id, invoice_id in (
        InvoiceModel.objects.filter(account_id__in=clientes)
        .filter(_q_em_atraso(hoje))
        .values_list("account_id", "id")
    ):
        atrasos[account_id].add(invoice_id)

    recebido = {
        linha["account_id"]: linha["total"]
        for linha in InvoiceModel.objects.filter(
            account_id__in=clientes, status=InvoiceModel.Status.PAID
        )
        .values("account_id")
        .annotate(total=Sum("amount"))
    }

    # A fonte do health são **os projetos não concluídos dos clientes das faturas**, e não os
    # projetos das faturas (FDD 038). A pergunta da guarda é por cliente: fatura sem projeto existe,
    # e o cliente cuja entrega está em frangalhos costuma ser justamente o que já saiu do projeto
    # que gerou a fatura. Projeto concluído fica de fora de propósito — um crítico congelado no
    # passado deixaria a trava ligada para sempre, que é como uma trava apodrece.
    ativos = list(
        ProjectModel.objects.filter(
            engagement__account_id__in=clientes, archived_at__isnull=True
        ).select_related("engagement").exclude(
            status=ProjectModel.Status.COMPLETED
        )
    )
    cliente_do_projeto = {project.pk: project.engagement.account_id for project in ativos}
    niveis: dict[int, list[str]] = defaultdict(list)
    for avaliacao in health_module.assess_projects_health(ativos):
        niveis[cliente_do_projeto[avaliacao["project_id"]]].append(avaliacao["level"])
    saude: dict[int, str] = {}
    for account_id, lista in niveis.items():
        # O **pior** nível, e a ordem é de `health` (a definição de "crítico" mora lá, e o limiar
        # não se redefine aqui). Cliente com um projeto em frangalhos e outro saudável não tem meia
        # saúde: a régua já reagiu ao crítico, e mostrar o saudável seria a tela contradizendo o
        # relógio.
        pior = health_module.worst_level(lista)
        if pior is not None:
            saude[account_id] = pior

    # A última resposta classificada e ainda não registrada, por cliente. O `exclude` sobre a
    # relação reversa é o que faz o atalho parar de insistir depois do registro — e ele olha só a
    # satisfação **não arquivada**, porque um registro que alguém arquivou deixou de valer e o
    # sinal volta a estar por registrar.
    sinais: dict[int, Activity] = {}
    registradas = SatisfactionRecordModel.objects.filter(
        source_activity__isnull=False, archived_at__isnull=True
    ).values("source_activity_id")
    for activity in (
        Activity.objects.filter(account_id__in=clientes, archived_at__isnull=True)
        .exclude(dunning_signal="")
        # Subconsulta explícita, e **não** `.exclude(satisfacoes__archived_at__isnull=True)`: o
        # `exclude` sobre relação reversa monta um LEFT JOIN, e para a atividade sem nenhuma
        # satisfação a coluna vem nula — ou seja, ele excluiria justamente os sinais por registrar,
        # que são todos os que esta linha existe para achar.
        .exclude(pk__in=registradas)
        # Explícito e não herdado do `Meta.ordering`: é a ordem que define qual é "a última", e ela
        # não pode depender de uma linha de outro arquivo continuar onde está.
        .order_by("-happened_on", "-created_at")
    ):
        sinais.setdefault(activity.account_id, activity)

    return PainelContexto(
        hoje=hoje,
        suspensao_por_fatura=por_fatura,
        suspensao_por_cliente=por_cliente,
        degraus_gastos=dict(gastos),
        clientes_no_teto=no_teto,
        atrasos_por_cliente=dict(atrasos),
        recebido_por_cliente=recebido,
        health_por_cliente=saude,
        sinal_por_cliente=sinais,
        satisfaction_records_por_cliente=satisfaction_module.registros_vigentes_por_cliente(
            clientes, hoje
        ),
    )


@dataclass(frozen=True)
class Avaliacao:
    """O que cabe hoje nesta fatura, e — quando nada cabe — por quê."""

    degrau: DunningStep | None
    motivo: str


def is_enabled() -> bool:
    return flags.is_enabled("cobranca")


def _hoje(hoje: date | None) -> date:
    """Todo "hoje" da régua vem de `localdate()`.

    `date.today()` devolve o dia do relógio do processo, que em contêiner é UTC: às 21h de São
    Paulo ele já virou, e a régua leria D+1 onde ainda é D+0.
    """
    return hoje or timezone.localdate()


def tempo_de_casa_dias(account: Account, hoje: date | None = None) -> int:
    return (_hoje(hoje) - timezone.localtime(account.created_at).date()).days


def _q_em_atraso(dia: date) -> Q:
    """O que conta como "já atrasou": paga depois do vencimento, ou vencida agora.

    Expressão única, e é por isso que ela é função e não literal repetido: `reincidente` a usa
    fatura a fatura e a pré-carga do painel a usa em lote, e duas cópias divergiriam no primeiro
    ajuste — a tela passaria a segmentar por uma régua e o relógio por outra.
    """
    from .models import Invoice

    return (
        Q(status=Invoice.Status.PAID, paid_at__date__gt=F("due_date"))
        | Q(status=Invoice.Status.OVERDUE)
        # A janela entre a virada do dia e o job das 06:00, em que a fatura está `issued` e
        # atrasada de fato. É a mesma leitura da `property is_overdue` (FDD 028), em SQL.
        | Q(status=Invoice.Status.ISSUED, due_date__lt=dia)
    )


def reincidente(
    account: Account,
    hoje: date | None = None,
    ignorando: Invoice | None = None,
    contexto: PainelContexto | None = None,
) -> bool:
    """Este cliente já atrasou antes?

    Sai do dado que sempre esteve gravado (FDD 036): fatura paga depois do vencimento, ou vencida
    agora. Nenhum campo novo — faltava alguém perguntar.

    **`ignorando` é o que faz a segmentação existir.** Sem excluir a fatura que está sendo avaliada,
    toda fatura vencida tornaria o próprio cliente "reincidente" e a régua `RELACAO_LONGA` seria
    inalcançável exatamente no momento em que ela serve para alguma coisa. Reincidência é
    histórico: *outras* faturas.
    """
    from .models import Invoice

    dia = _hoje(hoje)
    if contexto is not None:
        # O mesmo conjunto que a consulta abaixo produziria, já carregado em lote. A exclusão da
        # própria fatura é feita aqui, e não na pré-carga, porque o conjunto é **por cliente** e
        # cada fatura dele exclui uma diferente.
        atrasadas: set[int] = contexto.atrasos_por_cliente.get(account.pk, set())
        return bool(atrasadas - {ignorando.pk}) if ignorando is not None else bool(atrasadas)
    consulta = Invoice.objects.filter(account=account)
    if ignorando is not None and ignorando.pk:
        consulta = consulta.exclude(pk=ignorando.pk)
    return consulta.filter(_q_em_atraso(dia)).exists()


def satisfaction_vigente(
    account: Account, hoje: date | None = None, contexto: PainelContexto | None = None
) -> SatisfactionRecord | None:
    """O registro de satisfação que ainda vale hoje para este cliente, de **qualquer** fonte.

    É o que a linha do painel mostra: quem decide o próximo degrau precisa ver também a leitura de
    quem entrega, porque ela é o que existe antes de alguém ter perguntado. Ver `regua_para` para
    a outra pergunta, a que muda comportamento.
    """
    dia = _hoje(hoje)
    if contexto is not None:
        registros = contexto.satisfaction_records_por_cliente.get(account.pk, [])
    else:
        registros = satisfaction_module.registros_vigentes_por_cliente([account.pk], dia).get(
            account.pk, []
        )
    return satisfaction_module.vigente(registros, dia)


def dissatisfaction_declarada(
    account: Account, hoje: date | None = None, contexto: PainelContexto | None = None
) -> SatisfactionRecord | None:
    """A insatisfação que troca a escada: **declarada** pelo cliente e ainda vigente.

    `fonte=declared` e não as duas somadas, e essa linha é a decisão central da FDD 037
    (ADR 0032): abrandar uma cobrança é ato com consequência em dinheiro, e precisa da palavra do
    cliente — não da nossa leitura sobre ele. Somar as duas fontes num filtro só deixaria todos os
    testes de comportamento passando e faria a régua recuar por palpite.

    A escolha sai de `satisfaction.vigente(..., fonte=...)` e não de um filtro local, porque uma
    percebida registrada depois de uma declarada esconderia a declarada se a escolha fosse feita
    antes do filtro.
    """
    from .models import SatisfactionRecord

    dia = _hoje(hoje)
    if contexto is not None:
        registros = contexto.satisfaction_records_por_cliente.get(account.pk, [])
    else:
        registros = satisfaction_module.registros_vigentes_por_cliente([account.pk], dia).get(
            account.pk, []
        )
    registro = satisfaction_module.vigente(
        registros, dia, fonte=SatisfactionRecord.Fonte.DECLARED
    )
    if registro is None or registro.nivel != SatisfactionRecord.Nivel.DISSATISFIED:
        return None
    return registro


def entrega_critica(
    account: Account, hoje: date | None = None, contexto: PainelContexto | None = None
) -> bool:
    """A outra metade da camada 5: **a nossa entrega** está em estado crítico para este cliente?

    A condição é ter ao menos um projeto **não concluído** com `level == "crítico"`. Projeto
    concluído fica de fora porque um crítico congelado no passado deixaria a trava ligada para
    sempre — e uma trava que nunca desliga é uma trava que ninguém respeita.

    **Pergunta por cliente, e não pelo projeto da fatura** (FDD 038), pela mesma razão que o
    `SatisfactionRecord` liga ao cliente: a régua pergunta por cliente e fatura sem projeto existe.
    Ligar ao projeto da fatura deixaria a trava sem alcance justamente em quem já saiu daquela
    entrega.

    **Só o `level` atravessa**, nunca o score nem os sinais — a mesma cerca comercial do
    `PainelContexto`. E o limiar é o de `health._level`: reescrevê-lo aqui criaria uma segunda
    definição de "crítico", que diverge da primeira sem nada ficar vermelho.

    `hoje` entra na assinatura para as três guardas de `regua_para` serem chamadas do mesmo jeito, e
    não é usado: o Health Score é função pura sobre o agora e não recebe um dia por parâmetro.
    """
    from . import health as health_module
    from .models import Project

    if contexto is not None:
        # A **mesma** leitura que a linha do painel mostra, e não uma segunda consulta: é isto que
        # impede a tela de dizer "saudável" com a régua já tensa por entrega.
        return contexto.health_por_cliente.get(account.pk) == health_module.CRITICAL
    ativos = list(
        Project.objects.filter(engagement__account=account, archived_at__isnull=True).exclude(
            status=Project.Status.COMPLETED
        ).select_related("engagement")
    )
    return any(
        avaliacao["level"] == health_module.CRITICAL
        for avaliacao in health_module.assess_projects_health(ativos)
    )


def causa_da_tensao(
    account: Account, hoje: date | None = None, contexto: PainelContexto | None = None
) -> str | None:
    """Por que a relação está tensa — `satisfacao`, `entrega`, `ambas`, ou nada.

    **Não participa da decisão.** `regua_para` não a chama: as duas condições levam à mesma escada,
    e derivar a escada da causa transformaria um rótulo de tela em regra de dinheiro. O que ela
    existe para evitar é o painel dizer "régua tensa" sem dizer por quê — as condutas que as duas
    causas sugerem são diferentes, e uma é consertável por quem entrega.
    """
    dia = _hoje(hoje)
    por_satisfaction = dissatisfaction_declarada(account, dia, contexto=contexto) is not None
    por_entrega = entrega_critica(account, dia, contexto=contexto)
    if por_satisfaction and por_entrega:
        return TENSAO_AMBAS
    if por_satisfaction:
        return TENSAO_SATISFACTION
    if por_entrega:
        return TENSAO_ENTREGA
    return None


def regua_para(
    account: Account,
    hoje: date | None = None,
    ignorando: Invoice | None = None,
    contexto: PainelContexto | None = None,
) -> tuple[DunningStep, ...]:
    """Qual das três escadas vale para este cliente. Função pura sobre o cliente, no molde de
    `health._level`: explicável em uma frase e testável sem montar cenário.

    **A tensão é testada primeiro**, antes da relação longa (FDD 037). Um cliente de anos que está
    insatisfeito é o caso mais perigoso da carteira, e a escada desenhada para proteger o cliente
    antigo não pode absorvê-lo em silêncio — ela adia o lembrete e depois escala, quando o que este
    caso precisa é de gente na conversa mais cedo, não de mais paciência do robô.

    A tensão tem **duas** origens desde a FDD 038, e as duas levam à mesma escada: o cliente disse
    que está insatisfeito, ou a nossa entrega está em estado crítico. O argumento acima vale inteiro
    para a segunda — um cliente de anos com a entrega em frangalhos é o mesmo caso perigoso, só que
    medido pelo nosso próprio trabalho em vez de dito por ele. Uma escada nova para a entrega
    duplicaria a `RELACAO_TENSA` e, com chaves próprias, faria o mesmo lembrete sair duas vezes para
    quem trocasse de escada entre duas execuções. Qual das duas origens está valendo é pergunta de
    tela, e quem responde é `causa_da_tensao`.
    """
    dia = _hoje(hoje)
    if dissatisfaction_declarada(account, dia, contexto=contexto) is not None or entrega_critica(
        account, dia, contexto=contexto
    ):
        return RELACAO_TENSA
    if tempo_de_casa_dias(account, dia) >= RELACAO_LONGA_DIAS and not reincidente(
        account, dia, ignorando=ignorando, contexto=contexto
    ):
        return RELACAO_LONGA
    return PADRAO


def suspensao_ativa(
    invoice: Invoice, hoje: date | None = None, contexto: PainelContexto | None = None
) -> CobrancaSuspensao | None:
    """A suspensão que cala a régua para esta fatura — dela ou do cliente inteiro.

    `until__gte` porque `until` é inclusivo: a cobrança volta no dia **seguinte** ao prazo, e volta
    sozinha. Não existe "pular" silencioso em nenhum dos dois sentidos (RFC 0004).
    """
    from .models import CobrancaSuspensao

    dia = _hoje(hoje)
    if contexto is not None:
        # As duas candidatas que a consulta abaixo uniria. A de maior `until` vence, que é o que a
        # ordenação `-until, -id` do modelo faz com `.first()` — e é a certa para a tela mostrar:
        # a régua volta a falar na mais distante das duas.
        candidatas = [
            suspensao
            for suspensao in (
                contexto.suspensao_por_fatura.get(invoice.pk),
                contexto.suspensao_por_cliente.get(invoice.account_id),
            )
            if suspensao is not None
        ]
        return max(candidatas, key=lambda s: (s.until, s.pk)) if candidatas else None
    return (
        CobrancaSuspensao.objects.filter(lifted_at__isnull=True, until__gte=dia)
        .filter(Q(invoice=invoice) | Q(account_id=invoice.account_id))
        .first()
    )


def pode_contatar(
    account: Account, hoje: date | None = None, contexto: PainelContexto | None = None
) -> bool:
    """O teto duro de frequência: um contato ao cliente a cada N dias, somando todas as faturas.

    Conta só o que **foi ao cliente** (`canal="email"`). Aviso interno não gasta a franquia do
    cliente — ele nem chega lá —, e fazer a escalada competir com o lembrete pelo mesmo teto
    atrasaria justamente o degrau que existe para acordar gente.
    """
    from .models import DunningContact

    dia = _hoje(hoje)
    if contexto is not None:
        return account.pk not in contexto.clientes_no_teto
    corte = dia - timedelta(days=settings.DUNNING_MIN_DAYS_BETWEEN_CONTACTS)
    return not DunningContact.objects.filter(
        account=account, canal=DunningContact.Canal.EMAIL, sent_on__gt=corte
    ).exists()


def destinatarios(account: Account) -> list[Contact]:
    """Os contatos que recebem cobrança neste cliente. Vazio é resposta legítima, não erro."""
    from .models import Contact

    return list(
        Contact.objects.filter(
            account=account, receives_billing=True, archived_at__isnull=True
        ).exclude(email="")
    )


def dias_de_atraso(invoice: Invoice, hoje: date | None = None) -> int:
    """Dias desde o vencimento. Negativo antes dele — é o que o pré-aviso lê."""
    return (_hoje(hoje) - invoice.due_date).days


def avaliar(
    invoice: Invoice, hoje: date | None = None, contexto: PainelContexto | None = None
) -> Avaliacao:
    """Que degrau cabe hoje nesta fatura — e, quando nenhum, o motivo.

    **A ordem das guardas é a entrega**, e cada uma tem teste próprio:

    1. estado não cobrável — é ela que faz "ninguém que pagou é cobrado" ser verdade *por
       construção*, sem rotina de cancelamento que possa perder a corrida com a baixa;
    2. suspensão ativa — recuar é declarado, e a declaração vale mais que a régua;
    3. degrau já gasto — a idempotência, que o banco arbitra;
    4. teto de frequência — só para o que vai ao cliente;
    5. o degrau da escada.

    Inverter 1 e 3 não mudaria o resultado, mas inverter 4 e 5 mudaria: o teto precisa saber para
    onde o degrau vai antes de decidir se cala.

    `contexto` troca a **fonte** do dado, nunca a regra: as guardas continuam sendo estas linhas,
    nesta ordem. É o que `assess_project_health` faz com `milestones=`/`tasks=` (FDD 022) — sem
    isso, o painel precisaria reescrever a decisão em outro lugar, e a tela passaria a divergir do
    relógio no primeiro ajuste. Ver `PainelContexto`.
    """

    dia = _hoje(hoje)
    if contexto is not None and contexto.hoje != dia:
        # Contexto nasce para um dia: o teto de frequência e a reincidência são recortes de `hoje`.
        # Usá-lo para outro dia produziria silêncio (ou fala) sem nada ficar vermelho, que é a pior
        # classe de defeito desta funcionalidade.
        raise ValueError(f"Contexto do painel é de {contexto.hoje}, não de {dia}.")
    if invoice.status not in COBRAVEIS:
        return Avaliacao(None, ESTADO_NAO_COBRAVEL)
    if suspensao_ativa(invoice, dia, contexto=contexto) is not None:
        return Avaliacao(None, SUSPENSA)

    regua = regua_para(invoice.account, dia, ignorando=invoice, contexto=contexto)
    dias = dias_de_atraso(invoice, dia)
    degrau = next((d for d in regua if d.cabe_em(dias)), None)
    if degrau is None:
        return Avaliacao(None, SEM_DEGRAU)
    if _degrau_gasto(invoice, degrau, contexto):
        return Avaliacao(None, DEGRAU_GASTO)
    if degrau.destino == CLIENTE and not pode_contatar(invoice.account, dia, contexto=contexto):
        return Avaliacao(None, TETO_DE_FREQUENCIA)
    return Avaliacao(degrau, "")


def _degrau_gasto(invoice: Invoice, degrau: DunningStep, contexto: PainelContexto | None) -> bool:
    from .models import DunningContact

    if contexto is not None:
        return degrau.key in contexto.degraus_gastos.get(invoice.pk, frozenset())
    return DunningContact.objects.filter(invoice=invoice, dunning_step=degrau.key).exists()


def degrau_devido(invoice: Invoice, hoje: date | None = None) -> DunningStep | None:
    """O degrau que cabe hoje, ou nada. Fachada de `avaliar` para quem não precisa do motivo."""
    return avaliar(invoice, hoje).degrau


def moeda(valor: Decimal) -> str:
    """`Decimal("10000.01")` vira `"R$ 10.000,01"`.

    À mão e não por `locale`: o formato depende de um locale instalado no contêiner, e a diferença
    entre a máquina de quem desenvolve e a imagem de produção apareceria como um valor de fatura
    escrito errado num e-mail para cliente.
    """
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"R$ {milhar},{centavos}"


def texto_do_degrau(invoice: Invoice, degrau: DunningStep, hoje: date | None = None) -> tuple[str, str]:
    """Assunto e corpo do degrau, já preenchidos. Texto puro — não existe template HTML de e-mail
    neste produto, e introduzir um aqui seria dívida de renderização por uma mensagem de seis
    linhas."""
    dias = dias_de_atraso(invoice, hoje)
    campos = {
        "numero": invoice.number or f"#{invoice.pk}",
        "cliente": invoice.account.name,
        "valor": moeda(invoice.amount),
        "vencimento": invoice.due_date.strftime("%d/%m/%Y"),
        "dias": max(dias, 0),
        "dias_para_vencer": max(-dias, 0),
    }
    return degrau.assunto.format(**campos), degrau.corpo.format(**campos)


def _internos(account: Account) -> list[User]:
    """Quem responde pela relação: o dono do cliente e os admins.

    **Não é a equipe do projeto**, e por isso a notificação sai sem `project=`: o filtro de
    `notify` recorta por participação, e quem precisa decidir sobre um recebível vencido é quem
    responde pelo cliente — que pode não estar em projeto nenhum.
    """
    from .models import User

    # `Q(role=ADMIN) | Q(is_superuser=True)` é **o mesmo predicado de `User.is_admin_role`**, que é
    # quem autoriza no backend. Filtrar só por papel repetiria aqui o defeito que a FDD 017 corrigiu
    # no SPA: `manage.py createsuperuser` cria com `role` no default (`delivery`), então numa
    # instalação nova — quando o superusuário é o único admin que existe — a escalada não teria a
    # quem chegar. E este degrau é gasto uma vez só.
    pessoas = {
        pessoa.pk: pessoa
        for pessoa in User.objects.filter(
            Q(role=User.Role.ADMIN) | Q(is_superuser=True), is_active=True
        )
    }
    if account.owner_id and account.owner.is_active:
        pessoas.setdefault(account.owner_id, account.owner)
    return list(pessoas.values())


def registrar(
    invoice: Invoice,
    degrau: DunningStep,
    *,
    hoje: date | None = None,
    canal: str,
    subject: str,
    body: str,
    to_email: str = "",
    sent_by: User | None = None,
    ai_interaction: AiInteraction | None = None,
) -> DunningContact:
    """Grava o que saiu. **Só é chamada depois do envio**, nunca antes.

    A ordem não é estilo: as rodadas de homologação da FDD 024 acharam três vezes a mesma classe de
    defeito — registro gravado sem o fornecedor ter sido chamado. Aqui isso valeria duas mentiras
    ao mesmo tempo: o degrau constaria gasto (e a `UniqueConstraint` impediria a retentativa) e a
    tela diria que o cliente foi avisado quando nada saiu.
    """
    from .models import DunningContact

    return DunningContact.objects.create(
        invoice=invoice,
        account=invoice.account,
        dunning_step=degrau.key,
        canal=canal,
        sent_on=_hoje(hoje),
        subject=subject[:255],
        to_email=to_email,
        body=body,
        sent_by=sent_by,
        ai_interaction=ai_interaction,
    )


def enviar_ao_cliente(
    invoice: Invoice,
    degrau: DunningStep,
    *,
    hoje: date | None = None,
    subject: str = "",
    body: str = "",
    sent_by: User | None = None,
    ai_interaction: AiInteraction | None = None,
) -> DunningContact:
    """Manda o degrau ao cliente e registra. Sem contato de cobrança, vira escalada interna.

    Falha fechada, no padrão que a casa já usa no enriquecimento de lead (FDD 030): cala quando não
    sabe, em vez de chutar o destinatário de um e-mail sobre dinheiro. E cala **em voz alta** — o
    degrau é gasto como interno, com o motivo no corpo, para que a falta de contato apareça para
    quem pode cadastrá-lo em vez de sumir num log.
    """
    from .models import DunningContact

    assunto, corpo = texto_do_degrau(invoice, degrau, hoje)
    assunto, corpo = subject or assunto, body or corpo

    contatos = destinatarios(invoice.account)
    if not contatos:
        motivo = (
            f"{degrau.key}: nada saiu para o cliente porque {invoice.account.name} não tem "
            "nenhum contato marcado como 'recebe cobrança' com e-mail preenchido."
        )
        return _escalar(invoice, degrau, hoje=hoje, subject=assunto, body=motivo, sent_by=sent_by)

    enderecos = [contato.email for contato in contatos]
    # `fail_silently=False` de propósito, ao contrário do espelho de e-mail das notificações: lá o
    # registro in-app já existe e o e-mail é cópia; aqui o e-mail **é** o degrau, e engolir a falha
    # gravaria um `DunningContact` afirmando um contato que não aconteceu.
    send_mail(assunto, corpo, None, enderecos, fail_silently=False)
    return registrar(
        invoice,
        degrau,
        hoje=hoje,
        canal=DunningContact.Canal.EMAIL,
        subject=assunto,
        body=corpo,
        to_email=", ".join(enderecos),
        sent_by=sent_by,
        ai_interaction=ai_interaction,
    )


def _escalar(
    invoice: Invoice,
    degrau: DunningStep,
    *,
    hoje: date | None = None,
    subject: str = "",
    body: str = "",
    sent_by: User | None = None,
) -> DunningContact:
    """Acorda quem responde pela relação. Nada disto sai para o cliente."""
    from . import notifications
    from .models import DunningContact

    assunto, corpo = texto_do_degrau(invoice, degrau, hoje)
    assunto, corpo = subject or assunto, body or corpo
    internos = _internos(invoice.account)
    if not internos:
        # **Escalada sem ninguém a acordar não gasta o degrau.** Registrar aqui produziria o pior
        # dos dois mundos: a régua pararia de falar com o cliente (o degrau interno assumiu) e
        # ninguém saberia disso — o "pular silencioso" que a RFC 0004 recusa nos dois sentidos.
        # Levantar deixa `executar` contar a falha e logar em `ERROR`, que vira evento no Sentry
        # (ADR 0012), e o degrau volta a caber amanhã, quando existir a quem escalar.
        raise SemDestinatarioInterno(
            f"Nenhum admin ativo e nenhum dono ativo para escalar a cobrança de "
            f"{invoice.account.name}."
        )
    notifications.notify(internos, "cobranca", f"{assunto} — {corpo}", "/cobranca")
    return registrar(
        invoice,
        degrau,
        hoje=hoje,
        canal=DunningContact.Canal.INTERNO,
        subject=assunto,
        body=corpo,
        sent_by=sent_by,
    )


def aplicar(invoice: Invoice, degrau: DunningStep, hoje: date | None = None) -> DunningContact:
    """Executa o degrau pelo destino dele. É o caminho automático (`sent_by` fica nulo)."""
    if degrau.destino == CLIENTE:
        return enviar_ao_cliente(invoice, degrau, hoje=hoje)
    return _escalar(invoice, degrau, hoje=hoje)


def _nome_da_regua(regua: tuple[DunningStep, ...]) -> str:
    if regua is RELACAO_TENSA:
        return "relacao_tensa"
    return "relacao_longa" if regua is RELACAO_LONGA else "padrao"


def painel(hoje: date | None = None) -> list[dict[str, object]]:
    """Uma linha por fatura cobrável, com o que a decisão do próximo passo precisa.

    Existe porque a RFC 0004 exige, na seção Segurança, que quem decide veja *health, tempo de casa
    e valor do cliente* **na mesma tela** — *"não a dois cliques"*, e a dois cliques ninguém olha.
    Sem esta rota, o SPA teria de reescrever `regua_para`, `reincidente`, `tempo_de_casa_dias` e o
    teto em TypeScript: uma segunda definição da régua, que é o que a ADR 0026 e a FDD 017 proíbem
    justamente porque as duas cópias não ficam vermelhas ao divergir — elas só passam a discordar.

    **Responde com a flag desligada**, e cada linha diz isso. É leitura, e serve para decidir se
    vale ligar; mas uma tela que mostrasse "próximo degrau: lembrete" sem avisar que nada vai sair
    prometeria por conta própria.

    O silêncio vem **nomeado** (`motivo`), com as mesmas constantes de `avaliar`. Uma tela que só
    diz "nada hoje" ensina quem a usa a não confiar nela — e a régua tem quatro motivos legítimos
    de calar.
    """
    from .models import DunningContact, Invoice

    dia = _hoje(hoje)
    invoices = list(
        # Sem `select_related("project")` desde a FDD 038: o health da linha deixou de ser o do
        # projeto **da fatura** e passou a ser o pior nível do cliente, e nenhuma outra coluna lê o
        # projeto. Um `select_related` sem leitor é um join pago por nada.
        Invoice.objects.filter(status__in=COBRAVEIS)
        .select_related("account")
        .order_by("due_date", "id")
    )
    contexto = contexto_do_painel(invoices, dia)
    ligada = is_enabled()

    # O dinheiro deste painel sai como texto por `dinheiro.dinheiro` — o argumento inteiro está
    # na docstring de lá. O fechamento que morava aqui era a primeira das três definições da mesma
    # regra; a ADR 0068 as reduziu a uma.
    linhas: list[dict[str, object]] = []
    for invoice in invoices:
        avaliacao = avaliar(invoice, dia, contexto=contexto)
        degrau = avaliacao.degrau
        regua = regua_para(invoice.account, dia, ignorando=invoice, contexto=contexto)
        suspensao = suspensao_ativa(invoice, dia, contexto=contexto)
        satisfaction = satisfaction_vigente(invoice.account, dia, contexto=contexto)
        sinal = contexto.sinal_por_cliente.get(invoice.account_id)
        linhas.append({
            "invoice": invoice.pk,
            "number": invoice.number,
            # O par canônico e o legado saem **juntos**, com o mesmo valor — o comportamento de
            # todo alias de leitura da `/api/v1/` (`docs/ontology/aliases.md` §2c). Este painel é
            # dict cru, sem serializer que faça isso sozinho (`AliasesDaV1Mixin` não alcança quem
            # não é `ModelSerializer`), então os dois pares são escritos à mão aqui. A view remove
            # `client`/`client_name` da resposta quando a requisição é da `/api/v2/` (issue #122,
            # fatia 3a) — quem decide isso é ela, não este agregador, que não conhece a versão.
            "account": invoice.account_id,
            "account_name": invoice.account.name,
            "client": invoice.account_id,
            "client_name": invoice.account.name,
            "amount": dinheiro(invoice.amount),
            "due_date": invoice.due_date,
            "status": invoice.status,
            "status_display": invoice.get_status_display(),
            "dias_de_atraso": dias_de_atraso(invoice, dia),
            "payment_url": invoice.payment_url,
            "proximo_degrau": degrau.key if degrau else None,
            "proximo_degrau_display": (
                DunningContact.DunningStep(degrau.key).label if degrau else None
            ),
            # A data em que a janela do degrau **abriu**, não uma previsão: com o degrau cabendo
            # hoje ela está no passado, e é o que deixa "o quê e quando" caber numa linha só.
            "proximo_degrau_em": (
                invoice.due_date + timedelta(days=degrau.de) if degrau else None
            ),
            "motivo": avaliacao.motivo,
            # Só o nível, e o **pior entre os projetos não concluídos do cliente** (FDD 038).
            # Era o do projeto da fatura, e os dois discordavam: a guarda de entrega olha todos os
            # projetos ativos do cliente, então a tela diria "saudável" com a régua já tensa. Nulo
            # quando o cliente não tem projeto ativo nenhum. Ver a cerca comercial em
            # `PainelContexto`.
            "health_level": contexto.health_por_cliente.get(invoice.account_id),
            "tempo_de_casa_dias": tempo_de_casa_dias(invoice.account, dia),
            # A satisfação vigente, na mesma linha do próximo degrau (FDD 037) — a exigência da
            # RFC 0004 de decidir *"na mesma tela, não a dois cliques"*, agora com o sinal que
            # vinha da outra parte da relação. Vai a **fonte** junto, e não só o nível, porque a
            # linha precisa dizer se aquilo é o cliente falando ou a nossa leitura sobre ele: é o
            # que separa o que muda a escada do que não muda.
            "satisfacao_nivel": satisfaction.nivel if satisfaction else None,
            "satisfacao_fonte": satisfaction.fonte if satisfaction else None,
            # Idade e não a data: o sinal envelhece, e "há 12 dias" é a leitura que faz alguém
            # perguntar de novo — a data crua exigiria a subtração de cabeça.
            "satisfacao_dias": (dia - satisfaction.happened_on).days if satisfaction else None,
            # Por que a relação está tensa, quando está (FDD 038). Rótulo, não decisão: a escada
            # é a mesma nas três causas, e é `regua` que diz qual escada vale.
            "tensao_causa": causa_da_tensao(invoice.account, dia, contexto=contexto),
            # A leitura da IA que **ninguém registrou ainda** (ADR 0032). Vai rotulada como leitura
            # justamente para não se confundir com a satisfação vigente logo acima: aquela é
            # registro, esta é uma resposta lida. Some da linha quando alguém registrar.
            "sinal_kind": sinal.dunning_signal if sinal else None,
            "sinal_display": sinal.get_dunning_signal_display() if sinal else None,
            "sinal_em": sinal.happened_on if sinal else None,
            "sinal_activity": sinal.pk if sinal else None,
            "reincidente": reincidente(invoice.account, dia, ignorando=invoice, contexto=contexto),
            "regua": _nome_da_regua(regua),
            # O "valor do cliente" que a RFC pede à vista: o que a casa já recebeu dele, e não o
            # que ela estimou ganhar. Custo, margem e ROI continuam fora — aqui como no rascunho.
            "recebido_do_cliente": dinheiro(
                contexto.recebido_por_cliente.get(invoice.account_id, Decimal("0"))
            ),
            "suspensao": (
                {
                    "id": suspensao.pk,
                    "until": suspensao.until,
                    "owner": suspensao.owner_id,
                    "owner_name": suspensao.owner.get_full_name() or suspensao.owner.username,
                }
                if suspensao
                else None
            ),
            "regua_ligada": ligada,
        })
    return linhas


def executar(hoje: date | None = None) -> dict[str, object]:
    """Uma passada da régua sobre todas as faturas cobráveis. Devolve um resumo contável.

    O resumo conta **os calados e por quê**, e isso não é enfeite: fim de semana, teto, suspensão e
    degrau gasto são todos "não hoje", então um job que não manda nada é o caso comum. Sem os
    motivos, a única leitura possível de um job silencioso é supor que ele quebrou.

    **Com a flag desligada, no-op silencioso** — o mesmo desenho de `digest.send_daily_digest` e
    `calendar_sync`: a regra de flag mora no módulo de domínio, e o `scheduler.py` não a duplica.
    """
    from .models import Invoice

    def _resumo(
        *, avaliadas: int = 0, contatos: int = 0, escaladas: int = 0, falhas: int = 0,
        calados: dict[str, int] | None = None, motivo: str = "",
    ) -> dict[str, object]:
        return {
            "avaliadas": avaliadas, "contatos": contatos, "escaladas": escaladas,
            "falhas": falhas, "calados": calados or {}, "motivo": motivo,
        }

    if not is_enabled():
        return _resumo(motivo=FLAG_DESLIGADA)

    dia = _hoje(hoje)
    # **Nada em fim de semana.** Cobrança que chega no sábado é lida como falta de educação, e o
    # ganho de antecipá-la dois dias é zero. Determinístico e testável, ao contrário de "horário
    # comercial" implícito no cron.
    if dia.weekday() >= 5:
        return _resumo(motivo=FIM_DE_SEMANA)

    avaliadas = contatos = escaladas = falhas = 0
    calados: dict[str, int] = {}
    # A lista materializada e **um** contexto para a passada inteira (FDD 038). O laço já era um
    # N+1 de quatro perguntas por fatura; a guarda de entrega somaria o Health Score de cada
    # cliente a isso, e o job roda sobre a carteira toda. É a mesma pré-carga do painel, e a
    # equivalência entre os dois caminhos tem teste próprio — `contexto` troca a fonte do dado,
    # nunca a regra.
    cobraveis = list(Invoice.objects.filter(status__in=COBRAVEIS).select_related("account__owner"))
    contexto = contexto_do_painel(cobraveis, dia)
    for invoice in cobraveis:
        avaliadas += 1
        avaliacao = avaliar(invoice, dia, contexto=contexto)
        if avaliacao.degrau is None:
            calados[avaliacao.motivo] = calados.get(avaliacao.motivo, 0) + 1
            continue
        try:
            # `atomic()` próprio por fatura, e não um em volta do laço: a `UniqueConstraint` do
            # degrau é quem arbitra a corrida entre duas execuções, e um `IntegrityError` capturado
            # dentro de um bloco externo sem savepoint deixa a transação do Postgres envenenada —
            # tudo o que viesse depois falharia com "current transaction is aborted", e no SQLite
            # do CI passaria (mesma lição de `invoices.finish_issue`).
            with transaction.atomic():
                contato = aplicar(invoice, avaliacao.degrau, dia)
        except IntegrityError:
            # Outra execução gastou o degrau entre a leitura e a gravação. Não é erro: é a
            # idempotência funcionando.
            calados[DEGRAU_GASTO] = calados.get(DEGRAU_GASTO, 0) + 1
            continue
        except Exception:  # noqa: BLE001 - uma fatura não pode derrubar a régua inteira
            logger.exception("régua de cobrança falhou na fatura %s", invoice.pk)
            falhas += 1
            continue
        if contato.canal == "email":
            contatos += 1
            # **O teto de frequência é a única dimensão que esta passada muda**, e é por cliente:
            # sem esta linha, quem tem três faturas vencidas receberia três e-mails no mesmo dia —
            # o contexto foi lido antes do primeiro envio e continuaria dizendo que a franquia está
            # livre. Era o que a consulta fatura a fatura fazia de graça, e é o preço de pré-carregar
            # o que o próprio laço altera. As outras dimensões (suspensão, reincidência, satisfação,
            # health) não mudam por a régua ter falado.
            contexto.clientes_no_teto.add(invoice.account_id)
        else:
            escaladas += 1

    return _resumo(
        avaliadas=avaliadas, contatos=contatos, escaladas=escaladas, falhas=falhas, calados=calados
    )
