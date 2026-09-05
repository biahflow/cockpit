"""As perguntas de Discovery, congeladas em constante (ADR 0069; DAP
`dap-discovery-session-e-business-case-r2`, decisão **E1**).

Espelho de `docs/discovery-questions.md`, que por sua vez é espelho da ficha *Discovery Questions
— base genérica* do Notion. **Não se decide pergunta aqui**: mudar o texto de uma é mudança na
fonte e passa pela §8 do mapa de linguagem — entra primeiro na página do Notion, depois no espelho
em `docs/`, depois aqui.

Molde de `kickoff.KICKOFF_TEMPLATES` e de `invoices.INVOICE_SCHEDULES`: método que a casa executa,
escrito como constante de módulo e servido por rota. A alternativa — uma base de perguntas editável
no Pulse (E2) — foi recusada por escrito na ADR 0069: a mesma pergunta passaria a existir em dois
lugares divergindo em silêncio. Constantes no cliente (E3) foi recusada porque o método precisa
alcançar o corpus e os agentes, e nada disso roda no navegador.

## Por que cada pergunta tem um id estável, e por que isso não é detalhe

A resposta de uma sessão é gravada em `DiscoverySession.notes`, sob o id da pergunta. **Guardá-la
por índice seria um defeito silencioso com data marcada**: a própria ficha prevê que a base evolua
(*"perguntas que provaram valor em duas verticais sobem para a base genérica"*), e inserir uma
pergunta no meio de um bloco faria a resposta de ontem aparecer sob a pergunta de hoje — sem erro,
sem log, sem nada vermelho. Quem lesse a sessão veria uma citação de reunião respondendo a outra
pergunta, que é a pior forma de dado errado: plausível.

Com o id, reordenar, acrescentar e remover são operações seguras, e a consequência da remoção fica
declarada em vez de escondida: a resposta de uma pergunta que saiu da base **continua gravada** e
deixa de ser exibida. Ela não se perde — o registro de uma reunião que não se repete não é apagado
por edição de catálogo.

O id é slug, e não número: `q3` seria um índice com outro nome.

## O que atravessa da ficha para cá, e o que fica lá

**A pergunta como ela é feita.** A ficha escreve algumas linhas com um aparte para quem conduz —
*"(levam a caminhos diferentes)"*, *"(quase toda operação tem pelo menos uma; se disserem que não,
pergunte de outro jeito)"*, *"(alimenta esta base)"*. Isso é orientação de condução, não parte da
pergunta, e vira rótulo de campo ruim numa tela usada durante a reunião. A orientação **de bloco**
atravessa em `note`, que é onde a ficha a escreve como tal (blocos E e F).

Nada disso é edição da fonte: a ficha continua sendo a fonte, e o espelho fiel dela é
`docs/discovery-questions.md`. O que este módulo recorta é o que a tela mostra.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryQuestion:
    """Uma pergunta da base: o id estável e o texto que a ficha do Notion escreve."""

    id: str
    text: str


@dataclass(frozen=True)
class DiscoveryBlock:
    """Um bloco A–F.

    Dois rótulos, e a diferença é de superfície: `label` é o nome do bloco como a ficha o escreve
    (o cabeçalho do painel, "Bloco B — Follow the work (com quem executa)"), e `short_label` é a
    forma curta da faixa de blocos. Ela vem daqui, e não do TypeScript, pela razão de E1: encurtar
    o nome na tela criaria uma segunda definição de como o bloco se chama, fora da fonte.

    `note` é a regra de condução que a ficha escreve junto do bloco, quando há uma. Vazia é o
    normal — quatro dos seis blocos não têm.
    """

    id: str
    label: str
    short_label: str
    questions: tuple[DiscoveryQuestion, ...]
    note: str = ""


def _bloco(
    id: str, label: str, short_label: str, note: str, perguntas: tuple[tuple[str, str], ...]
) -> DiscoveryBlock:
    return DiscoveryBlock(
        id=id, label=label, short_label=short_label, note=note,
        questions=tuple(DiscoveryQuestion(id=chave, text=texto) for chave, texto in perguntas),
    )


BLOCKS: tuple[DiscoveryBlock, ...] = (
    _bloco(
        "a", "Contexto executivo", "Contexto executivo", "",
        (
            ("negocio-hoje",
             "Como está o negócio hoje? Cresceu, encolheu ou estabilizou nos últimos 12 meses?"),
            ("o-que-mais-incomoda",
             "Quando você olha o resultado do mês, o que mais te incomoda?"),
            ("se-o-ano-fechasse-hoje", "Se o ano fechasse hoje, o que teria dado errado?"),
            ("o-que-mudou",
             "O que mudou nos últimos meses que fez isso virar prioridade agora?"),
            ("cortar-despesa-ou-esforco",
             "Quando você diz que precisa reduzir custo, é cortar despesa ou fazer a mesma coisa "
             "com menos esforço?"),
            ("um-problema-em-90-dias",
             "Se você pudesse resolver um único problema operacional nos próximos 90 dias, qual "
             "seria?"),
            ("o-que-ja-tentaram",
             "O que vocês já tentaram melhorar aí e não foi para frente? Por que parou?"),
        ),
    ),
    _bloco(
        "b", "Follow the work (com quem executa)", "Follow the work", "",
        (
            ("caso-real-do-comeco-ao-fim",
             "Me leva por um caso real, do começo ao fim. Pega um caso recente — o que aconteceu, "
             "na ordem?"),
            ("onde-precisou-interpretar",
             "Onde nesse caminho alguém precisou interpretar, adivinhar ou ligar para outra "
             "pessoa?"),
            ("planilha-fora-do-sistema", "Que planilha existe fora do sistema?"),
            ("como-a-informacao-passa",
             "Quando a informação passa de uma pessoa para outra, ela passa por onde: sistema, "
             "WhatsApp, papel, voz?"),
            ("casos-por-mes", "Quantos casos desse tipo passam por aqui num mês?"),
            ("tempo-do-caso",
             "Quanto tempo leva um caso simples? E um complicado? Qual a proporção entre eles?"),
            ("falta-de-informacao",
             "Com que frequência falta informação para você conseguir trabalhar? O que você faz "
             "quando falta?"),
            ("o-que-volta-para-refazer", "O que volta para refazer, e por quê?"),
            ("mudar-uma-coisa-no-fluxo",
             "Se você pudesse mudar uma coisa nesse fluxo, qual seria?"),
        ),
    ),
    _bloco(
        "c", "Sistemas e dados", "Sistemas e dados", "",
        (
            ("sistemas-e-quem-usa",
             "Quais sistemas participam desse processo, e quem usa cada um?"),
            ("onde-a-informacao-nasce", "Onde a informação nasce? Onde ela mora depois?"),
            ("sistemas-conversam", "Esses sistemas conversam entre si ou alguém redigita?"),
            ("exportacao-e-formato",
             "Dá para exportar dados desses sistemas? Em que formato?"),
            ("meses-de-historico", "Quantos meses de histórico existem?"),
            ("quem-extrai", "Quem consegue extrair? Precisa do fornecedor?"),
            ("confianca-nos-dados",
             "Qual a confiança de vocês na qualidade desses dados, de 1 a 5?"),
        ),
    ),
    _bloco(
        "d", "Sponsor, acesso e abertura a mudança", "Sponsor e acesso", "",
        (
            ("quem-bate-o-martelo",
             "Se aparecer uma mudança de processo que exige decisão sua, você bate o martelo ou "
             "passa por mais alguém?"),
            ("acesso-a-quem-executa",
             "Vou precisar conversar com quem executa. Isso é possível nas próximas duas "
             "semanas?"),
            ("mudar-como-a-informacao-e-coletada",
             "Se o diagnóstico apontar que o problema não é tecnologia e sim como a informação é "
             "coletada hoje, vocês topariam mudar isso?"),
            ("data-que-torna-urgente",
             "Existe alguma data ou compromisso que torna isso urgente?"),
            ("quem-vai-resistir",
             "Quem nessa operação provavelmente vai resistir à mudança, e por quê?"),
        ),
    ),
    _bloco(
        "e", "Magnitude (ordem de grandeza)", "Magnitude",
        "Faça para as duas ou três dores priorizadas. Não busque número perfeito — busque "
        "magnitude.",
        (
            ("vezes-por-mes", "Quantas vezes isso acontece por mês?"),
            ("quem-resolve-e-quanto-tempo",
             "Quem resolve quando acontece, e quanto tempo essa pessoa gasta?"),
            ("salario-da-funcao", "Quanto ganha, por mês, uma pessoa nessa função?"),
            ("custo-do-erro", "Quando dá errado de vez, quanto custa o erro?"),
            ("sabem-ou-e-impressao", "Vocês sabem esse número ou é impressão?"),
        ),
    ),
    _bloco(
        "f", "Fechamento e aprendizado", "Fechamento",
        "Nunca pergunte “gostou do trabalho?”.",
        (
            ("o-que-entendem-agora",
             "O que vocês entendem agora sobre a operação que não estava claro antes do "
             "Discovery?"),
            ("o-que-faria-diferente",
             "Se a gente fizesse isso de novo, o que você faria diferente?"),
            ("pergunta-que-nao-fez-sentido",
             "Teve alguma pergunta minha que não fez sentido para vocês?"),
        ),
    ),
)

#: Índice por id, para quem valida o que chega no corpo. Derivado, e não uma segunda lista.
BLOCK_BY_ID: dict[str, DiscoveryBlock] = {bloco.id: bloco for bloco in BLOCKS}


def block(block_id: str) -> DiscoveryBlock | None:
    """O bloco de um id, ou `None`. Quem chama decide se a ausência é 400."""
    return BLOCK_BY_ID.get(block_id)


def question_ids(block_id: str) -> frozenset[str]:
    """Os ids de pergunta que um bloco aceita hoje. Vazio para bloco que não existe."""
    bloco = BLOCK_BY_ID.get(block_id)
    return frozenset(pergunta.id for pergunta in bloco.questions) if bloco else frozenset()
