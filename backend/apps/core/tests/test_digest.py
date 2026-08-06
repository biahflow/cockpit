from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core import digest, notifications
from apps.core.models import AiInteraction, Milestone, Notification, ProjectMember, Task, User

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


def _atrasada(project, owner, title, dias=2):
    return Task.objects.create(
        project=project, title=title, owner=owner,
        due_date=timezone.localdate() - timedelta(days=dias),
    )


@pytest.mark.django_db
def test_build_user_digest_context_lists_overdue_and_upcoming():
    owner = UserFactory()
    project = ProjectFactory(owner=owner)
    Milestone.objects.create(project=project, title="Marco atrasado", owner=owner,
                             due_date=timezone.localdate() - timedelta(days=2))
    Task.objects.create(project=project, title="Tarefa a vencer", owner=owner,
                        due_date=timezone.localdate() + timedelta(days=3))

    context = digest.build_user_digest_context(owner)

    assert "Marco atrasado" in context
    assert "Tarefa a vencer" in context


@pytest.mark.django_db
def test_build_user_digest_context_empty_without_items():
    assert digest.build_user_digest_context(UserFactory()) == ""


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_send_daily_digest_uses_ai_emails_and_audits(mailoutbox, monkeypatch):
    from apps.core import ai

    monkeypatch.setattr(ai, "complete", lambda system, user: ("Resumo do dia", {"prompt_tokens": 2, "completion_tokens": 1}))
    owner = UserFactory(email="dono@x.test")
    project = ProjectFactory(owner=owner)
    Milestone.objects.create(project=project, title="Atrasado", owner=owner,
                             due_date=timezone.localdate() - timedelta(days=1))

    sent = digest.send_daily_digest()

    assert sent == 1
    assert any("resumo diário" in mail.subject.lower() for mail in mailoutbox)
    assert AiInteraction.objects.filter(user=owner, feature="daily_digest").count() == 1


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
def test_send_daily_digest_noop_when_email_flag_off():
    owner = UserFactory(email="a@x.test")
    project = ProjectFactory(owner=owner)
    Task.objects.create(project=project, title="Pendente", owner=owner,
                        due_date=timezone.localdate() - timedelta(days=1))
    assert digest.send_daily_digest() == 0


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=False)
def test_send_daily_digest_command_runs_without_ai(mailoutbox):
    owner = UserFactory(email="dono@x.test")
    project = ProjectFactory(owner=owner)
    Task.objects.create(project=project, title="Pendente", owner=owner,
                        due_date=timezone.localdate() - timedelta(days=1))

    call_command("send_daily_digest")

    assert any("resumo diário" in mail.subject.lower() for mail in mailoutbox)


# --- digest por participação (FDD 010, FDD 018) ------------------------------------------------


@pytest.mark.django_db
def test_membro_que_nao_e_dono_de_nada_recebe_os_atrasados_do_projeto():
    """O furo que a FDD 018 registrou em aberto.

    Quem entra numa equipe não vira dono de nada — `owner` é sempre quem criou o item. Filtrando
    só por `owner=`, essa pessoa recebia contexto vazio e `send_daily_digest` a pulava: participava
    do projeto e nunca soube de um atraso.
    """
    dono = UserFactory()
    membro = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory(owner=dono)
    ProjectMemberFactory(project=project, user=membro)
    _atrasada(project, dono, "Homologar integração")

    context = digest.build_user_digest_context(membro)

    assert "Homologar integração" in context
    assert "Do seu projeto" in context


@pytest.mark.django_db
def test_quem_saiu_da_equipe_para_de_receber_os_proprios_itens_daquele_projeto():
    """Nada reatribui item quando alguém sai da equipe — então o `owner` sobrevive à remoção.

    Sem o recorte de acesso na seção própria, o digest seguia mandando título e vencimento de um
    projeto cujo detalhe já responde 404 para essa pessoa.
    """
    entrega = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory(owner=UserFactory())
    ProjectMemberFactory(project=project, user=entrega)
    _atrasada(project, entrega, "Tarefa de um projeto que eu deixei")

    assert "Tarefa de um projeto que eu deixei" in digest.build_user_digest_context(entrega)

    ProjectMember.objects.get(project=project, user=entrega).archive()

    assert digest.build_user_digest_context(entrega) == ""


@pytest.mark.django_db
def test_admin_dono_de_item_em_projeto_alheio_continua_recebendo():
    """Ninguém pode perder, em silêncio, e-mail que já recebia.

    Para admin e vendas o `project_scope_q` devolve `Q()` vazio — o recorte novo só morde a
    Entrega, que é de quem a fronteira de projeto fala.
    """
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory(owner=UserFactory())  # o admin não participa
    _atrasada(project, admin, "Item que eu criei em projeto alheio")

    context = digest.build_user_digest_context(admin)

    assert "Item que eu criei em projeto alheio" in context
    assert "Seus itens" in context


@pytest.mark.django_db
def test_admin_nao_recebe_o_portfolio_da_casa():
    """A prova de que a seção da equipe usa participação, e não `visible_to`.

    `visible_to` devolve *tudo* para admin e vendas; usá-la aqui mandaria o portfólio inteiro da
    casa para o admin, todo dia. Participação responde outra pergunta que não "posso ver?".
    """
    admin = UserFactory(role=User.Role.ADMIN)
    meu = ProjectFactory(owner=UserFactory())
    ProjectMemberFactory(project=meu, user=admin)
    _atrasada(meu, UserFactory(), "Atraso do meu projeto")

    alheio = ProjectFactory(owner=UserFactory())
    _atrasada(alheio, UserFactory(), "Atraso de projeto que não é meu")

    context = digest.build_user_digest_context(admin)

    assert "Atraso do meu projeto" in context
    assert "Atraso de projeto que não é meu" not in context


@pytest.mark.django_db
def test_item_proprio_nao_aparece_duas_vezes():
    """Dono e membro ao mesmo tempo é o caso comum — e as duas seções se sobreporiam."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory(owner=UserFactory())
    ProjectMemberFactory(project=project, user=entrega)
    _atrasada(project, entrega, "Item que é meu")

    context = digest.build_user_digest_context(entrega)

    assert context.count("Item que é meu") == 1


@pytest.mark.django_db
def test_secao_da_equipe_traz_so_atrasados():
    """"A vencer em 7 dias" do projeto inteiro seria volume sem sinal."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    outro = UserFactory()
    project = ProjectFactory(owner=outro)
    ProjectMemberFactory(project=project, user=entrega)
    _atrasada(project, outro, "Atrasado de outra pessoa")
    Task.objects.create(project=project, title="A vencer de outra pessoa", owner=outro,
                        due_date=timezone.localdate() + timedelta(days=3))

    context = digest.build_user_digest_context(entrega)

    assert "Atrasado de outra pessoa" in context
    assert "A vencer de outra pessoa" not in context


@pytest.mark.django_db
def test_teto_por_bloco_resume_o_excedente():
    """Um projeto com dezenas de atrasos não pode virar parede de texto diária."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    outro = UserFactory()
    project = ProjectFactory(owner=outro)
    ProjectMemberFactory(project=project, user=entrega)
    for n in range(digest._MAX_LINHAS + 3):
        _atrasada(project, outro, f"Atraso {n}")

    context = digest.build_user_digest_context(entrega)

    assert context.count("- Atraso") == digest._MAX_LINHAS
    assert "e mais 3" in context


@pytest.mark.django_db
def test_send_daily_digest_alcanca_o_membro_sem_itens_proprios(mailoutbox):
    """O efeito ponta a ponta: antes, `send_daily_digest` pulava essa pessoa."""
    dono = UserFactory(email="dono@x.test")
    membro = UserFactory(role=User.Role.DELIVERY, email="membro@x.test")
    project = ProjectFactory(owner=dono)
    ProjectMemberFactory(project=project, user=membro)
    _atrasada(project, dono, "Atraso que a equipe precisa ver")

    with override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=False):
        enviados = digest.send_daily_digest()

    destinatarios = {endereco for mail in mailoutbox for endereco in mail.to}
    assert "membro@x.test" in destinatarios
    assert enviados == 2  # o dono pelo item próprio, o membro pela seção da equipe


@pytest.mark.django_db
def test_quem_nao_tem_nada_a_reportar_nao_recebe_e_mail(mailoutbox):
    """Digest sem conteúdo não vira e-mail vazio — a pessoa é pulada."""
    UserFactory(email="ocioso@x.test")

    with override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=False):
        assert digest.send_daily_digest() == 0

    assert mailoutbox == []


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True)
def test_notify_mirrors_to_email_when_flag_on(mailoutbox):
    user = UserFactory(email="u@x.test")
    notifications.notify([user], "test", "Olá")
    assert Notification.objects.filter(user=user, kind="test").count() == 1
    assert any(mail.to == ["u@x.test"] for mail in mailoutbox)


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
def test_notify_skips_email_when_flag_off(mailoutbox):
    notifications.notify([UserFactory(email="u@x.test")], "test", "Olá")
    assert mailoutbox == []
