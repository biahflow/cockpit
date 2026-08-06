"""Regressão: notificação de projeto só chega a quem alcança o projeto (FDD 010, FDD 018, ADR 0010).

O último resíduo do `owner=` como critério. Nada reatribui item quando alguém sai de uma equipe —
o `ProjectMember` é arquivado e o `WorkItem.owner` fica —, então quem foi removido continuava
recebendo notificação de um projeto que já não abre.

O caminho realmente exposto é o `tasksync.apply_inbound`: ele dispara por **webhook do fornecedor**,
arbitrariamente depois da criação e sem `request.user` nenhum para consultar. Os signals de criação
eram seguros pela API (lá o dono é o autor, já validado), mas não quando `calendar_sync` cria tarefa
com `owner=project.owner` de dentro de um job agendado — que passou a rodar a cada 15 min na FDD 023.

O contraponto importa tanto quanto o caso: notificação escolhida por **papel** (lead novo) não pode
ser recortada por participação. Guardar demais aqui quebraria o comercial.
"""

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import notifications, tasksync
from apps.core.models import Lead, Notification, ProjectMember, Task, User
from apps.core.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory

pytestmark = pytest.mark.django_db


def _tarefa_sincronizada(project, owner, external_id="ENG-1") -> Task:
    return Task.objects.create(
        project=project, title="Homologar integração", owner=owner,
        due_date=timezone.localdate(), source="linear", external_id=external_id,
    )


def _atualizacoes(user) -> int:  # type: ignore[no-untyped-def]
    """Só as da sincronia — criar a tarefa dispara a sua própria notificação."""
    return Notification.objects.filter(user=user, message__startswith="Tarefa atualizada").count()


def test_membro_da_equipe_recebe_a_notificacao_da_sincronia() -> None:
    """O caminho feliz primeiro: sem ele, o teste seguinte passaria por não notificar ninguém."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=entrega)
    _tarefa_sincronizada(project, entrega, external_id="ENG-10")

    tasksync.apply_inbound("linear", "ENG-10", "completed")

    assert _atualizacoes(entrega) == 1


def test_removido_da_equipe_nao_recebe_mais_notificacao_do_projeto() -> None:
    """O defeito. A pessoa continua `owner` da tarefa; o acesso é que acabou."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=entrega)
    task = _tarefa_sincronizada(project, entrega, external_id="ENG-11")

    ProjectMember.objects.get(project=project, user=entrega).archive()

    tasksync.apply_inbound("linear", "ENG-11", "completed")

    assert _atualizacoes(entrega) == 0
    # A tarefa continua dela — o que mudou foi o alcance, não a titularidade.
    task.refresh_from_db()
    assert task.owner_id == entrega.id
    assert task.status == Task.Status.DONE


@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True)
def test_o_espelho_por_email_cai_junto(mailoutbox) -> None:  # type: ignore[no-untyped-def]
    """A guarda vale antes de gravar, então o e-mail sai do mesmo corte — não adianta esconder
    a linha do sino e mandar o título por e-mail assim mesmo."""
    entrega = UserFactory(role=User.Role.DELIVERY, email="fora@x.test")
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=entrega)
    _tarefa_sincronizada(project, entrega, external_id="ENG-12")
    ProjectMember.objects.get(project=project, user=entrega).archive()
    mailoutbox.clear()

    tasksync.apply_inbound("linear", "ENG-12", "completed")

    assert mailoutbox == []


def test_tarefa_criada_por_job_para_dono_sem_equipe_nao_notifica() -> None:
    """O caminho silencioso: `calendar_sync` e `kickoff` criam item com `owner=project.owner`,
    dono que não passou por `_assert_in_scope` e cuja participação pode ter sido arquivada."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=entrega)
    ProjectMember.objects.get(project=project, user=entrega).archive()

    Task.objects.create(
        project=project, title="Tarefa vinda do calendário", owner=entrega,
        due_date=timezone.localdate(),
    )

    assert not Notification.objects.filter(user=entrega, kind="task").exists()


def test_admin_nao_e_afetado_pela_guarda() -> None:
    """Para admin e vendas `visible_to` devolve tudo, então a guarda é no-op — e precisa ser,
    senão a correção viraria perda silenciosa de notificação para quem responde pela carteira."""
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()  # o admin não participa
    _tarefa_sincronizada(project, admin, external_id="ENG-13")

    tasksync.apply_inbound("linear", "ENG-13", "completed")

    assert _atualizacoes(admin) == 1


def test_notificacao_por_papel_nao_e_recortada_por_projeto() -> None:
    """O contraponto: lead novo escolhe destinatário por papel e não fala de projeto nenhum.

    Se a guarda tivesse sido aplicada em bloco, o comercial pararia de ser avisado.
    """
    vendas = UserFactory(role=User.Role.SALES)
    entrega = UserFactory(role=User.Role.DELIVERY)

    Lead.objects.create(name="Fulano", email="fulano@x.test")

    assert Notification.objects.filter(user=vendas, kind="lead").count() == 1
    assert not Notification.objects.filter(user=entrega, kind="lead").exists()


def test_notify_sem_projeto_mantem_o_comportamento_antigo() -> None:
    """`project=None` é o default e não filtra nada — é o que preserva os chamadores por papel."""
    entrega = UserFactory(role=User.Role.DELIVERY)

    notifications.notify([entrega], "avulsa", "Sem projeto envolvido")

    assert Notification.objects.filter(user=entrega, kind="avulsa").count() == 1
