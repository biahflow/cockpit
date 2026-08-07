"""Inventário e disciplina de frescor (FDD 029) — a metade que roda sem IA nenhuma."""

from datetime import timedelta
from itertools import count

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import knowledge
from apps.core.models import KnowledgeArea, KnowledgePiece, Notification, User

from .factories import UserFactory


@pytest.fixture
def area():
    return KnowledgeArea.objects.get(slug="entrega")


@pytest.fixture
def dono(area):
    pessoa = UserFactory(role="delivery", first_name="Dona", last_name="Área")
    area.owner = pessoa
    area.save(update_fields=["owner"])
    return pessoa


_contador = count(1)


def _peca(area=None, **kwargs):
    """Peça com `source_path` único — a constraint parcial é real e reprova duplicata."""
    kwargs.setdefault("title", "Runbook de restauração")
    kwargs.setdefault("kind", KnowledgePiece.Kind.PROCEDURE)
    kwargs.setdefault("source_path", f"docs/runbooks/{next(_contador)}.md")
    return KnowledgePiece.objects.create(area=area, **kwargs)


# --- O estado derivado --------------------------------------------------------


@pytest.mark.django_db
def test_as_cinco_areas_vem_semeadas_e_sem_dono():
    """A semente não inventa responsável — 'sem dono' é o estado inicial honesto."""
    assert KnowledgeArea.objects.count() == 5
    assert not KnowledgeArea.objects.exclude(owner=None).exists()


@pytest.mark.django_db
def test_peca_sem_area_ou_sem_dono_e_sem_dono(area):
    assert knowledge.freshness(_peca(None)) == knowledge.SEM_DONO
    assert knowledge.freshness(_peca(area)) == knowledge.SEM_DONO  # área existe, dono não


@pytest.mark.django_db
def test_sem_dono_vence_ate_a_peca_recem_verificada(area, dono):
    """"Peça sem dono é peça em falta" — e isso ganha de estar fresca."""
    peca = _peca(area, last_verified_at=timezone.localdate())
    assert knowledge.freshness(peca) == knowledge.CORRENTE

    area.owner = None
    area.save(update_fields=["owner"])
    peca.refresh_from_db()
    assert knowledge.freshness(peca) == knowledge.SEM_DONO


@pytest.mark.django_db
def test_peca_nunca_verificada_nao_e_corrente(area, dono):
    """Nunca conferida não é fresca: tratá-la assim é como um inventário vira decoração."""
    peca = _peca(area)
    KnowledgePiece.objects.filter(pk=peca.pk).update(
        created_at=timezone.now() - timedelta(days=200)
    )
    peca.refresh_from_db()
    assert knowledge.freshness(peca) == knowledge.VENCIDO


@pytest.mark.django_db
def test_prazo_zero_significa_nao_vence(area, dono):
    """ADR é quase imutável: substitui-se, não se atualiza. Cobrá-la seria ruído."""
    peca = _peca(area, kind=KnowledgePiece.Kind.DECISION, review_interval_days=0,
                 last_verified_at=timezone.localdate() - timedelta(days=3650))
    assert knowledge.due_date(peca) is None
    assert knowledge.freshness(peca) == knowledge.CORRENTE


@pytest.mark.django_db
def test_prazo_nulo_herda_o_da_area(area, dono):
    peca = _peca(area, review_interval_days=None,
                 last_verified_at=timezone.localdate() - timedelta(days=181))
    assert knowledge.review_interval(peca) == area.review_interval_days == 180
    assert knowledge.freshness(peca) == knowledge.VENCIDO


@pytest.mark.django_db
def test_a_vencer_avisa_antes_de_virar_divida(area, dono):
    peca = _peca(area, review_interval_days=180,
                 last_verified_at=timezone.localdate() - timedelta(days=160))
    assert knowledge.freshness(peca) == knowledge.A_VENCER


@pytest.mark.django_db
def test_varias_lacunas_tacitas_coexistem(area, dono):
    """`source_path` vazio é lacuna; um `unique=True` simples deixaria existir **uma** no sistema."""
    _peca(area, title="Como precificar fora de tabela", source_path="")
    _peca(area, title="Como conduzir a virada de chave", source_path="")
    assert KnowledgePiece.objects.filter(source_path="").count() == 2


# --- O job --------------------------------------------------------------------


@pytest.mark.django_db
def test_o_job_avisa_o_dono_do_que_venceu(area, dono):
    _peca(area, review_interval_days=90,
          last_verified_at=timezone.localdate() - timedelta(days=120))
    resumo = knowledge.check_freshness()
    assert resumo["vencidas"] == 1
    assert Notification.objects.filter(user=dono, kind="knowledge_stale").count() == 1


@pytest.mark.django_db
def test_o_job_nao_avisa_o_mesmo_todo_dia(area, dono):
    """Sem teto de frequência o aviso vira ruído diário, e o laço inteiro é ignorado."""
    _peca(area, review_interval_days=90,
          last_verified_at=timezone.localdate() - timedelta(days=120))
    knowledge.check_freshness()
    knowledge.check_freshness()
    assert Notification.objects.filter(kind="knowledge_stale").count() == 1

    depois = timezone.localdate() + timedelta(days=8)
    knowledge.check_freshness(depois)
    assert Notification.objects.filter(kind="knowledge_stale").count() == 2


@pytest.mark.django_db
def test_peca_sem_dono_avisa_o_admin_com_outra_mensagem(area):
    """Sem dono é um defeito próprio, com destinatário próprio — não rodapé de outro aviso."""
    admin = UserFactory(role="admin")
    _peca(area)
    knowledge.check_freshness()
    aviso = Notification.objects.filter(user=admin, kind="knowledge_ownerless").first()
    assert aviso is not None
    assert "sem dono" in aviso.message


@pytest.mark.django_db
def test_o_comando_nao_falha_com_divida_editorial(area):
    """Runbook vencido não é incidente. Sair com erro ensinaria a silenciar o alerta."""
    from django.core.management import call_command

    _peca(area)
    call_command("check_knowledge_freshness")  # não levanta


@pytest.mark.django_db
def test_o_job_esta_na_tabela_do_agendador():
    from apps.core import scheduler

    tabela = {job.name: job for job in scheduler.jobs()}
    assert tabela["knowledge_freshness"].command == "check_knowledge_freshness"


# --- A API --------------------------------------------------------------------


@pytest.fixture
def api_admin():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    return client


@pytest.mark.django_db
def test_summary_conta_por_estado(area, dono, api_admin):
    _peca(area, title="Vencido", review_interval_days=30,
          last_verified_at=timezone.localdate() - timedelta(days=60))
    _peca(area, title="Corrente", review_interval_days=180,
          last_verified_at=timezone.localdate())
    _peca(None, title="Órfã")

    dados = api_admin.get("/api/v1/knowledge-pieces/summary/").data
    assert dados["vencido"] == 1
    assert dados["corrente"] == 1
    assert dados["sem_dono"] == 1


@pytest.mark.django_db
def test_filtro_por_estado(area, dono, api_admin):
    _peca(area, title="Vencido", review_interval_days=30,
          last_verified_at=timezone.localdate() - timedelta(days=60))
    _peca(area, title="Corrente", review_interval_days=180,
          last_verified_at=timezone.localdate())

    resposta = api_admin.get("/api/v1/knowledge-pieces/?status=vencido")
    assert [p["title"] for p in resposta.data] == ["Vencido"]


@pytest.mark.django_db
def test_verificar_grava_autor_e_carimbo(area, dono, api_admin):
    peca = _peca(area)
    resposta = api_admin.post(f"/api/v1/knowledge-pieces/{peca.id}/verify/")
    assert resposta.status_code == 200
    peca.refresh_from_db()
    assert peca.last_verified_at == timezone.localdate()
    assert peca.verified_by is not None


@pytest.mark.django_db
def test_verificar_nao_e_campo_que_um_patch_liga(area, dono, api_admin):
    peca = _peca(area)
    api_admin.patch(f"/api/v1/knowledge-pieces/{peca.id}/",
                    {"last_verified_at": "2020-01-01"}, format="json")
    peca.refresh_from_db()
    assert peca.last_verified_at is None


@pytest.mark.django_db
def test_o_dono_verifica_mesmo_sendo_da_entrega(area, dono):
    """O aviso chega a quem pode agir — travar o ato atrás de admin quebraria o laço."""
    peca = _peca(area)
    client = APIClient()
    client.force_authenticate(dono)
    assert client.post(f"/api/v1/knowledge-pieces/{peca.id}/verify/").status_code == 200


@pytest.mark.django_db
def test_quem_nao_e_dono_nem_admin_nao_verifica(area, dono):
    peca = _peca(area)
    client = APIClient()
    client.force_authenticate(UserFactory(role="delivery"))
    resposta = client.post(f"/api/v1/knowledge-pieces/{peca.id}/verify/")
    assert resposta.status_code == 403
    assert "Dona" in resposta.data["detail"]


@pytest.mark.django_db
def test_todo_autenticado_le_o_inventario(area, dono):
    _peca(area)
    for papel in (User.Role.SALES, User.Role.DELIVERY):
        client = APIClient()
        client.force_authenticate(UserFactory(role=papel))
        assert client.get("/api/v1/knowledge-pieces/").status_code == 200
        assert client.post("/api/v1/knowledge-pieces/",
                           {"title": "x", "area": area.id}, format="json").status_code == 403
