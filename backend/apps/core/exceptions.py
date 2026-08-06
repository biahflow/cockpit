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
"""

from __future__ import annotations

from rest_framework.exceptions import APIException


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
