"""Regressão: o mandato de Design Partner não nasce da assinatura da **casa**.

`Document.is_signed` era um `.exists()` sobre as assinaturas concluídas. Com um signatário só —
o cliente — "alguém assinou" e "está assinado" eram a mesma frase, e a propriedade estava certa por
acidente. A issue #115 pôs três pessoas na mesma solicitação (a casa, a parte contratante e uma
testemunha) e desfez o acidente: a **primeira** assinatura a chegar costuma ser a da casa, porque é
ela quem envia.

O estrago não seria um erro na tela. Seria silencioso e em cadeia, tudo antes de o cliente abrir o
link: o artefato de contrato viraria `ACCEPTED`, o `Engagement` de Design Partner nasceria (ADR 0061),
o aviso interno diria que o acordo foi assinado e o convite para marcar o Discovery sairia para o
cliente — anunciando um acordo que ele ainda não assinou.

A guarda que impede isso é `Document.is_signed` perguntar **por rodada** (`document_ref`, o id que o
fornecedor devolve no `createDocument` e que todos os signatários de uma chamada compartilham).
`design_partner.abrir_engagement_do_acordo` já a consultava; este teste afirma que a resposta dela
continua sendo "não" enquanto faltar alguém, porque essa é a única coisa que separa o mandato da
sorte.
"""

import pytest
from django.core import mail
from django.test import override_settings

from apps.core import discovery_booking, esign
from apps.core.models import Artifact, Document, Engagement, SignatureRequest, User
from apps.core.tests.factories import AccountFactory, UserFactory

RODADA = "autentique-doc-1"


def _acordo(user: User) -> Document:
    return Document.objects.create(
        account=AccountFactory(owner=user, name="Rio Home Care"),
        original_name="acordo-design-partner.pdf",
        uploaded_by=user,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )


def _tres_signatarios(document: Document) -> dict[str, SignatureRequest]:
    """A casa, a parte contratante e a testemunha — todas na mesma rodada, todas pendentes."""
    return {
        papel: SignatureRequest.objects.create(
            document=document,
            signer_email=f"{papel}@x.test",
            signer_role=papel,
            document_ref=RODADA,
            provider_ref=f"sig-{papel}",
        )
        for papel in (
            SignatureRequest.SignerRole.HOUSE,
            SignatureRequest.SignerRole.COUNTERPARTY,
            SignatureRequest.SignerRole.WITNESS,
        )
    }


@pytest.mark.django_db
@override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)
def test_a_assinatura_da_casa_nao_abre_o_mandato_nem_avisa_o_cliente():
    user = UserFactory(role=User.Role.ADMIN)
    document = _acordo(user)
    solicitacoes = _tres_signatarios(document)

    esign.apply_decision(solicitacoes["house"].pk, SignatureRequest.Status.SIGNED)

    assert document.is_signed is False
    assert Engagement.objects.count() == 0
    assert Artifact.objects.filter(status=Artifact.Status.ACCEPTED).count() == 0
    assert _convites() == []

    esign.apply_decision(solicitacoes["counterparty"].pk, SignatureRequest.Status.SIGNED)
    assert Engagement.objects.count() == 0  # falta a testemunha

    esign.apply_decision(solicitacoes["witness"].pk, SignatureRequest.Status.SIGNED)

    assert document.is_signed is True
    assert Engagement.objects.filter(
        originating_design_partner_agreement=document,
        commercial_model=Engagement.CommercialModel.DESIGN_PARTNER,
    ).count() == 1
    # E o convite sai uma vez, para a **parte contratante** — nunca para quem fechou a rodada.
    assert [convite.to for convite in _convites()] == [["counterparty@x.test"]]


def _convites() -> list:
    return [m for m in mail.outbox if m.subject == discovery_booking.CONVITE_DO_DISCOVERY.assunto]
