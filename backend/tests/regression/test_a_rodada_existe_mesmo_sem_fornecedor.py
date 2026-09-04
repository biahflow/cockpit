"""Sem fornecedor homologado a rodada de assinatura continua existindo (issue #115, ADR 0065).

A rodada passou a ser o recorte de *"este documento está assinado?"*, e o recorte é o
`document_ref`. Com fornecedor ele vem do `createDocument`; **sem** fornecedor não vem ninguém, e
deixar o campo vazio jogaria todas as solicitações do documento na mesma rodada — um documento
recusado, reenviado e assinado à mão nunca mais contaria como assinado.

Isso não é caso de canto: o `NullProvider` é modo **previsto** (`CLAUDE.md`, docstring de
`esign.send_for_signature`), com o `mark-signed` manual como caminho legítimo. Era o comportamento
de antes desta entrega, quando a pergunta era um `.exists()`, e não pode regredir.

Por isso `send_for_signature` cunha uma referência `local:` quando o fornecedor não dá nenhuma. Um
teste é o que impede a próxima varredura de tirar o cunho achando que é enfeite.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import esign
from apps.core.models import Document, SignatureRequest
from apps.core.tests.factories import AccountFactory, UserFactory

pytestmark = pytest.mark.django_db

SEM_FORNECEDOR = override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="", ESIGN_API_TOKEN="")


def _document() -> Document:
    """Mesmo molde de `apps/core/tests/test_esign.py` — não há `DocumentFactory`."""
    user = UserFactory()
    account = AccountFactory(owner=user)
    return Document.objects.create(
        account=account, original_name="contrato.pdf", uploaded_by=user
    )


def _solicitar(document, email: str) -> SignatureRequest:
    """Uma rodada de um signatário, pelo mesmo caminho que a view usa."""
    signers = [esign.Signer(email=email, role=SignatureRequest.SignerRole.COUNTERPARTY)]
    (ref,) = esign.send_for_signature(document, signers)
    return SignatureRequest.objects.create(
        document=document,
        signer_email=email,
        signer_role=SignatureRequest.SignerRole.COUNTERPARTY,
        provider_ref=ref.provider_ref,
        document_ref=ref.document_ref,
        sign_url=ref.sign_url,
    )


@SEM_FORNECEDOR
def test_sem_fornecedor_cada_pedido_ganha_a_propria_rodada() -> None:
    document = _document()

    primeira = _solicitar(document, "a@cliente.test")
    segunda = _solicitar(document, "b@cliente.test")

    assert primeira.document_ref.startswith("local:")
    assert primeira.document_ref != segunda.document_ref, (
        "dois pedidos sem fornecedor caíram na mesma rodada; uma recusa antiga travaria o documento"
    )


@SEM_FORNECEDOR
def test_recusar_reenviar_e_assinar_a_mao_deixa_o_documento_assinado() -> None:
    """O caminho inteiro do registro local — e o que regrediria sem o cunho da rodada."""
    document = _document()

    recusada = _solicitar(document, "a@cliente.test")
    esign.apply_decision(recusada.pk, SignatureRequest.Status.DECLINED)
    assert document.is_signed is False

    reenviada = _solicitar(document, "a@cliente.test")
    esign.apply_decision(reenviada.pk, SignatureRequest.Status.SIGNED)

    assert document.is_signed is True, (
        "a rodada recusada e a assinada ficaram no mesmo grupo, e o documento nunca fecha"
    )
    assert document.rodada_assinada == reenviada.document_ref


@SEM_FORNECEDOR
def test_a_rodada_local_de_dois_so_fecha_com_os_dois() -> None:
    """O cunho separa rodadas; ele **não** afrouxa a regra dentro de uma."""
    document = _document()
    signers = [
        esign.Signer(email="cliente@x.test", role=SignatureRequest.SignerRole.COUNTERPARTY),
        esign.Signer(email="casa@x.test", role=SignatureRequest.SignerRole.HOUSE),
    ]
    refs = esign.send_for_signature(document, signers)
    assert len({ref.document_ref for ref in refs}) == 1, "uma chamada é uma rodada só"

    criadas = [
        SignatureRequest.objects.create(
            document=document, signer_email=signer.email, signer_role=signer.role,
            document_ref=ref.document_ref,
        )
        for signer, ref in zip(signers, refs, strict=True)
    ]

    criadas[0].status = SignatureRequest.Status.SIGNED
    criadas[0].signed_at = timezone.now()
    criadas[0].save(update_fields=["status", "signed_at"])
    assert document.is_signed is False

    criadas[1].status = SignatureRequest.Status.SIGNED
    criadas[1].signed_at = timezone.now()
    criadas[1].save(update_fields=["status", "signed_at"])
    assert document.is_signed is True
