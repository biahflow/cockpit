"""Resumo diário (digest) por IA — Go-live/Hypercare (RFC 0002, FDD 010).

Reúne os itens do dia de cada usuário e envia um resumo por e-mail. Com a IA ligada, o texto é
redigido pelo modelo (auditado em `AiInteraction`); desligada, cai no resumo estruturado. Tudo
atrás da flag `email`.

O digest tem **duas seções** (FDD 010, FDD 018):

- **Seus itens** — o que a pessoa possui, atrasado ou a vencer em 7 dias.
- **Do seu projeto** — o que está atrasado nos projetos de que ela *participa*, de outras pessoas.

A segunda seção existe porque, até aqui, o digest filtrava só por `owner=` e quem entrava numa
equipe sem ser dono de nada recebia um digest vazio — consequência que a FDD 018 registrou em
aberto e que só passou a doer quando a FDD 023 fez o digest realmente rodar todo dia.

Duas regras que parecem detalhe e não são:

- **Participação não é visibilidade.** A seção da equipe consulta `ProjectMember` diretamente, e
  **não** `Project.objects.visible_to()`: esta devolve *tudo* para admin e vendas, e usá-la encheria
  a caixa de um admin com o portfólio inteiro da casa, todo dia. Visibilidade responde "posso ver?";
  aqui a pergunta é "isto é meu problema?".
- **A seção própria passou a respeitar o acesso** (`project_scope_q`). Nada reatribui os itens
  quando alguém sai de uma equipe, então quem saiu continua `owner` das suas tarefas — e o digest
  seguia mandando título e vencimento de um projeto que a pessoa já não abre. Para admin e vendas
  a função devolve `Q()` vazio, então ninguém perde o que recebia.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.mail import send_mail
from django.utils import timezone

from . import ai, flags

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import User, WorkItem

_SYSTEM = (
    "Você escreve um resumo diário curto e acionável em português a partir dos itens "
    "fornecidos (marcos e tarefas). O material vem em duas seções: os itens da própria pessoa e "
    "os itens atrasados dos projetos de que ela participa, que são de outras pessoas — não "
    "misture as duas, e não atribua a ela o que está na segunda. Priorize o que está atrasado; "
    "use apenas o material dado."
)

# Teto por bloco. Sem ele, um projeto com 80 itens abertos vira uma parede de texto diária para
# cada pessoa da equipe — e um digest que ninguém lê é o mesmo que digest nenhum.
_MAX_LINHAS = 10


def _linhas(items: list[WorkItem], *, vencido: bool) -> list[str]:
    """As primeiras `_MAX_LINHAS` de um bloco, com o resto somado em uma linha final."""
    verbo = "venceu" if vencido else "vence"
    linhas = [f"- {item.title} ({verbo} {item.due_date})" for item in items[:_MAX_LINHAS]]
    if len(items) > _MAX_LINHAS:
        linhas.append(f"- ... e mais {len(items) - _MAX_LINHAS}")
    return linhas


def build_user_digest_context(user: User) -> str:
    """Monta o material do digest da pessoa. Vazio quando não há nada a reportar."""
    from .models import Milestone, Project, Task, project_scope_q

    today = timezone.localdate()
    soon = today + timedelta(days=7)

    # Projetos de que a pessoa participa — critério de relevância, não de acesso (ver o docstring
    # do módulo). Materializado uma vez e reusado nos dois modelos: o laço abaixo não pode virar
    # uma consulta por projeto.
    member_project_ids = list(
        Project.objects.filter(
            members__user=user,
            members__archived_at__isnull=True,
            archived_at__isnull=True,
        ).values_list("id", flat=True)
    )

    meus: list[str] = []
    da_equipe: list[str] = []

    # O adjetivo acompanha o gênero do rótulo: "Marcos atrasados", "Tarefas atrasadas". Isto é
    # texto que chega por e-mail a um cliente interno todo dia — concordância importa.
    for label, atrasados, model in (
        ("Marcos", "atrasados", Milestone),
        ("Tarefas", "atrasadas", Task),
    ):
        abertos = model.objects.filter(archived_at__isnull=True).exclude(status=model.Status.DONE)

        # `.distinct()`: o join com `members` dentro de `project_scope_q` multiplica linhas.
        proprios = list(abertos.filter(project_scope_q(user, "project"), owner=user).distinct())
        overdue = [item for item in proprios if item.due_date < today]
        upcoming = [item for item in proprios if today <= item.due_date <= soon]
        if overdue:
            meus.append(f"{label} {atrasados}:")
            meus += _linhas(overdue, vencido=True)
        if upcoming:
            meus.append(f"{label} a vencer nos próximos 7 dias:")
            meus += _linhas(upcoming, vencido=False)

        # Só atrasados, e só de outras pessoas: o que já apareceu acima não se repete, e "a vencer
        # em 7 dias" do projeto inteiro seria volume sem sinal.
        equipe = list(
            abertos.filter(project_id__in=member_project_ids, due_date__lt=today).exclude(owner=user)
        )
        if equipe:
            da_equipe.append(f"{label} {atrasados}:")
            da_equipe += _linhas(equipe, vencido=True)

    if not meus and not da_equipe:
        return ""

    blocos: list[str] = []
    if meus:
        blocos.append("\n".join(["Seus itens", *meus]))
    if da_equipe:
        blocos.append("\n".join(["Do seu projeto (itens de outras pessoas)", *da_equipe]))
    return "\n\n".join(blocos)


def send_daily_digest() -> int:
    """Envia o digest a cada usuário ativo com itens a reportar. Retorna quantos foram enviados."""
    from .models import AiInteraction, User

    if not flags.is_enabled("email"):
        return 0
    sent = 0
    for user in User.objects.filter(is_active=True):
        if not user.email:
            continue
        context = build_user_digest_context(user)
        if not context:
            continue
        # A redação por IA é enfeite; a entrega é o produto. A chamada ficava crua **dentro deste
        # laço**: um 429 no terceiro usuário levantava e matava o resto da fila — quem já tinha
        # sido iterado recebia, o resto não recebia nada, e a contagem se perdia junto. O agendador
        # não cai (ele isola o job de propósito), e é isso que torna a falha ruim: vira uma linha
        # de log, o carimbo do dia é gravado assim mesmo e não há retentativa até amanhã.
        #
        # A degradação certa já estava escrita aqui: cair no mesmo texto simples do ramo "IA
        # desligada", que é o desenho que o `qualify_lead` segue desde a FDD 024 — falha de IA
        # degrada para o comportamento de IA desligada.
        text = context
        if ai.is_enabled():
            try:
                text, usage = ai.complete(_SYSTEM, context)
            except ai.AiProviderError:
                logger.exception("digest de %s sai sem redação por IA (fornecedor falhou)", user.username)
            else:
                AiInteraction.objects.create(
                    user=user, feature="daily_digest",
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
        # `send_mail` devolve quantas mensagens saíram, e com `fail_silently=True` isso é `0`
        # quando o SMTP recusa ou não existe. Somar 1 aqui fazia o scheduler logar
        # "Digests enviados: 12" com zero entregues — o mesmo modo de falha do agendador que não
        # existia, uma camada abaixo: o número dizia que estava tudo bem.
        #
        # `fail_silently` continua ligado de propósito: um endereço inválido não pode interromper
        # o envio para o resto da casa. O que muda é a contagem parar de mentir.
        enviados = send_mail(
            "Seu resumo diário — Portal Biahflow", text, None, [user.email], fail_silently=True
        )
        if not enviados:
            logger.warning("digest não entregue a %s (SMTP recusou ou não respondeu)", user.username)
            continue
        sent += 1
    return sent
