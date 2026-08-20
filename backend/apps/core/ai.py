"""Camada de IA (OpenAI) atrás de flag.

Mesma estratégia do `apps/core/drive.py`: o SDK é importado de forma lazy e só é chamado
quando `AI_ENABLED`. As funções de montagem de contexto e o limite de uso são puras e
testáveis; a chamada ao modelo fica fora da cobertura (`# pragma: no cover`).

Antivazamento: o contexto passado ao modelo contém apenas dados do recurso em questão
(nunca o conteúdo binário dos documentos — só os nomes) e o system prompt orienta o modelo
a responder somente com base no material fornecido.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone

from . import flags

if TYPE_CHECKING:
    from .models import Activity, Invoice, Lead, Meeting, Opportunity, Project, User

# Limite de caracteres da transcrição enviada ao modelo (controle de tokens/custo).
MEETING_TRANSCRIPT_LIMIT = 12000

# Quantos blocos do catálogo a proposta carrega (FDD 026). Existe pela mesma razão do limite
# acima: o catálogo é aberto e cresce sem teto, e um prompt que cresce com ele é custo por
# chamada que ninguém pediu. Seis cabem numa proposta sem virar lista de compras.
OPPORTUNITY_BLUEPRINT_LIMIT = 6

# Quantos cases publicados a proposta cita (FDD 027). Menor que o teto de blueprints de propósito:
# blueprint é escopo — precisa listar o que a venda inclui —, case é prova, e três provas boas
# convencem mais que seis rasas.
OPPORTUNITY_CASE_LIMIT = 3

# Quantos processos mapeados do cliente a proposta carrega (FDD 039). Mesmo motivo dos dois tetos
# acima: o mapa de uma operação inteira cresce sem limite, e um prompt que cresce com ele é custo
# por chamada que ninguém pediu. Quatro processos descrevem a operação sem virar inventário.
OPPORTUNITY_PROCESSO_LIMIT = 4


class AiProviderError(Exception):
    """A OpenAI não respondeu: rede, timeout, chave revogada, cota ou modelo inacessível.

    Existe para que quem chama possa tratar **falha do fornecedor** sem engolir junto um defeito
    nosso. Sem ela, o único jeito de proteger uma action era `except Exception` em volta de todo o
    trabalho — e aí um erro de banco no `save()` seguinte seria reportado como "a IA está fora do
    ar", que é exatamente o tipo de mentira que a FDD 024 existe para evitar.
    """


def is_enabled() -> bool:
    return flags.is_enabled("ai")


# Features que **não** partem de uma pessoa. A cota existe para limitar o que alguém gasta; cobrar
# dela um job que roda sozinho encolhe a franquia sem avisar — o digest diário tirava 1 das 50
# chamadas de cada usuário ativo com itens, todo dia, por um e-mail que ninguém pediu.
AUTOMATED_FEATURES = ("daily_digest",)


def within_daily_limit(user: User) -> bool:
    from .models import AiInteraction

    today = timezone.localdate()
    used = (
        AiInteraction.objects.filter(user=user, created_at__date=today)
        .exclude(feature__in=AUTOMATED_FEATURES)
        .count()
    )
    return used < settings.AI_DAILY_LIMIT


def build_project_context(project: Project) -> str:
    from .models import Document, Milestone, Task

    # A data de hoje ancora todo o resto: sem ela o modelo recebe uma lista de prazos e **não tem
    # como saber qual já venceu**. Observado na rodada 2 (FDD 024) — perguntado sobre o maior
    # risco de um projeto com tarefa vencida há três dias, o assistente respondeu "Não sei." em
    # três tokens, porque de fato não dava para saber. Vale para resumo, próximos passos e chat.
    lines = [f"Hoje é {timezone.localdate()}.", f"Projeto: {project.name}", f"Status: {project.status}"]
    if project.description:
        lines.append(f"Descrição: {project.description}")
    lines.append(f"Período: {project.start_date} a {project.due_date}")

    milestones = Milestone.objects.filter(project=project, archived_at__isnull=True)
    if milestones:
        lines.append("Marcos:")
        lines += [f"- {m.title} [{m.status}] prazo {m.due_date}" for m in milestones]
    tasks = Task.objects.filter(project=project, archived_at__isnull=True)
    if tasks:
        lines.append("Tarefas:")
        lines += [f"- {t.title} [{t.status}] prazo {t.due_date}" for t in tasks]
    documents = Document.objects.filter(project=project, archived_at__isnull=True)
    if documents:
        lines.append("Documentos (nomes): " + ", ".join(d.original_name for d in documents))
    return "\n".join(lines)


def build_meeting_context(meeting: Meeting) -> str:
    """Contexto de uma reunião para Discovery/Assessment: só dados desta reunião."""
    transcript = meeting.transcript.strip()
    if len(transcript) > MEETING_TRANSCRIPT_LIMIT:
        transcript = transcript[:MEETING_TRANSCRIPT_LIMIT] + "\n[transcrição truncada]"
    lines = [
        f"Projeto: {meeting.project.name}",
        f"Reunião: {meeting.title}",
        f"Data: {meeting.date}",
        f"Situação: {meeting.status}",
        "Transcrição:",
        transcript,
    ]
    return "\n".join(lines)


def build_opportunity_context(opportunity: Opportunity) -> str:
    lines = [
        f"Oportunidade: {opportunity.title}",
        f"Cliente: {opportunity.client.name}",
        f"Valor estimado: {opportunity.estimated_value}",
        f"Etapa: {opportunity.stage.name}",
        f"Previsão de fechamento: {opportunity.expected_close_date}",
    ]
    if opportunity.contact:
        lines.append(f"Contato: {opportunity.contact.name}")
    if opportunity.scope:
        lines.append(f"Escopo: {opportunity.scope}")
    service = opportunity.service
    if service:
        label = f"{service.name} ({service.get_tier_display()})" if service.tier else service.name
        lines.append(f"Nível de produto: {label}")
        lines.append(f"Preço de tabela: {'gratuito' if service.is_free else service.list_price}")
        if service.summary:
            lines.append(f"Escopo do nível: {service.summary}")
    lines.extend(_blueprint_lines(opportunity))
    lines.extend(_case_lines(opportunity))
    lines.extend(_processo_lines(opportunity))
    return "\n".join(lines)


def _blueprint_lines(opportunity: Opportunity) -> list[str]:
    """Os blocos do catálogo aplicáveis a esta oportunidade (FDD 026).

    É o que faz a proposta citar o Funcionário Digital concreto — "um SDR que qualifica lead fora
    do horário" — e não só o nível de produto. Aplicável significa: ativo, e ou amarrado ao nível
    vendido ou genérico (sem `service`), porque um bloco de Implantação não cabe num Discovery.
    Os valores saem **resolvidos** pela vertical do cliente, que é a razão de a variante existir.

    Sem catálogo, nada é emitido — quem não construiu biblioteca segue com o contexto de antes.
    O antivazamento fica intacto: isto lê esta oportunidade e o catálogo global, que é da casa e
    não de cliente nenhum.
    """
    from . import blueprints
    from .models import DigitalEmployeeBlueprint

    aplicaveis = list(
        DigitalEmployeeBlueprint.objects.filter(active=True)
        .filter(Q(service=opportunity.service_id) | Q(service__isnull=True))
        .prefetch_related("variants")[:OPPORTUNITY_BLUEPRINT_LIMIT]
    )
    if not aplicaveis:
        return []
    vertical = opportunity.client.vertical
    lines = ["Funcionários Digitais do catálogo aplicáveis a esta venda:"]
    for blueprint in aplicaveis:
        valores = blueprints.resolve(blueprint, vertical)
        detalhe = f"- {valores['name']} ({valores['area_display']})"
        if valores["description"]:
            detalhe += f": {valores['description']}"
        if valores["kpi_label"]:
            detalhe += f" | KPI: {valores['kpi_label']}"
        if valores["hours_saved_month"]:
            detalhe += f" | ~{valores['hours_saved_month']}h poupadas/mês"
        lines.append(detalhe)
    if vertical:
        lines.append(f"Vertical do cliente: {vertical.name} (os blocos acima já vêm ajustados a ela)")
    return lines


_UNIDADE_KPI = {
    "percent": "%", "hours": "h", "minutes": "min", "currency": "R$", "count": "",
}


def _numero_kpi(valor: str | None, unidade: str) -> str:
    """`"48"` + `"hours"` vira `"48h"`. Sem unidade, o número sai sozinho."""
    if valor is None:
        return "—"
    sufixo = _UNIDADE_KPI.get(unidade, "")
    return f"R$ {valor}" if unidade == "currency" else f"{valor}{sufixo}"


def _case_lines(opportunity: Opportunity) -> list[str]:
    """Os cases publicados da mesma vertical — a prova, ao lado da promessa (FDD 027).

    Três guardas fazem esta função, e nenhuma é decorativa:

    1. **Só publicado com consentimento.** A condição de publicação já é essa, e repeti-la na
       consulta é barato: se um dia algo publicar por outro caminho, o prompt não sai citando
       cliente que não autorizou.
    2. **Nunca o `roi_snapshot`.** Receita e custo de outro cliente são números internos da casa, e
       este texto vai para uma proposta que o cliente lê. O que sai é métrica operacional do
       Funcionário Digital e o health — o que o cliente comprou, não o que a casa ganhou.
    3. **Anonimizado não vira nome.** Case sem autorização de marca entra como "uma empresa do
       setor X", que é exatamente para o que `anonymized` existe.

    Sem case publicado da vertical, nada é emitido: quem ainda não tem repositório segue com o
    contexto de antes.
    """
    from .models import Case

    vertical = opportunity.client.vertical
    if vertical is None:
        # Sem vertical não há "mesmo setor", e citar case de qualquer setor seria prova fraca
        # vendida como forte. Ao contrário do catálogo, que resolve para o genérico, aqui o
        # silêncio é a resposta certa.
        return []
    publicados = list(
        Case.objects.filter(
            status=Case.Status.PUBLISHED,
            client_consent=True,
            archived_at__isnull=True,
            vertical=vertical,
        ).select_related("project__client")[:OPPORTUNITY_CASE_LIMIT]
    )
    if not publicados:
        return []
    lines = [f"Cases já entregues no mesmo setor ({vertical.name}), com número real:"]
    for case in publicados:
        # No case anonimizado nem o título entra: ele é montado como "Cliente — Projeto" no
        # congelamento, e deixá-lo passar devolveria pela porta dos fundos o nome que
        # `anonymized` existe para omitir.
        lines.append(f"- Uma empresa do setor {vertical.name}" if case.anonymized else f"- {case.title}")
        if case.summary:
            lines.append(f"  {case.summary}")
        for metrica in case.metrics:
            rotulo = metrica.get("kpi_label") or metrica.get("name") or "KPI"
            unidade = metrica.get("kpi_unit", "")
            depois = _numero_kpi(metrica.get("current"), unidade)
            if metrica.get("has_baseline"):
                antes = _numero_kpi(metrica.get("baseline"), unidade)
                sentido = "menor é melhor" if metrica.get("kpi_direction") == "down" else "maior é melhor"
                lines.append(f"  · {rotulo}: de {antes} para {depois} ({sentido})")
            else:
                # A lacuna é dita, não preenchida: sem base registrada, "de 0 para 48" seria uma
                # afirmação que ninguém mediu.
                lines.append(f"  · {rotulo}: {depois} ao final (sem base registrada no início)")
        saude = case.health_snapshot.get("score")
        if saude is not None:
            lines.append(f"  · Saúde da entrega ao encerrar: {saude}/100")
    return lines


def _processo_lines(opportunity: Opportunity) -> list[str]:
    """O que o Discovery levantou da operação do cliente — e **só o número que tem fato atrás**
    (FDD 039).

    Quatro guardas, no molde de `_case_lines` acima, e a terceira é a razão de a função existir:

    1. **Sem processo mapeado, nada é emitido.** Quem não fez Discovery estruturado segue com o
       contexto de antes, como acontece sem case e sem catálogo.
    2. **O mapa qualitativo sempre entra**: o nome do processo e os nomes das etapas. É descrição
       do que foi levantado, não afirmação de quantidade — não depende de sustentação nenhuma.
    3. **O número do custo só entra quando há evidência rotulada como fato por trás dele**
       (`processos.custo_do_estado_atual` responde isso em `sustentacao`). Levar para uma proposta
       que o cliente lê um custo apoiado só em hipótese é literalmente o que
       `docs/metodologia-fde.md:86` proíbe: apresentar hipótese como fato. E o dano não é o número
       errado — é que ele volta na reunião seguinte como compromisso da casa.
    4. **A lacuna é dita, não silenciada.** Omitir o processo não sustentado deixaria o modelo
       diante de um buraco, e diante de um buraco o modelo preenche — foi o defeito que a rodada 5
       de homologação achou na base de conhecimento (FDD 029). Dizer "este não está sustentado, não
       afirme número" é a instrução que o silêncio não dá. Mesmo movimento do "sem base registrada
       no início" em `_case_lines`, e do `nao_apurado` que sai junto do total parcial.

    O antivazamento fica intacto: isto lê os processos **deste** cliente, e nada de terceiros.
    """
    from . import processos as processos_module

    # A formatação de dinheiro vem de `cobranca` e não é reescrita aqui: duas definições de
    # "R$ 10.000,01" divergem no dia em que alguém corrigir uma só, e o sintoma seria a proposta e
    # a cobrança escrevendo o mesmo valor de dois jeitos. O helper deixou de ser privado ao ganhar
    # o segundo consumidor — sublinhado é o aviso de "não importe isto", e importá-lo assim mesmo
    # deixaria uma renomeação em `cobranca.py` quebrar a proposta sem nada apontar para cá.
    from .cobranca import moeda
    from .models import Processo, ProcessoEtapa

    mapeados = list(
        Processo.objects.filter(client=opportunity.client_id, archived_at__isnull=True)
        .prefetch_related(
            # A etapa arquivada por conta própria (o processo vivo, ela não) é uma etapa que
            # alguém removeu do mapa; ressuscitá-la no prompt desfaria a remoção.
            Prefetch("etapas", queryset=ProcessoEtapa.objects.filter(archived_at__isnull=True))
        )[:OPPORTUNITY_PROCESSO_LIMIT]
    )
    if not mapeados:
        return []
    lines = ["Processos da operação do cliente já mapeados no Discovery:"]
    for processo in mapeados:
        lines.append(f"- {processo.name}")
        etapas = [etapa.name for etapa in processo.etapas.all()]
        if etapas:
            lines.append(f"  Etapas: {' → '.join(etapas)}")
        custo = processos_module.custo_do_estado_atual(processo)
        if custo["sustentacao"] != processos_module.SUSTENTADO:
            lines.append(
                "  Custo do estado atual: ainda NÃO sustentado por evidência — o que se sabe deste "
                "processo é hipótese. NÃO afirme número de custo, economia ou retorno para ele."
            )
            continue
        lines.append(
            f"  Custo do estado atual: {moeda(custo['total'])} por mês, sustentado por evidência "
            "registrada como fato."
        )
        if custo["nao_apurado"]:
            # Um total parcial apresentado como fechado é o mesmo erro em escala menor: o que
            # ficou de fora precisa sair junto do número, senão a soma vira o custo inteiro.
            fora = ", ".join(custo["nao_apurado"])
            lines.append(
                f"  Esse total é parcial: {fora} não foi apurado e ficou de fora. Não estime valor "
                "para o que falta."
            )
    return lines


def build_lead_context(lead: Lead, answers: dict | None = None) -> str:
    """Contexto de um lead para qualificação: só dados deste lead + respostas de triagem."""
    lines = [
        f"Nome: {lead.name}",
        f"E-mail: {lead.email}",
    ]
    if lead.company:
        lines.append(f"Empresa: {lead.company}")
    if lead.phone:
        lines.append(f"Telefone: {lead.phone}")
    if lead.message:
        lines.append(f"Mensagem: {lead.message}")
    # O cadastro público do CNPJ, quando o enriquecimento o trouxe (FDD 030). Entra no **mesmo**
    # contexto e não num prompt paralelo: o objetivo declarado é melhorar o `ai_fit`, e um segundo
    # score seria dois números discordando sem que ninguém saiba qual olhar. Vazio é o normal —
    # sem CNPJ, com a flag desligada ou com o fornecedor fora do ar, isto não acrescenta linha
    # nenhuma e a qualificação vê exatamente o que via antes.
    from . import enrichment as enrichment_module

    lines.extend(enrichment_module.summary_lines(lead.enrichment))
    for question, answer in (answers or {}).items():
        if answer:
            lines.append(f"{question}: {answer}")
    return "\n".join(lines)


def _client():  # pragma: no cover - I/O com a OpenAI
    from openai import OpenAI

    # Timeout explícito: o SDK espera 10 min por padrão, e uma destas chamadas roda **dentro do
    # POST público** do formulário de leads (`qualification.qualify_lead`). Sem teto, um dia ruim
    # da OpenAI prende o worker do gunicorn e derruba o site inteiro junto — não só a IA.
    #
    # `max_retries=0` porque o teto tem de ser o que a variável promete. Medido na homologação da
    # rodada 2 (FDD 024): com `AI_TIMEOUT_SECONDS=1`, a resposta levou **5,5 s** — o SDK tenta 3
    # vezes por padrão, então o teto real era `timeout × 3` mais backoff, e com o default de 30 s
    # isso é mais de um minuto e meio segurando um worker por causa de um formulário público.
    # A retentativa escondida também rendia pouco depois desta mesma rodada: agora todo ponto de
    # chamada ou degrada (digest, qualificação) ou devolve 502 dizendo que vale repetir — a
    # retentativa passou a ser visível e do usuário, em vez de invisível e do worker.
    if settings.AI_BASE_URL:
        return OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.AI_BASE_URL,
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=0,
        )
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.AI_TIMEOUT_SECONDS,
        max_retries=0,
    )


def completion_kwargs(system: str, user: str, max_tokens: int | None = None) -> dict:
    """Os argumentos da chamada ao modelo. **Regra, não I/O** — por isso mora fora do `complete`.

    `max_tokens` é opcional de propósito, e não global. A rodada 2 mediu a saída real de cada
    superfície (média ~225 tokens, máximo 854 no contrato): um teto único ou seria alto demais para
    servir de teto, ou truncaria um contrato no meio de uma cláusula. Então ele vale só onde a
    saída tem **forma fixa e pequena** — os dois pontos que consomem JSON curto —, e quem sabe
    disso é quem escreveu o prompt.
    """
    argumentos: dict = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if max_tokens is not None:
        argumentos["max_tokens"] = max_tokens
    return argumentos


# Lotes de 100 na indexação: o corpus tem ~420 trechos, então são cinco chamadas em vez de 420.
EMBED_BATCH = 100


def embed(texts: list[str]) -> list[list[float]]:
    """Vetores para uma lista de textos (FDD 029, ADR 0022).

    Mesma divisão de `complete`: a rede mora em `_client()`, fora da cobertura, e o que sobra aqui
    é a **tradução** de qualquer falha do SDK para `AiProviderError` — regra, e não I/O, então
    testável com o cliente dublado.

    É a **primeira chamada a `embeddings.create` do repositório**: até aqui `ai.py` só falava
    `chat.completions.create`. A dimensão não é passada de propósito — `text-embedding-3-small`
    devolve 1536 nativamente, que é o que a coluna espera, e o parâmetro `dimensions` só existiria
    para encolher, comprando um jeito a mais de errar.
    """
    vetores: list[list[float]] = []
    for inicio in range(0, len(texts), EMBED_BATCH):
        lote = texts[inicio : inicio + EMBED_BATCH]
        try:
            resposta = _client().embeddings.create(model=settings.AI_EMBEDDING_MODEL, input=lote)
        except Exception as exc:  # noqa: BLE001 - o SDK levanta uma família inteira; aqui vira uma só
            raise AiProviderError(str(exc) or exc.__class__.__name__) from exc
        vetores += [item.embedding for item in resposta.data]
    return vetores


def complete(system: str, user: str, max_tokens: int | None = None) -> tuple[str, dict]:
    """Chama o modelo e retorna (texto, uso de tokens).

    A rede mora em `_client()`, que segue fora da cobertura; o que sobra aqui é a **tradução** de
    qualquer falha do SDK para `AiProviderError` — regra, e não I/O, então testável com o cliente
    dublado. É o mesmo movimento que a FDD 024 fez com `all_day_range()` e `parse_freebusy()`, e a
    primeira vez que um caminho de IA sai da região `# pragma: no cover`.
    """
    try:
        response = _client().chat.completions.create(
            model=settings.AI_MODEL, **completion_kwargs(system, user, max_tokens)
        )
    except Exception as exc:  # noqa: BLE001 - o SDK levanta uma família inteira; aqui vira uma só
        # A mensagem do provedor é o produto: é ela que diz se foi chave, cota ou modelo.
        raise AiProviderError(str(exc) or exc.__class__.__name__) from exc
    usage = response.usage
    return (
        response.choices[0].message.content or "",
        {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
        },
    )


def build_cobranca_context(invoice: Invoice, degrau: str = "", hoje: date | None = None) -> str:
    """O contexto do rascunho de tom (FDD 036, camada 4 da RFC 0004).

    **A cerca comercial é a razão de esta função existir separada**, e não de o prompt ser montado
    na view. A RFC 0004 é literal: *"O valor da fatura é do cliente por direito; custo e margem
    **nunca** saem."* Então o que entra aqui é o que o cliente já sabe (quanto, quando venceu, há
    quantos dias) mais o que a casa precisa para escolher o **tom** — tempo de relação, se há
    entrega atrasada e o **nível** de saúde da entrega.

    Três ausências deliberadas, e cada uma é um vazamento que não acontece:

    1. **`actual_value`, ROI e `roi_snapshot` não entram.** São a receita e o retorno como a *casa*
       os calcula, e um parágrafo de cobrança que os cita entrega o número interno junto com a
       cobrança. É o mesmo corte que `_case_lines` já faz com o `roi_snapshot` de terceiro.
    2. **Nível de health, nunca o score nem os sinais.** "atenção" é o que ajusta o tom; "62/100,
       2 entregas atrasadas" é a nossa medição da nossa própria falha, e ela não é assunto de um
       e-mail de cobrança.
    3. **Nenhuma fatura de outro cliente.** Tudo aqui pende desta fatura e deste cliente.

    O corpus interno fica de fora de graça: `grounding` só é preenchido pelo `AgentView`, e o ponto
    de injeção é único (FDD 029).
    """
    from . import cobranca
    from . import health as health_module
    from .models import Milestone, Task

    dia = hoje or timezone.localdate()
    client = invoice.client
    dias = (dia - invoice.due_date).days
    lines = [
        f"Hoje é {dia}.",
        f"Cliente: {client.name}",
        f"Fatura: {invoice.number or 'sem número'}",
        f"Valor: {invoice.amount}",
        f"Vencimento: {invoice.due_date}",
        (
            f"Dias de atraso: {dias}"
            if dias >= 0
            else f"Ainda não venceu: faltam {-dias} dia(s)."
        ),
    ]
    if invoice.description:
        lines.append(f"Referente a: {invoice.description}")
    if degrau:
        lines.append(f"Degrau da régua: {degrau}")
    anos = cobranca.tempo_de_casa_dias(client, dia) // 365
    lines.append(
        f"Tempo de casa: {anos} ano(s) completo(s)" if anos else "Tempo de casa: menos de um ano"
    )
    lines.append(
        "Histórico: já atrasou antes."
        if cobranca.reincidente(client, dia, ignorando=invoice)
        else "Histórico: nunca atrasou antes."
    )
    project = invoice.project
    if project is not None:
        # **Só o nível.** Ver a razão 2 no docstring.
        lines.append(f"Saúde da entrega: {health_module.assess_project_health(project)['level']}")
        atrasados = sum(
            1
            for item in [
                *Milestone.objects.filter(project=project, archived_at__isnull=True),
                *Task.objects.filter(project=project, archived_at__isnull=True),
            ]
            if item.is_overdue
        )
        # Se a casa está devendo entrega, cobrar com tom firme é pedir para ouvir sobre o atraso
        # dela — e quem redige precisa saber disso antes de escrever, não depois da resposta.
        lines.append(
            f"Entregas atrasadas neste projeto: {atrasados}"
            if atrasados
            else "Não há entrega atrasada neste projeto."
        )
    return "\n".join(lines)


def build_resposta_de_cobranca_context(activity: Activity) -> str:
    """O que a pessoa que atendeu registrou sobre a resposta do cliente (FDD 036).

    Só a `Activity` e a fatura a que ela se refere. Classificar não precisa de mais que isso, e
    tudo o que sobrasse aqui seria contexto de cliente entrando num prompt sem razão declarada.
    """
    lines = [
        f"Cliente: {activity.client.name}",
        f"Tipo de interação: {activity.get_kind_display()}",
        f"Data: {activity.happened_on}",
        f"Resumo: {activity.summary}",
    ]
    if activity.notes:
        lines.append(f"Detalhes: {activity.notes}")
    invoice = activity.invoice
    if invoice is not None:
        lines.append(
            f"Fatura em questão: {invoice.number or 'sem número'}, {invoice.amount}, "
            f"vencimento {invoice.due_date}, situação {invoice.get_status_display()}"
        )
    return "\n".join(lines)
