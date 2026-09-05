"""O próximo passo da conta: qual melhoria atacar em seguida, e **o que falta nela** (FDD 054).

A ADR 0069 registrou que esta peça "já existe pela metade e ninguém percebeu": o sinal está
pronto — `priority.ranking_da_conta` ordena por Opportunity Score e `recommendations.py` já emite
a recomendação `prioritization`. **O que faltava era o leitor**, e a pergunta que ele responde não
é "qual é a melhor?", é *"o que falta nela?"*.

**A função devolve a primeira com degrau pendente, e não a de maior score.** Uma oportunidade já
encaminhada — hipótese escolhida, business case aprovado, venda aberta — esconderia a seguinte se
o critério fosse só a posição no ranking, e o painel existe para dizer o que fazer, não para
repetir a ordenação que a tela de priorização já mostra.

**Ela devolve chaves, nunca frases**, no molde exato de `prove.o_que_falta_para_iniciar`: rótulo é
da superfície, e um servidor que devolvesse "Escolher a hipótese" em português congelaria a copy do
board dentro do backend — o mesmo defeito que o `CLAUDE.md` proíbe em mapa de estado ("devolve
variante, nunca a cor").

**É a única expressão da regra, e são dois os leitores.** A action `next-step` do `AccountViewSet`
desenha o painel do detalhe da conta (DAP `dap-discovery-session-e-business-case-r2`, decisão B1) e
`recommendations.build_recommendations` escolhe por ela a oportunidade que anuncia em
`/indicadores`. Se o recomendador mantivesse a query própria dele, os dois lugares mostrariam
respostas diferentes para a mesma pergunta, e a divergência não deixaria nada vermelho — foi o
contra-argumento registrado da decisão B1, e esta função é a metade que o responde.

**A ordenação não é reimplementada aqui.** Quem responde "qual vem antes" continua sendo
`priority.ranking_da_conta`, que também é quem define o conjunto elegível: viva, não descartada e
**com avaliação vigente**. Sem avaliação não há por onde ordenar, e é por isso que o vazio honesto
do painel diz "o próximo passo aparece quando houver avaliação" em vez de inventar uma fila.

**O quarto degrau é heurístico, e isso não se esconde.** Não existe FK entre
`ImprovementOpportunity` e `CommercialOpportunity` — e não deve existir: é a separação que o
`language-map` §5 protege, uma é melhoria operacional a priorizar e a outra é receita a fechar. Sem
o elo, "já abrimos a venda desta melhoria?" só se responde no nível da **conta**, e a consequência
fica declarada: uma conta com qualquer venda aberta não recebe este degrau, mesmo que a venda seja
de outro assunto. É leitura conservadora de propósito — errar para o lado de não cobrar quem já
tem conversa comercial em aberto é mais barato que mandar abrir a segunda venda do mês.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .priority import ranking_da_conta

if TYPE_CHECKING:
    from .models import Account, BusinessCase, ImprovementOpportunity

#: Os quatro degraus, **na ordem em que se percorre**. A ordem é a cadeia da FDD 048 mais o elo que
#: a FDD 053 fechou: escolher a aposta → orçá-la → decidir investir → vender. Ela não se reordena,
#: pelo motivo das cinco dimensões de `priority.DIMENSOES`: é ela que permite ler a tela e saber em
#: que altura da conversa a oportunidade está.
DEGRAU_ESCOLHER_HIPOTESE = "choose_hypothesis"
DEGRAU_MONTAR_BUSINESS_CASE = "build_business_case"
DEGRAU_DECIDIR_INVESTIMENTO = "decide_investment"
DEGRAU_ABRIR_VENDA = "open_commercial_opportunity"

#: O vocabulário fechado, para o esquema publicá-lo em vez de prometer "qualquer texto" — é o único
#: consumidor desta tupla, e é o que a impede de ser uma segunda definição da ordem: quem decide qual
#: degrau vence continua sendo a cadeia de `_degrau_pendente`, e nada aqui itera esta lista.
DEGRAUS: tuple[str, ...] = (
    DEGRAU_ESCOLHER_HIPOTESE,
    DEGRAU_MONTAR_BUSINESS_CASE,
    DEGRAU_DECIDIR_INVESTIMENTO,
    DEGRAU_ABRIR_VENDA,
)


def tem_venda_aberta(account: Account) -> bool:
    """Se a conta tem alguma `CommercialOpportunity` viva em etapa **aberta**.

    Público, e não privado, porque `recommendations.build_recommendations` faz exatamente esta
    pergunta na regra de `upsell` — e duas expressões de "esta conta tem venda em aberto" divergem
    na primeira vez que alguém mexer numa delas. É o mesmo argumento de
    `ImprovementOpportunity.current_assessment` e de `Project.objects.visible_to` (ADR 0010),
    aplicado a um predicado pequeno o bastante para parecer que não precisa de casa.
    """
    from .models import CommercialOpportunity, PipelineStage

    return CommercialOpportunity.objects.filter(
        account=account, archived_at__isnull=True, stage__kind=PipelineStage.Kind.OPEN
    ).exists()


def _hipotese_escolhida(oportunidade: ImprovementOpportunity) -> bool:
    """Se existe hipótese viva `chosen` — a que a constraint parcial garante ser no máximo uma.

    Filtra em Python sobre `.all()`, e não com `.filter()`, pela razão escrita em
    `ImprovementOpportunity.current_assessment`: um `.filter()` emite consulta nova e **ignora** o
    `prefetch_related` de quem chamou, que é custo de N+1 com aparência de custo resolvido.
    """
    from .models import SolutionHypothesis

    return any(
        hipotese.archived_at is None and hipotese.status == SolutionHypothesis.Status.CHOSEN
        for hipotese in oportunidade.hypotheses.all()
    )


def _business_cases_vivos(oportunidade: ImprovementOpportunity) -> list[BusinessCase]:
    """Os business cases não arquivados desta oportunidade. Mesma leitura, mesmo motivo."""
    return [caso for caso in oportunidade.business_cases.all() if caso.archived_at is None]


def _degrau_pendente(
    oportunidade: ImprovementOpportunity, venda_aberta: Callable[[], bool]
) -> str | None:
    """A chave do primeiro degrau que falta nesta oportunidade, ou `None` se nada falta.

    `venda_aberta` chega como função e não como booleano de propósito: só o quarto degrau precisa da
    resposta, e ela custa uma consulta por conta. Avaliá-la para toda oportunidade — inclusive as
    que param no primeiro degrau, que é o caso comum — pagaria a consulta para descartá-la.

    **Rascunho vence aprovado quando os dois existem.** A ordem é a desta cadeia — e ela é a única
    definição dela —, com o primeiro casamento vencendo: um business case ainda em rascunho ao lado
    de um aprovado é decisão pendente, e é ela que a tela precisa mostrar. Só a aprovação é única
    por oportunidade (a constraint parcial do modelo); rascunhos convivem.

    **Recusado não é pendência.** Uma oportunidade cujo investimento foi rejeitado não tem degrau
    nenhum: a decisão foi tomada, e insistir nela seria o produto discordando de quem decidiu. Ela
    sai da fila e a seguinte assume — que é o comportamento inteiro desta função.
    """
    from .models import BusinessCase

    if not _hipotese_escolhida(oportunidade):
        return DEGRAU_ESCOLHER_HIPOTESE
    vivos = _business_cases_vivos(oportunidade)
    if not vivos:
        return DEGRAU_MONTAR_BUSINESS_CASE
    if any(caso.status == BusinessCase.Status.DRAFT for caso in vivos):
        return DEGRAU_DECIDIR_INVESTIMENTO
    aprovado = any(caso.status == BusinessCase.Status.APPROVED for caso in vivos)
    if aprovado and not venda_aberta():
        return DEGRAU_ABRIR_VENDA
    return None


def _ranqueadas_em_ordem(account_id: int) -> list[ImprovementOpportunity]:
    """As oportunidades ranqueadas da conta, na ordem do ranking, com o que os degraus perguntam.

    Uma consulta e três prefetches: a avaliação (para o score que sai na resposta), as hipóteses e
    os business cases (para os degraus). Sem eles, cada oportunidade da conta custaria três
    consultas — e quem chama isto por conta é `build_recommendations`, que já itera a carteira
    inteira.
    """
    from .models import ImprovementOpportunity

    ranking = ranking_da_conta(account_id)
    if not ranking:
        return []
    por_id = {
        oportunidade.pk: oportunidade
        for oportunidade in ImprovementOpportunity.objects.filter(pk__in=ranking).prefetch_related(
            "assessments", "hypotheses", "business_cases"
        )
    }
    return [por_id[pk] for pk in sorted(ranking, key=lambda pk: ranking[pk])]


def oportunidades_ranqueadas(account: Account) -> int:
    """Quantas oportunidades da conta entraram na ordenação — o mesmo conjunto de `ranking_da_conta`.

    Existe porque o painel tem **dois** vazios que não são o mesmo vazio (DAP r2, seção 2): "nenhuma
    oportunidade priorizada nesta conta" e "nada pendente". Os dois chegam como `None` de
    `proximo_passo_da_conta`, e distingui-los na tela recontando oportunidades pelo `score != null`
    reexpressaria o critério de elegibilidade do ranking num segundo lugar — que é exatamente o que
    a decisão B1 comprou ao mandar os dois leitores usarem uma função só.
    """
    return len(ranking_da_conta(account.pk))


def proximo_passo_da_conta(account: Account) -> dict[str, Any] | None:
    """A primeira oportunidade ranqueada com degrau pendente, ou `None` quando nenhuma tem.

    Devolve `improvement_opportunity`, `title`, `score`, `assessment_version` e `missing`. O score
    sai como **texto**, na mesma forma que `ImprovementOpportunitySerializer.get_score` já publica
    (`"78.00"`), e a versão vai junto dele pelo motivo da decisão B1 do DAP de priorização: um score
    sem a versão ao lado é um número que não se pode comparar com o da semana passada.
    """
    venda: bool | None = None

    def venda_aberta() -> bool:
        """Memoiza a resposta: a pergunta é da conta, e a fila pode ter várias oportunidades."""
        nonlocal venda
        if venda is None:
            venda = tem_venda_aberta(account)
        return venda

    for oportunidade in _ranqueadas_em_ordem(account.pk):
        falta = _degrau_pendente(oportunidade, venda_aberta)
        vigente = oportunidade.current_assessment
        # `vigente` nunca é nulo aqui — `ranking_da_conta` só ranqueia quem tem avaliação viva —, e
        # a condição existe para o tipo, não para o caso: quem lê `vigente.score` logo abaixo
        # precisa que a leitura seja garantida, e não otimismo.
        if falta is None or vigente is None:
            continue
        return {
            "improvement_opportunity": oportunidade.pk,
            "title": oportunidade.title,
            "score": str(vigente.score),
            "assessment_version": vigente.version,
            "missing": falta,
        }
    return None
