"""Regressão: case sem consentimento do cliente não publica — por nenhum caminho (FDD 027).

Publicar um case é a casa afirmar publicamente um número sobre um cliente. Sem autorização
registrada, isso não é prova social, é uso indevido do resultado de outra empresa — e o estrago
não tem desfazer, porque o número já saiu em proposta.

Anonimizar **não** abre exceção, e é o ponto mais fácil de errar: são duas permissões diferentes
(usar o resultado / usar a marca), e tratar `anonymized` como uma versão fraca do consentimento
publicaria sem autorização nenhuma alegando discrição.

As duas portas são testadas de propósito: o `clean()` cobre admin do Django, shell e job; o
serializer cobre a API. Fechar só uma deixaria a outra escancarada.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.core.models import Case, Project
from apps.core.tests.factories import ProjectFactory, UserFactory


def _case() -> Case:
    project = ProjectFactory(actual_value=Decimal("100.00"), cost=Decimal("50.00"))
    project.status = Project.Status.COMPLETED
    project.save()
    return Case.objects.get(project=project)


def _admin() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    return client


@pytest.mark.django_db
def test_a_api_recusa_publicar_sem_consentimento() -> None:
    case = _case()

    resposta = _admin().patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json")

    assert resposta.status_code == 400
    case.refresh_from_db()
    assert case.status == Case.Status.DRAFT
    assert case.published_at is None


@pytest.mark.django_db
def test_anonimizar_nao_dispensa_o_consentimento() -> None:
    case = _case()
    api = _admin()
    assert api.patch(f"/api/v1/cases/{case.pk}/", {"anonymized": True}, format="json").status_code == 200

    resposta = api.patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json")

    assert resposta.status_code == 400
    case.refresh_from_db()
    assert case.status == Case.Status.DRAFT


@pytest.mark.django_db
def test_publicar_e_anonimizar_no_mesmo_corpo_tambem_e_recusado() -> None:
    """O caminho que passaria se a guarda olhasse `anonymized` do payload em vez do consentimento."""
    case = _case()

    resposta = _admin().patch(
        f"/api/v1/cases/{case.pk}/", {"status": "published", "anonymized": True}, format="json"
    )

    assert resposta.status_code == 400
    case.refresh_from_db()
    assert case.status == Case.Status.DRAFT


@pytest.mark.django_db
def test_o_modelo_recusa_fora_da_api() -> None:
    case = _case()
    case.status = Case.Status.PUBLISHED

    with pytest.raises(ValidationError):
        case.full_clean()


@pytest.mark.django_db
def test_com_consentimento_registrado_publica() -> None:
    """A contraprova: a guarda recusa o que falta autorização, não tudo."""
    case = _case()
    api = _admin()
    api.post(f"/api/v1/cases/{case.pk}/record-consent/")

    assert api.patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json").status_code == 200
