"""Camada de IA (OpenAI) atrás de flag.

Mesma estratégia do `apps/core/drive.py`: o SDK é importado de forma lazy e só é chamado
quando `AI_ENABLED`. As funções de montagem de contexto e o limite de uso são puras e
testáveis; a chamada ao modelo fica fora da cobertura (`# pragma: no cover`).

Antivazamento: o contexto passado ao modelo contém apenas dados do recurso em questão
(nunca o conteúdo binário dos documentos — só os nomes) e o system prompt orienta o modelo
a responder somente com base no material fornecido.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from . import flags

if TYPE_CHECKING:
    from .models import Lead, Meeting, Opportunity, Project, User

# Limite de caracteres da transcrição enviada ao modelo (controle de tokens/custo).
MEETING_TRANSCRIPT_LIMIT = 12000


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
    return "\n".join(lines)


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
