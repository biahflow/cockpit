"""O mandato de Design Partner nasce sozinho do acordo assinado — nunca de outra coisa.

`design_partner.abrir_engagement_do_acordo` só cria o `Engagement` quando as quatro condições da
invariante 13 (`Engagement.clean()`) valem ao mesmo tempo: documento é um Design Partner
Agreement, tem conta vinculada, está assinado, e nenhum mandato já nasceu dele. Fora disso, o
silêncio (`None`, sem gravar nada) é o comportamento certo — este arquivo afirma isso tanto quanto
afirma a criação.
"""

import pytest
from django.utils import timezone

from apps.core import design_partner, esign
from apps.core.models import Document, Engagement, SignatureRequest, User

from .factories import AccountFactory, ProjectFactory, UserFactory


def _signed_agreement(account=None, uploaded_by=None) -> Document:
    uploader = uploaded_by or UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=account or AccountFactory(owner=uploader),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="patrocinador@x.test",
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )
    return document


@pytest.mark.django_db
def test_acordo_assinado_cria_o_mandato():
    document = _signed_agreement()

    engagement = design_partner.abrir_engagement_do_acordo(document)

    assert engagement is not None
    assert engagement.pk is not None
    assert engagement.account_id == document.account_id
    assert engagement.commercial_model == Engagement.CommercialModel.DESIGN_PARTNER
    assert engagement.owner_id == document.uploaded_by_id
    assert engagement.originating_design_partner_agreement_id == document.pk


@pytest.mark.django_db
@pytest.mark.parametrize("kind", [Document.Kind.NDA, Document.Kind.COMMERCIAL_CONTRACT])
def test_assinar_nda_ou_contrato_comercial_nao_abre_mandato(kind: str):
    """`kind` classifica o documento; abrir mandato é comportamento de um subconjunto só — hoje,
    exatamente o Design Partner Agreement (ADR 0061).
    """
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="documento.pdf",
        uploaded_by=uploader,
        kind=kind,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="patrocinador@x.test",
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )

    engagement = design_partner.abrir_engagement_do_acordo(document)

    assert engagement is None
    assert not Engagement.objects.filter(originating_design_partner_agreement=document).exists()


@pytest.mark.django_db
def test_a_decisao_de_abrir_mandato_mora_na_constante(monkeypatch: pytest.MonkeyPatch):
    """A decisão de quais `kind` abrem mandato mora em `models.DOCUMENT_KINDS_QUE_ABREM_ENGAGEMENT`
    — não numa comparação com o valor literal `DESIGN_PARTNER_AGREEMENT` espalhada por
    `abrir_engagement_do_acordo`. Este teste amplia só a constante, sem tocar a função, e espera
    que um NDA assinado passe a abrir mandato: se a função comparasse com o literal outra vez,
    ampliar a constante não teria efeito nenhum e o `assert engagement is not None` falharia.
    """
    from apps.core import models

    monkeypatch.setattr(
        models, "DOCUMENT_KINDS_QUE_ABREM_ENGAGEMENT", frozenset({Document.Kind.NDA})
    )
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="nda.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.NDA,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="patrocinador@x.test",
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )

    engagement = design_partner.abrir_engagement_do_acordo(document)

    assert engagement is not None
    assert engagement.originating_design_partner_agreement_id == document.pk


@pytest.mark.django_db
def test_documento_sem_kind_assinado_nao_cria_mandato():
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="contrato-comercial.pdf",
        uploaded_by=uploader,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="patrocinador@x.test",
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )

    engagement = design_partner.abrir_engagement_do_acordo(document)

    assert engagement is None
    assert not Engagement.objects.filter(originating_design_partner_agreement=document).exists()


@pytest.mark.django_db
def test_acordo_recusado_nao_cria_mandato():
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="patrocinador@x.test",
        status=SignatureRequest.Status.DECLINED,
    )

    engagement = design_partner.abrir_engagement_do_acordo(document)

    assert engagement is None
    assert not Engagement.objects.filter(originating_design_partner_agreement=document).exists()


@pytest.mark.django_db
def test_chamar_a_funcao_duas_vezes_nao_duplica_o_mandato():
    """A segunda chamada encontra a quarta condição já falsa e devolve `None` sem efeito."""
    document = _signed_agreement()

    first = design_partner.abrir_engagement_do_acordo(document)
    second = design_partner.abrir_engagement_do_acordo(document)

    assert first is not None
    assert second is None
    assert Engagement.objects.filter(originating_design_partner_agreement=document).count() == 1


@pytest.mark.django_db
def test_assinar_duas_vezes_via_apply_decision_nao_duplica_o_mandato():
    """A idempotência de `esign.apply_decision` cobre o mandato: reentrega não abre um segundo."""
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="patrocinador@x.test")

    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)
    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)

    assert Engagement.objects.filter(originating_design_partner_agreement=document).count() == 1


@pytest.mark.django_db
def test_mandato_nasce_com_julgamento_humano_vazio():
    document = _signed_agreement()

    engagement = design_partner.abrir_engagement_do_acordo(document)

    assert engagement is not None
    assert engagement.mandate == ""
    assert engagement.sponsor_id is None
    assert engagement.success_definition == ""


@pytest.mark.django_db
def test_a_recusa_da_ancora_nomeia_o_documento_que_a_pessoa_escolheu(
    monkeypatch: pytest.MonkeyPatch,
):
    """A mensagem sai do valor escolhido, e não cravada em "Design Partner Agreement".

    Hoje a constante tem um membro e a frase cravada bateria — é justamente por isso que ela
    passaria despercebida. Este teste amplia a constante e exige que a recusa nomeie o **NDA**:
    com a frase cravada, quem tentasse pendurar um NDA num projeto leria uma mensagem sobre um
    documento que não é o dele.
    """
    from django.core.exceptions import ValidationError

    from apps.core import models

    monkeypatch.setattr(
        models, "DOCUMENT_KINDS_QUE_ABREM_ENGAGEMENT", frozenset({Document.Kind.NDA})
    )
    uploader = UserFactory(role=User.Role.ADMIN)
    documento = Document(
        project=ProjectFactory(),
        original_name="nda.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.NDA,
    )

    with pytest.raises(ValidationError) as erro:
        documento.full_clean()

    assert "NDA" in str(erro.value)
    assert "Design Partner Agreement" not in str(erro.value)
