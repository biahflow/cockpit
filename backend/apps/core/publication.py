"""A cadeia de publicação do Discovery — quem sustenta quem, num lugar só (FDD 051, ADR 0060).

`Process`, `Evidence`, `Finding`, `PainPoint` e `ImprovementOpportunity` ganharam marca de
publicável (`published_at`/`published_by`), e a marca sozinha não basta. O que o cliente vê
precisa ter sustentação **publicada** embaixo: sem isso a lista de ids do payload aponta para o
que não atravessou, e ele lê uma afirmação sobre a operação dele sem nada atrás.

A cadeia é uma escada de quatro degraus, mais uma âncora lateral:

    Evidence  →  Finding (fact)  →  PainPoint  →  ImprovementOpportunity
                     ↑                  ↑
                     └──── Process ─────┘

**O `Process` é raiz do próprio ramo e não pede nada para subir** — as etapas andam com ele. Mas
`findings[].process_id` e `pain_points[].process_id` atravessam, e um achado publicado citando
um processo que não está em `processes[]` é referência pendurada: o mesmo defeito que
`finding_ids`/`pain_point_ids` filtrados evitam do outro lado. Daí a âncora ser requisito para
subir, impedimento para descer **e** impedimento para se mudar por baixo de quem já subiu: mover
`process`/`step` de um registro publicado para um mapa não publicado pendura a referência sem
tocar em `published_at` nenhum.

`o_que_falta_para_publicar` é o único lugar em que a pergunta *"pode subir?"* é feita, e
`dependentes_publicados_de` o único em que se faz a inversa, *"quem cai se este sair?"*. As duas
são consultadas pelas actions `publish/`/`unpublish/` **e** pelos `perform_destroy`, porque
despublicar e arquivar desfazem a mesma sustentação — expressar a regra em cada porta faria as
portas divergirem no primeiro conserto, e o sintoma seria um item de pé no One sem nada embaixo.
É o motivo de `prove.o_que_falta_para_iniciar` e de `priority.ranking_da_conta` (ADR 0010).

`falta_a_ancora` é público pela mesma razão: `FindingSerializer` e `PainPointSerializer` fazem a
pergunta da âncora sobre o valor que **chegou no corpo**, e chamam esta função em vez de repetir
"publicado e vivo" com os dois FKs — a repetição divergiria no primeiro conserto, como as portas
divergiriam.

**A função devolve chaves, não frases.** Rótulo é da superfície, e um servidor que devolvesse
"evidência publicada" congelaria a copy de um board dentro do backend — a mesma decisão que
`prove.py` já tomou e que `CLAUDE.md` cobra dos mapas de estado ("devolve variante, nunca a cor").
`ROTULOS` e `frase_do_impedimento` existem para a mensagem da API ter texto legível sem que
nenhuma tela dependa dele.

**O `Evidence` é a folha e não exige nada**: ela é o dado bruto, o fim da escada. E o `Finding`
só exige o degrau de baixo quando é `fact`, pelo mesmo recorte da invariante §6.9 do
`language-map` — uma hipótese publicada é honesta justamente por não afirmar sustentação que não
tem. A âncora do processo, essa, vale para os três estados: ela não é sobre certeza, é sobre a
referência não ficar pendurada.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models import Model

    from .models import (
        Evidence,
        Finding,
        ImprovementOpportunity,
        PainPoint,
        Process,
        ProcessStep,
    )

    Publicavel = Evidence | Finding | ImprovementOpportunity | PainPoint | Process

#: Os requisitos de sustentação, um por degrau da escada. Chaves, e a ordem é a da escada.
REQUISITO_EVIDENCIA = "published_evidence"
REQUISITO_ACHADO = "published_finding"
REQUISITO_DOR = "published_pain_point"
#: Fora da escada de propósito: o processo não sustenta o achado, ele o **ancora**. Um achado sem
#: processo é perfeitamente publicável; o que não pode é citar um mapa que não atravessou.
REQUISITO_PROCESSO = "published_process"

REQUISITOS: tuple[str, ...] = (
    REQUISITO_EVIDENCIA,
    REQUISITO_ACHADO,
    REQUISITO_DOR,
    REQUISITO_PROCESSO,
)

ROTULOS: dict[str, str] = {
    REQUISITO_EVIDENCIA: "ao menos uma evidência publicada e viva",
    REQUISITO_ACHADO: "ao menos um achado publicado e vivo",
    REQUISITO_DOR: "ao menos uma dor publicada e viva",
    REQUISITO_PROCESSO: "o processo que ele cita publicado e vivo",
}

#: A recusa de despublicar/arquivar, por degrau: o que está preso e como sair dele. Uma redação
#: por degrau, lida pelas duas portas — o texto é o mesmo porque o estado impeditivo é o mesmo.
_IMPEDIMENTO: dict[str, str] = {
    "Evidence": "Esta é a última evidência publicada e viva de {quantos} achado(s) publicado(s) "
    "como fato. Despublique o achado primeiro, ou publique outra evidência.",
    "Finding": "Este é o último achado publicado e vivo de {quantos} dor(es) publicada(s). "
    "Despublique a dor primeiro, ou publique outro achado.",
    "PainPoint": "Esta é a última dor publicada e viva de {quantos} oportunidade(s) de melhoria "
    "publicada(s). Despublique a oportunidade primeiro, ou publique outra dor.",
    # Sem "ou publique outro": o achado cita **um** processo, então não há segunda âncora a
    # oferecer. A única saída é pelo de cima, e a mensagem diz isso em vez de sugerir um caminho
    # que não existe.
    "Process": "Este processo é a âncora de {quantos} achado(s) ou dor(es) publicado(s). "
    "Despublique-os primeiro.",
}


def _tem_publicado_vivo(related: Any, excluindo: int | None = None) -> bool:
    """Existe no M2M ao menos um registro publicado e não arquivado?

    `.filter()` e não `.all()` filtrado em Python — o contrário do que `prove._medicoes_vivas` e
    `ImprovementOpportunity.current_assessment` fazem, e a assimetria tem medida: lá quem chama é
    o snapshot, iterando dezenas de linhas sobre um `prefetch_related`; aqui quem chama é uma
    action sobre **um** objeto, e `EXISTS` no banco é uma consulta contra carregar a coleção
    inteira para descartá-la.
    """
    queryset = related.filter(archived_at__isnull=True, published_at__isnull=False)
    if excluindo is not None:
        queryset = queryset.exclude(pk=excluindo)
    return queryset.exists()


def _processos_ancorados(process: Process | None, step: ProcessStep | None) -> list[Process]:
    """Os processos que uma âncora cita — por `process`, por `step`, ou pelos dois.

    O `step` conta, e não é preciosismo: `step_id` atravessa no snapshot como o `process_id`, a
    etapa só sai **dentro** do processo publicado, e um achado ancorado só na etapa penduraria a
    referência exatamente igual. Contar os dois aqui é o que mantém `publish/` e `unpublish/`
    simétricos — a recusa de despublicar já olha os dois caminhos.

    Os dois FKs são `SET_NULL` e independentes no schema, então nada garante que apontem para o
    mesmo mapa; a lista deduplica por pk em vez de supor que apontam.
    """
    ancoras: list[Process] = []
    vistos: set[int] = set()
    for processo in (process, step.process if step is not None else None):
        if processo is not None and processo.pk not in vistos:
            vistos.add(processo.pk)
            ancoras.append(processo)
    return ancoras


def o_que_falta_para_publicar(obj: Publicavel) -> list[str]:
    """As chaves do que **falta** para este registro atravessar. Lista vazia = pode publicar.

    A lista existe pela forma de `prove.o_que_falta_para_iniciar`, para a superfície poder desenhar
    pastilhas — e desde a âncora do processo ela de fato traz duas chaves de vez em quando: um
    `fact` pode faltar evidência publicada **e** citar um mapa que ninguém publicou.

    **O `Process` é raiz e não pede nada**: ele abre o próprio ramo, e as etapas andam com ele.
    """
    from .models import Evidence, Finding, PainPoint, Process

    if isinstance(obj, Evidence | Process):
        return []
    if isinstance(obj, Finding):
        faltas = []
        if obj.epistemic_status == Finding.EpistemicStatus.FACT and not _tem_publicado_vivo(
            obj.evidences
        ):
            faltas.append(REQUISITO_EVIDENCIA)
        return faltas + falta_a_ancora(obj.process, obj.step)
    if isinstance(obj, PainPoint):
        faltas = [] if _tem_publicado_vivo(obj.findings) else [REQUISITO_ACHADO]
        return faltas + falta_a_ancora(obj.process, obj.step)
    return [] if _tem_publicado_vivo(obj.pain_points) else [REQUISITO_DOR]


def falta_a_ancora(process: Process | None, step: ProcessStep | None) -> list[str]:
    """`[REQUISITO_PROCESSO]` quando algum mapa citado não atravessaria junto.

    Recebe a âncora **resolvida**, e não o registro que a cita, porque a quinta porta pergunta
    pelo mapa que *vai* valer: o `PATCH` que move `process`/`step` de um registro publicado
    compara o destino antes de ele estar no objeto. Ler de `obj.process`/`obj.step` obrigaria o
    serializer a reexpressar a regra sobre os valores novos — a segunda definição de "a âncora
    está publicada" que este módulo existe para não ter.
    """
    return (
        [REQUISITO_PROCESSO]
        if any(
            processo.archived_at is not None or processo.published_at is None
            for processo in _processos_ancorados(process, step)
        )
        else []
    )


def frase_do_que_falta(faltas: list[str]) -> str:
    """Os rótulos do que falta, para a mensagem de 400. Ordem estável: a de `REQUISITOS`."""
    return ", ".join(ROTULOS[chave] for chave in REQUISITOS if chave in faltas)


def dependentes_publicados_de(obj: Publicavel) -> list[Model]:
    """Os registros publicados que ficariam **sem sustentação publicada** se este saísse do ar.

    "Sair do ar" é despublicar **ou** arquivar: as duas desfazem a mesma coisa, e por isso a
    pergunta é uma só. É a inversa exata de `o_que_falta_para_publicar`, e o recorte acompanha:
    só `fact` prende evidência, porque só ele a exigiu para subir.

    Lista vazia para `ImprovementOpportunity`, que é o topo da escada — nada pende dela. Ramo
    escrito e não omitido porque a função é chamada pelas cinco actions.

    **O ramo do `Process` não pergunta pela "última"**, e é a única assimetria da função: um
    achado cita **um** mapa, então todo achado publicado que o cite fica pendurado se ele sair —
    não há segunda âncora que o salve, como uma segunda evidência salva o fato.
    """
    from .models import Evidence, Finding, PainPoint, Process

    if isinstance(obj, Process):
        return [
            *Finding.objects.filter(
                Q(process_id=obj.pk) | Q(step__process_id=obj.pk),
                archived_at__isnull=True,
                published_at__isnull=False,
            ).distinct(),
            *PainPoint.objects.filter(
                Q(process_id=obj.pk) | Q(step__process_id=obj.pk),
                archived_at__isnull=True,
                published_at__isnull=False,
            ).distinct(),
        ]
    if isinstance(obj, Evidence):
        return [
            achado
            for achado in obj.findings.filter(
                epistemic_status=Finding.EpistemicStatus.FACT,
                archived_at__isnull=True,
                published_at__isnull=False,
            )
            if not _tem_publicado_vivo(achado.evidences, excluindo=obj.pk)
        ]
    if isinstance(obj, Finding):
        return [
            dor
            for dor in obj.pain_points.filter(
                archived_at__isnull=True, published_at__isnull=False
            )
            if not _tem_publicado_vivo(dor.findings, excluindo=obj.pk)
        ]
    if isinstance(obj, PainPoint):
        return [
            oportunidade
            for oportunidade in obj.improvement_opportunities.filter(
                archived_at__isnull=True, published_at__isnull=False
            )
            if not _tem_publicado_vivo(oportunidade.pain_points, excluindo=obj.pk)
        ]
    return []


def frase_do_impedimento(obj: Publicavel, dependentes: list[Model]) -> str:
    """A mensagem do 409: quantos ficam presos e qual é o caminho de saída.

    Recusar, e nunca despublicar o de cima em silêncio — é o argumento das duas guardas de
    arquivamento que já existem (FDD 045, FDD 048): desfazer sozinho uma decisão que uma pessoa
    tomou é pior que o 409 que diz qual estado impede e como sair dele.
    """
    return _IMPEDIMENTO[type(obj).__name__].format(quantos=len(dependentes))
