"""Testes da Jornada de Transformação (FDD 011): materialização, avanço e permissões.

A partir da FDD 033, também os dois gates: o decision gate de quatro saídas e o quality gate
(checklist) que trava a conclusão de fase.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import (
    JourneyPhase,
    PhaseChecklistItem,
    Project,
    ProjectChecklistItem,
    ProjectDeliverable,
    ProjectPhase,
    User,
)

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _phase_at(project: Project, index: int) -> ProjectPhase:
    return project.phases.select_related("phase").order_by("phase__position", "id")[index]


def _requires_gate(project: Project, index: int) -> ProjectPhase:
    """Marca a fase de posição `index` como fase de decision gate (é config do template)."""
    project_phase = _phase_at(project, index)
    project_phase.phase.requires_gate = True
    project_phase.phase.save(update_fields=["requires_gate"])
    return project_phase


@pytest.mark.django_db
def test_project_creation_materializes_the_journey() -> None:
    """Ao nascer, um projeto ganha uma cópia do template: 1ª fase ativa, resto bloqueado."""
    project = ProjectFactory()

    phases = list(project.phases.order_by("phase__position"))
    assert len(phases) == JourneyPhase.objects.count() > 0
    assert phases[0].status == ProjectPhase.Status.ACTIVE
    assert phases[0].started_at is not None
    assert all(p.status == ProjectPhase.Status.LOCKED for p in phases[1:])
    # entregáveis do template foram copiados para a instância do projeto
    assert phases[0].deliverables.exists()
    assert project.current_phase == phases[0]


@pytest.mark.django_db
def test_advance_phase_completes_active_and_activates_next(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client.force_authenticate(delivery)

    response = client.post(reverse("project-advance-phase", args=[project.id]))

    assert response.status_code == 200
    ordered = list(project.phases.order_by("phase__position"))
    assert ordered[0].status == ProjectPhase.Status.DONE
    assert ordered[0].completed_at is not None
    assert ordered[1].status == ProjectPhase.Status.ACTIVE
    assert ordered[1].started_at is not None


@pytest.mark.django_db
def test_advance_phase_past_last_phase_is_graceful(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client.force_authenticate(admin)

    total = JourneyPhase.objects.count()
    for _ in range(total + 1):  # avança além da última fase
        response = client.post(reverse("project-advance-phase", args=[project.id]))
        assert response.status_code == 200

    assert project.current_phase is None
    assert project.phases.filter(status=ProjectPhase.Status.DONE).count() == total


@pytest.mark.django_db
def test_mark_deliverable_delivered_sets_timestamp(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    deliverable = ProjectDeliverable.objects.filter(project_phase__project=project).first()
    assert deliverable is not None
    client.force_authenticate(delivery)

    response = client.patch(
        reverse("projectdeliverable-detail", args=[deliverable.id]),
        {"status": ProjectDeliverable.Status.DELIVERED},
        format="json",
    )

    assert response.status_code == 200
    deliverable.refresh_from_db()
    assert deliverable.status == ProjectDeliverable.Status.DELIVERED
    assert deliverable.delivered_at is not None


@pytest.mark.django_db
def test_project_phases_are_lazily_materialized_when_missing(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    project.phases.all().delete()  # simula projeto antigo, anterior à jornada
    client.force_authenticate(admin)

    response = client.get(reverse("projectphase-list"), {"project": project.id})

    assert response.status_code == 200
    assert len(response.data) == JourneyPhase.objects.count()
    assert project.phases.filter(status=ProjectPhase.Status.ACTIVE).count() == 1


@pytest.mark.django_db
def test_delivery_reads_journey_but_sales_cannot_advance(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client.force_authenticate(sales)

    listed = client.get(reverse("projectphase-list"), {"project": project.id})
    advanced = client.post(reverse("project-advance-phase", args=[project.id]))
    deliverable = ProjectDeliverable.objects.filter(project_phase__project=project).first()
    marked = client.patch(
        reverse("projectdeliverable-detail", args=[deliverable.id]),
        {"status": ProjectDeliverable.Status.DELIVERED},
        format="json",
    )

    assert listed.status_code == 200  # vendas lê a jornada do projeto
    assert advanced.status_code == 403  # mas não avança fases
    assert marked.status_code == 403  # nem marca entregáveis


@pytest.mark.django_db
def test_journey_template_is_admin_only(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    admin = UserFactory(role=User.Role.ADMIN)

    client.force_authenticate(delivery)
    assert client.get(reverse("journeyphase-list")).status_code == 403

    client.force_authenticate(admin)
    admin_list = client.get(reverse("journeyphase-list"))
    assert admin_list.status_code == 200
    assert len(admin_list.data) == JourneyPhase.objects.count()


# ---------------------------------------------------------------------------
# Decision gate de quatro saídas (FDD 033)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fase_com_gate_nao_avanca_sem_decisao(client: APIClient) -> None:
    """O gate é obrigatório onde a metodologia diz que é: sem decisão, a fase não fecha."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    _requires_gate(project, 0)
    client.force_authenticate(admin)

    response = client.post(reverse("project-advance-phase", args=[project.id]))

    assert response.status_code == 409
    assert "decision gate" in response.data["detail"].lower()
    assert _phase_at(project, 0).status == ProjectPhase.Status.ACTIVE


@pytest.mark.django_db
@pytest.mark.parametrize("decision", ["go", "conditional_go"])
def test_gate_go_e_conditional_go_concluem_e_avancam(client: APIClient, decision: str) -> None:
    """As duas saídas de continuidade fazem a mesma coisa com a jornada — e guardam o que as separa."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    _requires_gate(project, 0)
    client.force_authenticate(delivery)

    response = client.post(
        reverse("project-apply-gate", args=[project.id]),
        {"decision": decision, "notes": "Latência acima do alvo — monitorar por 30 dias."},
        format="json",
    )

    assert response.status_code == 200
    first, second = _phase_at(project, 0), _phase_at(project, 1)
    assert first.status == ProjectPhase.Status.DONE
    assert first.completed_at is not None
    assert first.gate_decision == decision
    assert first.gate_notes.startswith("Latência")
    assert second.status == ProjectPhase.Status.ACTIVE
    # A lista devolvida é a mesma do `advance-phase`, com o gate visível na fase concluída.
    assert response.data[0]["gate_decision"] == decision
    assert response.data[0]["requires_gate"] is True


@pytest.mark.django_db
def test_gate_redesign_reabre_a_anterior_e_tranca_a_corrente(client: APIClient) -> None:
    """REDESIGN volta para testar de novo: a anterior reabre limpa e a corrente guarda o porquê."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client.force_authenticate(admin)
    assert client.post(reverse("project-advance-phase", args=[project.id])).status_code == 200
    _requires_gate(project, 1)

    response = client.post(
        reverse("project-apply-gate", args=[project.id]),
        {"decision": "redesign", "notes": "A abordagem de extração não sustenta o volume."},
        format="json",
    )

    assert response.status_code == 200
    first, second = _phase_at(project, 0), _phase_at(project, 1)
    assert first.status == ProjectPhase.Status.ACTIVE
    assert first.completed_at is None  # reabrir limpa o carimbo (precedente `Pendencia`)
    assert second.status == ProjectPhase.Status.LOCKED
    assert second.started_at is not None  # passou por aqui, e isso não se apaga
    assert second.gate_decision == ProjectPhase.GateDecision.REDESIGN
    assert "extração" in second.gate_notes


@pytest.mark.django_db
def test_gate_redesign_sem_fase_anterior_recusa(client: APIClient) -> None:
    """Na primeira fase não há para onde voltar — e recusar é melhor que fingir que voltou."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    _requires_gate(project, 0)
    client.force_authenticate(admin)

    response = client.post(
        reverse("project-apply-gate", args=[project.id]),
        {"decision": "redesign"},
        format="json",
    )

    assert response.status_code == 409
    assert "não há para onde voltar" in response.data["detail"]
    assert _phase_at(project, 0).gate_decision == ""  # nada gravado numa decisão que não aconteceu


@pytest.mark.django_db
def test_gate_no_go_registra_e_a_jornada_para_ali(client: APIClient) -> None:
    """NO-GO não muda a fase: registra por que a jornada parou, e o avanço passa a ser recusado."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    _requires_gate(project, 0)
    client.force_authenticate(admin)

    applied = client.post(
        reverse("project-apply-gate", args=[project.id]),
        {"decision": "no_go", "notes": "O modelo não alcança a precisão mínima do processo."},
        format="json",
    )
    advanced = client.post(reverse("project-advance-phase", args=[project.id]))

    assert applied.status_code == 200
    first = _phase_at(project, 0)
    assert first.status == ProjectPhase.Status.ACTIVE  # a fase não fecha
    assert first.gate_decision == ProjectPhase.GateDecision.NO_GO
    assert advanced.status_code == 409
    assert "NO-GO" in advanced.data["detail"]
    assert _phase_at(project, 1).status == ProjectPhase.Status.LOCKED


@pytest.mark.django_db
def test_apply_gate_recusa_fase_sem_gate_e_decisao_invalida(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client.force_authenticate(admin)

    sem_gate = client.post(
        reverse("project-apply-gate", args=[project.id]), {"decision": "go"}, format="json"
    )
    _requires_gate(project, 0)
    invalido = client.post(
        reverse("project-apply-gate", args=[project.id]), {"decision": "talvez"}, format="json"
    )

    assert sem_gate.status_code == 409  # o estado é que impede: a fase não é de gate
    assert invalido.status_code == 400  # o corpo é que está errado
    assert _phase_at(project, 0).gate_decision == ""


@pytest.mark.django_db
def test_gate_nao_entra_por_patch_direto(client: APIClient) -> None:
    """A decisão só entra pela action: um PATCH a gravaria sem nenhuma consequência."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    phase = _requires_gate(project, 0)
    client.force_authenticate(admin)

    response = client.patch(
        reverse("projectphase-detail", args=[phase.id]),
        {"gate_decision": "go", "gate_notes": "por fora"},
        format="json",
    )

    assert response.status_code == 200  # read-only no DRF é ignorado, não recusado
    phase.refresh_from_db()
    assert phase.gate_decision == ""
    assert phase.gate_notes == ""


@pytest.mark.django_db
def test_apply_gate_sem_fase_ativa_recusa(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    project.phases.all().update(status=ProjectPhase.Status.DONE)
    client.force_authenticate(admin)

    response = client.post(
        reverse("project-apply-gate", args=[project.id]), {"decision": "go"}, format="json"
    )

    assert response.status_code == 409
    assert "fase ativa" in response.data["detail"]


# ---------------------------------------------------------------------------
# Quality gate: o checklist que trava a conclusão (FDD 033)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_projeto_novo_herda_o_checklist_do_template() -> None:
    """O checklist é copiado na materialização, como o entregável — e projeto antigo não é reescrito."""
    template = JourneyPhase.objects.order_by("position").first()
    assert template is not None
    PhaseChecklistItem.objects.create(phase=template, text="Baseline definido?", position=0)
    antigo = ProjectFactory()
    antigo.phases.all().delete()

    novo = ProjectFactory()

    itens = ProjectChecklistItem.objects.filter(project_phase__project=novo)
    assert [item.text for item in itens] == ["Baseline definido?"]
    assert not ProjectChecklistItem.objects.filter(project_phase__project=antigo).exists()


@pytest.mark.django_db
def test_fase_com_checklist_pendente_nao_conclui(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    phase = _phase_at(project, 0)
    ProjectChecklistItem.objects.create(project_phase=phase, text="Amostra adequada?")
    ProjectChecklistItem.objects.create(project_phase=phase, text="Erros classificados?")
    client.force_authenticate(admin)

    response = client.post(reverse("project-advance-phase", args=[project.id]))

    assert response.status_code == 409
    assert "Faltam 2 item(ns)" in response.data["detail"]
    assert _phase_at(project, 0).status == ProjectPhase.Status.ACTIVE


@pytest.mark.django_db
def test_checklist_marcada_libera_a_conclusao(client: APIClient) -> None:
    """E marcar carimba a hora; desmarcar limpa, como o `delivered_at` do entregável."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    item = ProjectChecklistItem.objects.create(
        project_phase=_phase_at(project, 0), text="Economics calculado?"
    )
    client.force_authenticate(delivery)

    marked = client.patch(
        reverse("projectchecklistitem-detail", args=[item.id]), {"checked": True}, format="json"
    )
    item.refresh_from_db()
    carimbo = item.checked_at
    advanced = client.post(reverse("project-advance-phase", args=[project.id]))

    assert marked.status_code == 200
    assert item.checked is True
    assert carimbo is not None
    assert advanced.status_code == 200
    assert _phase_at(project, 0).status == ProjectPhase.Status.DONE

    client.patch(
        reverse("projectchecklistitem-detail", args=[item.id]), {"checked": False}, format="json"
    )
    item.refresh_from_db()
    assert item.checked_at is None


@pytest.mark.django_db
def test_justificativa_registrada_destrava_a_conclusao(client: APIClient) -> None:
    """Pular o quality gate é legítimo; fazê-lo em silêncio não é."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    phase = _phase_at(project, 0)
    ProjectChecklistItem.objects.create(project_phase=phase, text="T.O.E. avaliado?")
    client.force_authenticate(admin)

    waiver = client.patch(
        reverse("projectphase-detail", args=[phase.id]),
        {"checklist_waiver": "Cliente antecipou o go-live; T.O.E. fica para a revisão de 30 dias."},
        format="json",
    )
    advanced = client.post(reverse("project-advance-phase", args=[project.id]))

    assert waiver.status_code == 200
    assert advanced.status_code == 200
    assert _phase_at(project, 0).status == ProjectPhase.Status.DONE


@pytest.mark.django_db
def test_item_arquivado_nao_trava_a_fase(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    item = ProjectChecklistItem.objects.create(
        project_phase=_phase_at(project, 0), text="Pergunta que não se aplica"
    )
    client.force_authenticate(admin)

    archived = client.delete(reverse("projectchecklistitem-detail", args=[item.id]))
    advanced = client.post(reverse("project-advance-phase", args=[project.id]))

    assert archived.status_code == 204
    assert advanced.status_code == 200
    assert _phase_at(project, 0).status == ProjectPhase.Status.DONE


@pytest.mark.django_db
def test_gate_go_esbarra_no_checklist_sem_gravar_a_decisao(client: APIClient) -> None:
    """Os dois gates valem juntos, e o GO recusado não deixa decisão registrada pela metade."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    phase = _requires_gate(project, 0)
    ProjectChecklistItem.objects.create(project_phase=phase, text="Critérios de sucesso definidos?")
    client.force_authenticate(admin)

    response = client.post(
        reverse("project-apply-gate", args=[project.id]), {"decision": "go"}, format="json"
    )

    assert response.status_code == 409
    assert "checklist" in response.data["detail"].lower()
    phase.refresh_from_db()
    assert phase.gate_decision == ""
    assert phase.status == ProjectPhase.Status.ACTIVE


# ---------------------------------------------------------------------------
# Permissões dos dois gates
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vendas_le_o_checklist_mas_nao_marca_nem_aplica_gate(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    _requires_gate(project, 0)
    item = ProjectChecklistItem.objects.create(
        project_phase=_phase_at(project, 0), text="AS-IS validado?"
    )
    client.force_authenticate(sales)

    listed = client.get(reverse("projectchecklistitem-list"), {"project_phase": item.project_phase_id})
    marked = client.patch(
        reverse("projectchecklistitem-detail", args=[item.id]), {"checked": True}, format="json"
    )
    gated = client.post(
        reverse("project-apply-gate", args=[project.id]), {"decision": "go"}, format="json"
    )

    assert listed.status_code == 200
    assert marked.status_code == 403
    assert gated.status_code == 403


@pytest.mark.django_db
def test_entrega_so_alcanca_o_checklist_do_projeto_de_que_participa(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    alheio = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    _requires_gate(alheio, 0)
    meu_item = ProjectChecklistItem.objects.create(
        project_phase=_phase_at(meu, 0), text="Hipóteses rotuladas?"
    )
    alheio_item = ProjectChecklistItem.objects.create(
        project_phase=_phase_at(alheio, 0), text="Hipóteses rotuladas?"
    )
    client.force_authenticate(delivery)

    listed = client.get(reverse("projectchecklistitem-list"))
    meu_patch = client.patch(
        reverse("projectchecklistitem-detail", args=[meu_item.id]), {"checked": True}, format="json"
    )
    alheio_patch = client.patch(
        reverse("projectchecklistitem-detail", args=[alheio_item.id]),
        {"checked": True},
        format="json",
    )
    alheio_gate = client.post(
        reverse("project-apply-gate", args=[alheio.id]), {"decision": "go"}, format="json"
    )

    assert [row["id"] for row in listed.data] == [meu_item.id]
    assert meu_patch.status_code == 200
    assert alheio_patch.status_code == 404  # fora do queryset: nem existe, do ponto de vista dela
    assert alheio_gate.status_code == 404


@pytest.mark.django_db
def test_checklist_do_template_e_so_do_admin(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    admin = UserFactory(role=User.Role.ADMIN)
    phase = JourneyPhase.objects.order_by("position").first()
    assert phase is not None

    client.force_authenticate(delivery)
    assert client.get(reverse("phasechecklistitem-list")).status_code == 403

    client.force_authenticate(admin)
    created = client.post(
        reverse("phasechecklistitem-list"),
        {"phase": phase.id, "text": "Decision gate registrado?", "position": 0},
        format="json",
    )
    listed = client.get(reverse("phasechecklistitem-list"), {"phase": phase.id})
    toggled = client.patch(
        reverse("journeyphase-detail", args=[phase.id]), {"requires_gate": True}, format="json"
    )

    assert created.status_code == 201
    assert [row["text"] for row in listed.data] == ["Decision gate registrado?"]
    assert toggled.status_code == 200
    phase.refresh_from_db()
    assert phase.requires_gate is True
    assert toggled.data["checklist_items"][0]["text"] == "Decision gate registrado?"
