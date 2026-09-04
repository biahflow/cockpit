"""O convite para o cliente marcar o Discovery, e o token que abre a página pública.

Fecha o beco em que o ciclo do Design Partner terminava: o acordo era assinado, o mandato
nascia (`design_partner.abrir_engagement_do_acordo`) e o cliente não recebia nada. Aqui o
mandato recém-nascido vira um e-mail com um link, e o link vira a escolha do horário
(`booking.book_discovery`).

Superfície governada pelo DAP `docs/design/dap-agendamento-discovery-r1/`, r1, decisões
**A1 · B1 · C1 · D1 · E2**. Três coisas moram neste módulo porque as três são a mesma decisão:

- **O token.** `django.core.signing`, escopado a **um** mandato, com salt próprio e validade
  alinhada ao horizonte de oferta — não adianta um link viver mais do que a janela que ele
  mostra. O salt é próprio, e não o `booking` da pré-venda, porque salt compartilhado deixaria
  um token servir para a outra rota: quem recebeu o convite do Discovery passaria a agendar
  como lead qualificado, e o contrário também.
- **O texto do convite.** Constante de código, revisada uma vez — é isso que autoriza o e-mail
  a sair sozinho, o mesmo desenho do `Degrau` de `cobranca.py` (ADR 0031). Texto puro: não há
  template HTML de e-mail neste produto, e introduzir um por uma mensagem de sete linhas seria
  dívida de renderização.
- **O envio, best-effort.** A assinatura não pode falhar porque o SMTP caiu. O convite é o
  degrau seguinte à decisão do signatário, não parte dela.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.utils import timezone

from . import flags, kickoff, notifications
from .booking import BOOKING_HORIZON_DAYS

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import Booking, Engagement, Project


def is_enabled() -> bool:
    return flags.is_enabled("discovery_booking")


# Salt **próprio**, distinto do `BOOKING_TOKEN_SALT` da pré-venda (`views.py`). Ver a docstring.
DISCOVERY_BOOKING_TOKEN_SALT = "discovery-booking"
# Alinhado ao horizonte de oferta: um link que sobrevive à janela que ele mostra abre numa página
# sem horário nenhum, e o cliente lê "sem horários" quando o que houve foi o link vencer.
DISCOVERY_BOOKING_TOKEN_MAX_AGE = BOOKING_HORIZON_DAYS * 24 * 3600


# O título da `Meeting` que a reserva vira no projeto. Constante porque é o que a tela e o portal
# do cliente leem como "a sessão", e um literal solto na action divergiria do texto do template.
TITULO_DA_SESSAO_DE_DISCOVERY = "Sessão de Discovery"


class TokenExpirado(Exception):
    """O link venceu. Estado próprio porque a página diz outra coisa (D1)."""


class TokenInvalido(Exception):
    """A assinatura não confere **ou** o mandato não existe — e a resposta é a mesma para os dois.

    Distinguir "assinatura errada" de "mandato inexistente" para quem não está autenticado é dar
    retorno a quem sonda (decisão D1 do DAP).
    """


def token_for(engagement: Engagement) -> str:
    return signing.dumps({"engagement": engagement.pk}, salt=DISCOVERY_BOOKING_TOKEN_SALT)


def engagement_from_token(token: str) -> Engagement:
    """O mandato que o token autoriza. Levanta `TokenExpirado`/`TokenInvalido`."""
    from .models import Engagement

    try:
        payload = signing.loads(
            token, salt=DISCOVERY_BOOKING_TOKEN_SALT, max_age=DISCOVERY_BOOKING_TOKEN_MAX_AGE
        )
    except signing.SignatureExpired as exc:
        raise TokenExpirado from exc
    except signing.BadSignature as exc:
        raise TokenInvalido from exc
    engagement = Engagement.objects.filter(
        pk=payload.get("engagement"), archived_at__isnull=True
    ).select_related("account").first()
    if engagement is None:
        raise TokenInvalido
    return engagement


def discovery_agendado(engagement: Engagement) -> Booking | None:
    """A sessão de Discovery deste mandato, marcada ou já realizada (decisão C1: não remarca).

    **Realizada conta**, e a exclusão é só de `CANCELED`. Filtrar por `SCHEDULED` abriria um buraco
    que nenhuma das duas metades enxerga sozinha: o job `sessions_held` passa a sessão para `held`
    no dia seguinte ao dela, e o link do convite vale duas semanas — o cliente reabriria a página
    depois da conversa, encontraria horários oferecidos de novo e marcaria um **segundo** Discovery,
    ganhando um convite do Google para uma sessão que ninguém vai fazer.

    A pergunta que esta função responde não é "há sessão no futuro?", é **"este mandato já teve seu
    Discovery marcado?"** — e o que responde "não" a ela é o cancelamento, não o tempo passar.
    """
    from .models import Booking

    return (
        Booking.objects.filter(engagement=engagement, archived_at__isnull=True)
        .exclude(status=Booking.Status.CANCELED)
        .order_by("starts_at")
        .first()
    )


def registrar_sessao_no_projeto(project: Project, engagement: Engagement) -> Booking | None:
    """A sessão já marcada vira fato do projeto recém-criado. Devolve a reserva, ou `None`.

    Sem isto, três coisas ficavam erradas ao mesmo tempo pela **mesma** razão — o `Booking` do
    Discovery não atravessava para o projeto:

    - o painel "Saúde da relação" dizia *"Próxima reunião: A agendar"* com a sessão marcada, porque
      `build_account_overview` lê `Meeting` e o agendamento cria `Booking`: dois modelos para
      "reunião marcada", e o painel só conhece um. A `Meeting` é a tradução, não uma segunda
      verdade — a reserva continua sendo quem bloqueia o horário na agenda;
    - a tarefa "agendar a sessão" nascia pendente logo depois de a automação a ter cumprido;
    - o cronograma não se ancorava na sessão.

    O terceiro fica **de fora aqui de propósito**: as datas do projeto vêm do formulário aprovado
    (DAP `dap-engagement-r3`, C1), e sobrescrevê-las no servidor devolveria 201 mudando em silêncio
    o que quem preencheu escolheu. Quem pré-preenche é a tela, lendo `discovery_scheduled_at`.

    A data sai no **fuso local** (`localtime`): `Meeting.date` é `DateField` e a reserva é
    `DateTimeField`, então converter em UTC jogaria uma sessão das 21h para o dia seguinte.

    Chamada dentro da transação de quem cria o projeto: é escrita no banco, não efeito externo.
    """
    from .models import Meeting, Service, Task

    reserva = discovery_agendado(engagement)
    if reserva is None:
        return None
    # **A sessão é do projeto que É o Discovery, e de mais nenhum.** Um mandato origina vários
    # projetos por desenho (ADR 0050), e a reserva continua `scheduled` depois que a sessão
    # aconteceu — nada a fecha. Sem esta guarda, o projeto de Feasibility criado semanas depois
    # herdaria uma "Sessão de Discovery" que não é dele: a **mesma** reunião do mundo aparecendo
    # duas vezes, em dois cronogramas, e contando duas vezes no "Próxima reunião" da conta.
    #
    # Projeto sem degrau não recebe a sessão, e é a resposta honesta: se ninguém disse qual passo
    # da escada este projeto é, o sistema não tem como afirmar que a sessão marcada é a dele.
    degrau = project.service.tier if project.service else ""
    if degrau != Service.Tier.DISCOVERY_SPRINT:
        return None

    Meeting.objects.create(
        project=project,
        title=TITULO_DA_SESSAO_DE_DISCOVERY,
        date=timezone.localtime(reserva.starts_at).date(),
        meeting_url=reserva.calendar_link or "",
    )
    # Uma a uma, e não `update()`: é `WorkItem.save()` que carimba `completed_at`, e um `update()`
    # deixaria a tarefa concluída sem data de conclusão — estado que o cronograma do portal lê.
    for tarefa in Task.objects.filter(
        project=project,
        title=kickoff.TAREFA_DE_AGENDAR_O_DISCOVERY,
        archived_at__isnull=True,
    ).exclude(status=Task.Status.DONE):
        tarefa.status = Task.Status.DONE
        tarefa.save(update_fields=["status", "completed_at", "updated_at"])
    return reserva


# O Discovery Sprint dura de **5 a 7 dias** — é o que o convite promete ao cliente — e o template
# de kickoff do degrau fecha no Executive Readout em D+7 (`kickoff.KICKOFF_TEMPLATES`). Constante
# nomeada e não `+ 7` solto na criação: o número responde "quanto dura o Discovery", e um literal
# no meio da linha não diz isso a quem for encurtar o sprint depois.
DURACAO_DO_DISCOVERY_SPRINT_EM_DIAS = 7

# A oração que o kickoff anuncia no e-mail e na notificação. Aqui não houve venda **nem** clique de
# ninguém da casa: quem deu a partida foi o cliente.
ORIGEM_DA_SESSAO_MARCADA = "quando o cliente marcou a sessão de Discovery"


def _avisar_a_casa(engagement: Engagement, mensagem: str) -> None:
    """Diz a quem responde pelo mandato que o projeto ficou para a mão. **Nunca levanta.**

    Quem chama já está no caminho da falha, e a resposta do agendamento é 201 de qualquer jeito
    (ver `abrir_projeto_da_sessao`): deixar o aviso derrubar a rota pública seria trocar o defeito
    silencioso por um erro na cara do cliente que acabou de escolher o horário.
    """
    try:
        notifications.notify(
            [engagement.owner], "booking", mensagem, f"/contas/{engagement.account_id}"
        )
    except Exception:  # noqa: BLE001 - ver docstring: o aviso não derruba o agendamento
        logger.exception("aviso do Discovery do mandato %s não foi gravado", engagement.pk)


def abrir_projeto_da_sessao(engagement: Engagement, reserva: Booking) -> Project | None:
    """O projeto nasce no instante em que o cliente marca o horário. Devolve-o, ou `None`.

    Era o último passo manual do caminho feliz: alguém abria o detalhe da conta e clicava em
    "Novo projeto". No instante da reserva **tudo já está determinado** — o mandato existe, o
    degrau é o Discovery Sprint (é para isso que o acordo foi assinado) e as datas saem da sessão,
    porque o dia dela é o dia 0.

    **Best-effort, e essa é a decisão inteira.** Falhe o que falhar aqui, o agendamento segue 201:
    o cliente marcou o horário, e o projeto é consequência interna da casa — derrubar a reserva
    por causa dela seria punir o cliente por um problema nosso. Fica o log e o aviso interno, no
    molde de `kickoff.finalize`.

    Duas condições, e as duas são necessárias:

    - **nenhum projeto vivo do degrau no mandato.** É a mesma pergunta que a guarda de duplo clique
      faz, e pela mesma razão: um mandato origina vários projetos por desenho (ADR 0050), mas o
      Discovery Sprint dele é um só;
    - **existe um `Service` ativo no degrau.** Sem ele o projeto cairia no template genérico de
      `kickoff.template_for` e nasceria **sem os marcos que são a metodologia** — sem walkthrough,
      sem custo do estado atual, sem Executive Readout — e nada ficaria vermelho. Criar assim é
      pior do que não criar: a reserva do cliente continua valendo e alguém cria o projeto na mão,
      sabendo o que faltou.
    """
    try:
        project = _criar_projeto_da_sessao(engagement, reserva)
    except Exception:  # noqa: BLE001 - ver docstring: o projeto não derruba o agendamento
        logger.exception(
            "projeto do Discovery do mandato %s não foi criado (reserva %s)",
            engagement.pk,
            reserva.pk,
        )
        _avisar_a_casa(
            engagement,
            f"{engagement.account.name} marcou o Discovery, mas o projeto não nasceu — "
            "veja o log. Crie o projeto na mão.",
        )
        return None
    if project is None:
        return None
    try:
        # Fora da transação, como nos outros dois chamadores: são efeitos externos (Drive, e-mail).
        # **Em `try` próprio, e não junto do de cima**: o projeto já existe aqui, e um anúncio que
        # falha não pode fazer o aviso interno dizer "o projeto não nasceu" — mandaria alguém criar
        # na mão um projeto que está lá.
        kickoff.finalize(project, origem=ORIGEM_DA_SESSAO_MARCADA)
    except Exception:  # noqa: BLE001 - o anúncio do kickoff não desfaz o projeto
        logger.exception("kickoff do projeto %s do Discovery não completou", project.pk)
    return project


def _criar_projeto_da_sessao(engagement: Engagement, reserva: Booking) -> Project | None:
    from .models import Project, Service

    ja_existe = Project.objects.filter(
        engagement=engagement,
        service__tier=Service.Tier.DISCOVERY_SPRINT,
        archived_at__isnull=True,
    ).exists()
    if ja_existe:
        return None
    # No máximo um, pela restrição de banco "um `Service` ativo por `tier`" — o `first()` é para
    # o tipo, não para desempate.
    degrau = Service.objects.filter(
        tier=Service.Tier.DISCOVERY_SPRINT, active=True, archived_at__isnull=True
    ).order_by("id").first()
    if degrau is None:
        logger.warning(
            "Discovery do mandato %s agendado sem degrau ativo no catálogo: projeto não criado",
            engagement.pk,
        )
        _avisar_a_casa(
            engagement,
            f"{engagement.account.name} marcou o Discovery, mas o projeto não nasceu: não há "
            "Discovery Sprint ativo no catálogo. Crie o degrau e o projeto na mão.",
        )
        return None

    # A data **local** da reserva, e não a UTC: uma sessão das 21h viraria o dia seguinte, e o
    # cronograma inteiro nasceria deslocado. É a mesma armadilha de `registrar_sessao_no_projeto`.
    inicio = timezone.localtime(reserva.starts_at).date()
    conta = engagement.account

    def salvar() -> Project:
        return Project.objects.create(
            engagement=engagement,
            name=f"Discovery Sprint — {conta.name}",
            # **O dono é o do mandato, e é a diferença que mais confunde quem comparar com a
            # action.** Lá o dono é `request.user`; aqui a rota é pública e não há usuário
            # autenticado nenhum — quem responde pelo trabalho é quem responde pelo mandato.
            owner=engagement.owner,
            service=degrau,
            start_date=inicio,
            due_date=inicio + timedelta(days=DURACAO_DO_DISCOVERY_SPRINT_EM_DIAS),
        )

    return kickoff.criar_projeto_do_mandato(engagement, salvar)


@dataclass(frozen=True)
class Convite:
    """O texto que chega ao cliente. `str.format` com `{nome}` e `{link}`."""

    assunto: str
    corpo: str


# Redação **E2-r2** do DAP `dap-agendamento-discovery-r1`, aprovada em 2026-09-02. Mudar este
# texto é mudar o que a casa diz no primeiro contato depois da assinatura — passa por revisão nova
# do pacote, não por julgamento na hora.
#
# A r1 saiu informativa e o primeiro teste em uso mostrou o custo: o momento é de **comemoração**
# — alguém acabou de assinar uma parceria — e o texto tratava isso como notificação de sistema. A
# r2 celebra o aceite sem exagerar: nenhuma exclamação, nenhum superlativo, nenhuma promessa de
# resultado. O que mudou é de onde a mensagem fala.
#
# "Não precisa preparar nada — é só chegar" fica, e é a frase mais funcional do texto: ela remove
# a hesitação de quem adia agendamento por achar que precisa se preparar antes.
CONVITE_DO_DISCOVERY = Convite(
    assunto="É oficial: nossa parceria começou",
    corpo=(
        "Olá, {nome}.\n\n"
        "Que bom ter você com a gente. O acordo está assinado — e a partir de agora a Biahflow "
        "entra no seu processo para descobrir onde está o trabalho que dói e o que dá para "
        "transformar.\n\n"
        "O primeiro passo é o Discovery, e ele começa com uma conversa. Escolha o melhor "
        "horário:\n"
        "{link}\n\n"
        "Vamos percorrer o processo junto com quem executa ele no dia a dia. Não precisa preparar "
        "nada — é só chegar.\n\n"
        "Estamos animados para começar. Qualquer coisa, é só responder este e-mail.\n"
    ),
)


def link_do_convite(engagement: Engagement) -> str:
    """A rota pública da SPA, montada como o convite de acesso monta a dele (`views.py`)."""
    return f"{settings.FRONTEND_BASE_URL}/agendar/{token_for(engagement)}"


def _primeiro_nome(engagement: Engagement, signer_email: str) -> str:
    """Como chamar quem assinou.

    `SignatureRequest` guarda o e-mail de quem assina e **nunca** o nome — mas a conta guarda os
    dois, e é por e-mail que os dois registros se encontram. O board aprovado abre com "Olá,
    Sarah.", primeiro nome, e resolver isso pelo nome da conta ("Olá, Rio Home Care.") seria
    trocar a pessoa pela organização no ato mais pessoal do fluxo.

    Cai para o nome da conta quando quem assinou não é contato cadastrado: acontece, e nomear a
    organização é melhor que abrir com um e-mail cru ou com uma saudação sem nome.
    """
    from .models import Contact

    contato = (
        Contact.objects.filter(
            account_id=engagement.account_id,
            email__iexact=signer_email,
            archived_at__isnull=True,
        )
        .exclude(first_name="")
        .order_by("id")
        .first()
    )
    return contato.first_name if contato else engagement.account.name


def texto_do_convite(engagement: Engagement, signer_email: str = "") -> tuple[str, str]:
    """Assunto e corpo já preenchidos, com o nome de quem assinou quando a casa o conhece."""
    campos = {
        "nome": _primeiro_nome(engagement, signer_email),
        "link": link_do_convite(engagement),
    }
    return (
        CONVITE_DO_DISCOVERY.assunto.format(**campos),
        CONVITE_DO_DISCOVERY.corpo.format(**campos),
    )


def enviar_convite(engagement: Engagement, signer_email: str) -> bool:
    """Manda o convite a quem assinou. Best-effort: nunca levanta, e diz no log quando não saiu.

    `fail_silently=True` e conferência do retorno, no molde do `digest.py`: com o silêncio ligado
    `send_mail` devolve `0` quando o SMTP recusa, e somar um envio ali faria o log afirmar uma
    entrega que não houve. O `except` largo em volta é a diferença entre este chamador e os
    outros: quem chama é `esign.apply_decision`, e uma assinatura **não pode** ficar por aplicar
    porque o servidor de e-mail caiu — o webhook do fornecedor reentregaria em laço um evento que
    já teve efeito.
    """
    if not is_enabled() or not signer_email:
        return False
    assunto, corpo = texto_do_convite(engagement, signer_email)
    try:
        enviados = send_mail(assunto, corpo, None, [signer_email], fail_silently=True)
    except Exception:  # noqa: BLE001 - ver docstring: o convite não derruba a assinatura
        logger.exception("convite do Discovery do mandato %s não saiu", engagement.pk)
        return False
    if not enviados:
        logger.warning(
            "convite do Discovery do mandato %s não entregue (SMTP recusou ou não respondeu)",
            engagement.pk,
        )
        return False
    return True
