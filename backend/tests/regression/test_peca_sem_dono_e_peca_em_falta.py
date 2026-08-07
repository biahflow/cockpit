"""Regressão: o inventário não regride para "todos são donos" (FDD 029), quarta cláusula.

"Dono por área" é a exigência que mais apodrece na prática, e ela apodrece de um jeito específico:
não por alguém decidir que ninguém é dono, mas por "sem dono" deixar de **aparecer**. Uma peça
fresquíssima cujo dono saiu da empresa não está em ordem — está órfã, e um inventário que a chama
de corrente é um inventário mentindo.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import knowledge
from apps.core.models import KnowledgeArea, KnowledgePiece, Notification
from apps.core.tests.factories import UserFactory


def _peca(area, **kwargs):
    kwargs.setdefault("title", "Runbook qualquer")
    kwargs.setdefault("source_path", f"docs/runbooks/{kwargs['title']}.md")
    return KnowledgePiece.objects.create(area=area, **kwargs)


@pytest.mark.django_db
def test_a_semente_nao_inventa_dono():
    """O estado inicial honesto é "em falta" — e é ele que torna a tela útil no primeiro dia."""
    assert KnowledgeArea.objects.count() == 5
    assert not KnowledgeArea.objects.exclude(owner=None).exists()


@pytest.mark.django_db
def test_sem_dono_ganha_de_corrente():
    """A ordem dos estados é a regra: órfã vence fresca."""
    area = KnowledgeArea.objects.get(slug="entrega")
    peca = _peca(area, last_verified_at=timezone.localdate(), review_interval_days=180)
    assert knowledge.freshness(peca) == knowledge.SEM_DONO

    area.owner = UserFactory(role="delivery")
    area.save(update_fields=["owner"])
    peca.refresh_from_db()
    assert knowledge.freshness(peca) == knowledge.CORRENTE


@pytest.mark.django_db
def test_dono_que_sai_devolve_a_peca_para_em_falta():
    """`SET_NULL` e não `PROTECT`: travar o arquivamento fingiria que o dono continua lá."""
    area = KnowledgeArea.objects.get(slug="entrega")
    dono = UserFactory(role="delivery")
    area.owner = dono
    area.save(update_fields=["owner"])
    peca = _peca(area, last_verified_at=timezone.localdate(), review_interval_days=180)

    dono.delete()
    area.refresh_from_db()
    peca.refresh_from_db()
    assert area.owner is None
    assert knowledge.freshness(peca) == knowledge.SEM_DONO


@pytest.mark.django_db
def test_peca_sem_area_tambem_e_em_falta():
    assert knowledge.freshness(_peca(None)) == knowledge.SEM_DONO


@pytest.mark.django_db
def test_em_falta_aparece_no_resumo_e_no_filtro():
    """Não basta o estado existir no código: ele tem de **aparecer** para quem decide."""
    _peca(KnowledgeArea.objects.get(slug="entrega"))
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))

    assert api.get("/api/v1/knowledge-pieces/summary/").data["sem_dono"] == 1
    assert len(api.get("/api/v1/knowledge-pieces/?status=sem_dono").data) == 1


@pytest.mark.django_db
def test_em_falta_avisa_o_admin_com_mensagem_propria():
    """Destinatário próprio e mensagem própria: sem dono é um defeito, não rodapé de outro aviso."""
    admin = UserFactory(role="admin")
    _peca(KnowledgeArea.objects.get(slug="entrega"))
    knowledge.check_freshness()
    aviso = Notification.objects.filter(user=admin, kind="knowledge_ownerless").first()
    assert aviso is not None
    assert "sem dono" in aviso.message


@pytest.mark.django_db
def test_a_ingestao_nao_apaga_a_curadoria():
    """A regra que carrega a disciplina inteira: reingerir não pode zerar o que um humano decidiu.

    Sem ela, cada deploy apagaria dono e carimbo em silêncio — e ninguém ligaria uma coisa à outra,
    porque o sintoma (tudo vermelho de novo) aparece dias depois da causa.
    """
    knowledge.ingest(embed=False)
    peca = KnowledgePiece.objects.filter(source_path="docs/adr/0013-backup-logico-em-container-proprio.md").first()
    assert peca is not None

    outra_area = KnowledgeArea.objects.get(slug="comercial")
    KnowledgePiece.objects.filter(pk=peca.pk).update(
        area=outra_area,
        last_verified_at=timezone.localdate() - timedelta(days=3),
        review_interval_days=45,
    )

    knowledge.ingest(embed=False)

    peca.refresh_from_db()
    assert peca.area_id == outra_area.pk, "a reingestão moveu a peça de área"
    assert peca.last_verified_at == timezone.localdate() - timedelta(days=3)
    assert peca.review_interval_days == 45


@pytest.mark.django_db
def test_peca_cujo_arquivo_sumiu_e_arquivada_e_nao_apagada():
    """O inventário não perde linha em silêncio, e a curadoria sobrevive se o arquivo voltar."""
    area = KnowledgeArea.objects.get(slug="entrega")
    orfa = _peca(area, title="Sumida", source_path="docs/runbooks/sumida.md")
    knowledge.ingest(embed=False)
    orfa.refresh_from_db()
    assert orfa.archived_at is not None
    assert KnowledgePiece.objects.filter(pk=orfa.pk).exists()
