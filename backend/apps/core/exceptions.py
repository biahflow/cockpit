"""Falha de fornecedor externo vira **502**, nunca 500 (FDD 024).

A regra é uma só: quando o defeito é de quem está do outro lado da rede, o pedido não foi malfeito
e o erro não é nosso — 502 diz de quem é o problema **e** que vale repetir, enquanto 500 diz "algo
quebrou aqui" e não sugere nada a quem lê.

Ela nasceu no upload do Drive (FDD 024), voltou no convite por e-mail (rodada 1), de novo nas dez
superfícies de IA (rodada 2) e agora no Drive e no Calendário (rodada 3). Quatro expressões da
mesma regra em três módulos era o momento de parar: este repositório trata *uma regra, uma
expressão* como princípio — é o que a ADR 0010 faz com `visible_to`.

**As mensagens continuam distintas por fornecedor, de propósito.** O texto é o que a pessoa lê na
tela, e "não foi possível enviar o e-mail" não serve para uma proposta que não gerou. O que se
compartilha é o status e o motivo dele, não a redação.

Não confundir com `calendar_sync.CalendarUnavailable`, que é outra coisa: o sinal de *falhar
fechado* do free/busy — não conseguimos ler a agenda, então nada pode ser afirmado sobre ela — e
vira **503**, porque ali o recurso é que está indisponível, não o fornecedor que recusou.

No fim do módulo, a mesma regra virada para dentro: `api_exception_handler` traduz o
`ProtectedError` do banco em **409** (FDD 025). Também ali um 500 diria "quebrou aqui" sobre uma
recusa perfeitamente normal.
"""

from __future__ import annotations

from typing import Any

from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback


class UpstreamUnavailable(APIException):
    """Um fornecedor externo falhou. Subclasse por fornecedor, para a mensagem ser útil."""

    status_code = 502
    default_detail = "Um serviço externo não respondeu. Tente de novo em instantes."
    default_code = "upstream_unavailable"


class EmailUndeliverable(UpstreamUnavailable):
    """O SMTP recusou uma mensagem sem a qual a operação não faz sentido.

    O caso que a criou é o convite (rodada 1): ele **é** o e-mail, porque quem recebe não tem outro
    caminho para o token — então gravar a linha e não enviar deixava um convite válido que ninguém
    recebeu, e cada tentativa criava mais um.
    """

    default_detail = "Não foi possível enviar o e-mail. Verifique o SMTP e tente de novo."
    default_code = "email_undeliverable"


class AiProviderUnavailable(UpstreamUnavailable):
    """A OpenAI recusou, expirou ou não respondeu (rodada 2)."""

    default_detail = (
        "O serviço de IA não respondeu. Nada foi cobrado nem gravado — tente de novo em instantes."
    )
    default_code = "ai_provider_unavailable"


class DriveUnavailable(UpstreamUnavailable):
    """O Google Drive recusou a operação.

    Nasceu no upload, onde um 500 mudo fazia o arquivo do usuário desaparecer sem explicação
    (FDD 024); a rodada 3 estendeu ao **download**, que tinha ficado cru — o caminho em que a
    pessoa tenta pegar de volta o próprio arquivo. Quem chama passa um `detail` mais específico
    quando souber dizer melhor.
    """

    default_detail = "O Google Drive não respondeu agora. Tente de novo em instantes."
    default_code = "drive_unavailable"


class CalendarProviderUnavailable(UpstreamUnavailable):
    """O Google Calendar recusou a operação (rodada 3).

    Distinta da `calendar_sync.CalendarUnavailable`: aquela é o free/busy falhando fechado (503,
    "não sei o que há na agenda"); esta é o fornecedor recusando uma escrita ou uma leitura.
    """

    default_detail = "O Google Calendar não respondeu agora. Tente de novo em instantes."
    default_code = "calendar_unavailable"


class EsignUnavailable(UpstreamUnavailable):
    """O fornecedor de assinatura não aceitou a solicitação (rodada 4).

    Aqui o 502 vale por um motivo a mais que nas irmãs: a solicitação **é** o pedido ao fornecedor.
    Uma linha gravada sem referência dele é uma assinatura que ninguém vai assinar, que o webhook
    nunca poderá fechar, e sobre a qual o lembrete ainda cobraria uma pessoa de verdade.
    """

    default_detail = (
        "O fornecedor de assinatura não aceitou a solicitação. Nada foi registrado — "
        "tente de novo em instantes."
    )
    default_code = "esign_unavailable"


class GitHubIssuesUnavailable(UpstreamUnavailable):
    """A API do GitHub recusou o provisionamento da Issue de engenharia (FDD 040).

    A view de create prefere persistir `failed` e devolver 201 com o id — quem opera precisa
    do registro para o retry. Esta exceção existe para o caso em que a rota quiser traduzir
    a falha do fornecedor em 502, no mesmo molde das irmãs.
    """

    default_detail = (
        "O GitHub não aceitou o provisionamento da issue. Tente de novo em instantes."
    )
    default_code = "github_issues_unavailable"


class PaymentsUnavailable(UpstreamUnavailable):
    """O gateway de pagamento não aceitou a cobrança (FDD 028).

    Vale aqui o mesmo motivo a mais que na assinatura, com dinheiro em cima: a emissão **é** o
    pedido ao fornecedor. Uma fatura marcada como emitida sem link pagável é cobrança que ninguém
    consegue pagar, que o webhook nunca poderá fechar, e que ainda assim entra no total em aberto
    que alguém vai olhar para decidir alguma coisa.
    """

    default_detail = (
        "O gateway de pagamento não aceitou a cobrança. Nada foi emitido — "
        "tente de novo em instantes."
    )
    default_code = "payments_unavailable"


class StateConflict(APIException):
    """Recusado porque o **estado** do sistema não permite, não porque o pedido está malfeito.

    409, não 400: o pedido está bem formado e a permissão existe — o que impede é o estado, e é
    ele que muda para o pedido passar. Um 400 mandaria quem lê procurar erro no corpo.

    Nasceu como `ArchiveConflict`, do arquivamento, e o nome ficou estreito: a exclusão **real**
    (etapa do pipeline, fase da jornada) recusa pela mesma razão e com a mesma forma — contagem do
    que depende, mais o caminho de saída. Ver FDD 025.

    Mora aqui, e não nas views, desde a FDD 033: a recusa do decision gate e a do quality gate são
    regra de **domínio** e vivem em `journey.py`, que precisa continuar importável sem request —
    importar `views` de lá fecharia o ciclo (`views` importa `journey`). Este módulo não importa
    nada do domínio, então é o único lugar de onde os dois lados podem levantar a mesma exceção.
    """

    status_code = status.HTTP_409_CONFLICT


class InvalidInput(APIException):
    """Recusado porque o **pedido** está malfeito, não porque o estado impede.

    400, e é a contrapartida exata do `StateConflict` logo acima: lá o corpo está certo e o
    estado é que muda para o pedido passar; aqui é o corpo que muda. Devolver 409 para um valor
    inválido mandaria quem lê procurar num estado que está perfeitamente bom.

    Nasceu com a ADR 0053, quando a validação do decision gate desceu da view para `journey.py`:
    o vocabulário aceito depende da **fase ativa**, que só `journey.apply_gate` conhece, e a
    invariante pertence ao domínio pelo mesmo motivo que `Opportunity.clean()`/`Project.clean()`
    — shell, admin e migração não passam por rota. Mora aqui, e não em `journey.py`, pela razão
    do módulo: este é o único que não importa nada do domínio.
    """

    status_code = status.HTTP_400_BAD_REQUEST


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Handler do DRF com `ProtectedError` traduzido para **409** (FDD 025).

    Mesma regra do módulo, outro lado da rede: o DRF só conhece as próprias exceções, então tudo
    o mais sobe como 500 — inclusive o `ProtectedError`, que não é falha nenhuma, e sim o banco
    recusando apagar uma linha da qual outra depende. Sem tradução, um clique legítimo em
    "Excluir" virava "Não foi possível concluir a operação." na tela **e** um evento no Sentry,
    porque o SPA reporta todo status ≥ 500 (`api.ts`) — escondendo a única informação útil.

    409 pela razão do `StateConflict`: o pedido está bem formado e a permissão existe, o que
    impede é o estado. Isto aqui é **rede**, não a mensagem boa: quem sabe o que está em jogo é a
    view, e `perform_destroy` recusa antes, com contagem e caminho de saída. A rede existe porque
    são doze FKs `PROTECT` no `models.py` e nada obriga a próxima rota de exclusão a lembrar da
    sua.
    """
    if isinstance(exc, ProtectedError):
        set_rollback()  # como o handler do DRF faz; sem isto a transação da requisição vaza
        return Response(
            {"detail": "Outro registro ainda depende deste. Remova o vínculo antes de excluir."},
            status=status.HTTP_409_CONFLICT,
        )
    return exception_handler(exc, context)
