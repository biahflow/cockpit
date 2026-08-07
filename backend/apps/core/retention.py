"""Retenção de dado pessoal arquivado (LGPD).

O portal sempre soube **arquivar** e nunca soube **esquecer**: `archived_at` tira a linha das telas
e ela fica para sempre — no banco, nos backups e em qualquer agregador que não filtre. Para dado de
cliente real isso é uma pendência com peso jurídico, não estética.

Três decisões moram aqui, e todas são conservadoras de propósito:

- **Nasce inerte.** Retenção `0` significa *nunca expurgar*, e é o default de todas as famílias.
  Ninguém perde dado por ter atualizado o portal; o expurgo começa quando alguém decidir o prazo.
- **Só duas famílias**, e não os dezesseis modelos com `archived_at`. `Lead` e `Document` são as
  que guardam dado pessoal e são autocontidas. Apagar `Client` ou `Project` cascatearia sobre
  histórico comercial inteiro — é decisão de negócio maior, e fica registrada na ADR como não
  automatizada de propósito.
- **O arquivo vai junto com a linha.** Apagar o registro do documento e deixar o PDF no Drive ou no
  disco é meio expurgo, e o pior tipo: some o índice e fica o conteúdo.

A contagem é a partir de `archived_at`, não de `created_at`: o relógio começa quando alguém decidiu
que aquilo saiu de uso.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from . import drive

logger = logging.getLogger(__name__)

# Famílias expurgáveis. A chave é o nome usado na configuração e na saída do comando.
FAMILIAS = ("lead", "document")


@dataclass(frozen=True)
class Plano:
    """O que seria apagado numa família. `dias == 0` significa retenção desligada.

    `falhas` só existe para `document`: são as linhas cujo arquivo não saiu do provedor e que, por
    isso, ficaram para a próxima tentativa. Precisa ser contado e devolvido, e não apenas registrado
    no log — um expurgo que não expurgou e sai em silêncio é a mentira que fecha o ciclo.
    """

    familia: str
    dias: int
    quantidade: int
    falhas: int = 0

    @property
    def ativa(self) -> bool:
        return self.dias > 0


def dias_de(familia: str) -> int:
    """Prazo configurado, em dias. `0` (o default) = nunca expurgar."""
    return int(getattr(settings, "RETENTION_DAYS", {}).get(familia, 0))


def _queryset(familia: str, dias: int) -> QuerySet:
    from .models import Document, Lead

    limite = timezone.now() - timedelta(days=dias)
    # Anotado como `Any` porque as duas classes só compartilham o `TimestampedModel` abstrato, que
    # não tem `objects` — o mypy está certo, e a alternativa (um Protocol para "modelo com manager
    # e archived_at") seria abstração de mais para duas famílias.
    modelo: Any = {"lead": Lead, "document": Document}[familia]
    # `archived_at__lt`: só o que foi arquivado **e** já passou do prazo. Linha viva nunca entra —
    # este comando não decide o que sai de uso, ele só esquece o que já saiu.
    return modelo.objects.filter(archived_at__isnull=False, archived_at__lt=limite)


def planejar() -> list[Plano]:
    """O que o expurgo faria agora, sem tocar em nada."""
    planos = []
    for familia in FAMILIAS:
        dias = dias_de(familia)
        quantidade = _queryset(familia, dias).count() if dias > 0 else 0
        planos.append(Plano(familia=familia, dias=dias, quantidade=quantidade))
    return planos


def _apagar_arquivo(document) -> None:  # type: ignore[no-untyped-def]
    """Remove o conteúdo antes da linha. Falha aqui **não** apaga o registro.

    A ordem importa: se o arquivo não sai, a linha fica — assim o próximo expurgo tenta de novo.
    Ao contrário, some o índice e o conteúdo permanece sem ninguém sabendo que existe, que é
    exatamente o que a LGPD não quer.
    """
    if document.drive_file_id:
        drive.delete_document(document)
    elif document.file:
        document.file.delete(save=False)


def executar() -> list[Plano]:
    """Apaga de fato. Devolve o mesmo formato do `planejar`, com o que saiu."""
    from .models import Document

    resultados = []
    for familia in FAMILIAS:
        dias = dias_de(familia)
        if dias <= 0:
            resultados.append(Plano(familia=familia, dias=dias, quantidade=0))
            continue
        alvo = _queryset(familia, dias)
        if familia == "document":
            # Um a um, e não em massa: cada arquivo precisa sair antes da sua linha, e um erro num
            # documento não pode impedir o expurgo dos outros. O `try` é o que torna essa segunda
            # metade verdade — sem ele a primeira falha abortava o laço e levava junto todos os
            # documentos seguintes, que é o oposto exato do que esta linha promete.
            #
            # `except DriveProviderError` e não `except Exception`: erro de banco no `delete()`
            # logo abaixo continua sendo erro. Engoli-lo aqui viraria "o Google recusou" para uma
            # falha nossa — o tipo de mentira que o próprio `DriveProviderError` foi criado estreito
            # para evitar.
            saiu, falhas = 0, 0
            for documento in list(alvo):
                try:
                    _apagar_arquivo(documento)
                except drive.DriveProviderError:
                    # A linha **fica**, de propósito (ADR 0017): some o índice e fica o conteúdo é o
                    # pior resultado possível de um expurgo. Quem opera fica sabendo pelo comando.
                    logger.warning(
                        "expurgo: o arquivo de %s não saiu do provedor; a linha fica",
                        documento.original_name,
                        exc_info=True,
                    )
                    falhas += 1
                    continue
                Document.objects.filter(pk=documento.pk).delete()
                saiu += 1
            resultados.append(
                Plano(familia=familia, dias=dias, quantidade=saiu, falhas=falhas)
            )
        else:
            quantidade = alvo.count()
            alvo.delete()
            resultados.append(Plano(familia=familia, dias=dias, quantidade=quantidade))
    return resultados
