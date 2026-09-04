"""A régua de cobrança (FDD 036, camadas 3 e 4 da RFC 0004).

A escada é função pura sobre o estado da fatura, e é por isso que este arquivo começa por ela: o
oráculo do resto é "que degrau cabe hoje?" respondido sem banco, sem e-mail e sem relógio.

Nada aqui fala com provedor externo — a régua lê fatura, escreve registro e manda e-mail pelo SMTP
que a casa já usa —, então nada aqui está atrás de `# pragma: no cover`.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, cobranca, health
from apps.core.models import (
    Account,
    Activity,
    CobrancaContato,
    CobrancaSuspensao,
    Contact,
    Invoice,
    Meeting,
    Milestone,
    Notification,
    Pendencia,
    Project,
    SatisfactionRecord,
    User,
    WorkItem,
)

from .factories import (
    AccountFactory,
    ActivityFactory,
    InvoiceFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

HOJE = date(2026, 9, 2)  # uma quarta-feira: dia útil, para o fim de semana não mascarar nada


def _fatura(**kwargs) -> Invoice:  # type: ignore[no-untyped-def]
    """Uma fatura **emitida**, que é o estado em que a régua tem o que fazer.

    O número sai de um sequencial porque a `UniqueConstraint` parcial de `Invoice.number` é real:
    duas faturas com o mesmo número reprovam no insert, e é fácil escrever um cenário de dois
    recebíveis do mesmo cliente sem perceber.
    """
    kwargs.setdefault("status", Invoice.Status.ISSUED)
    kwargs.setdefault("number", f"2026-{Invoice.objects.count() + 1:04d}")
    return InvoiceFactory(**kwargs)


def _vencendo_em(dias: int, **kwargs) -> Invoice:  # type: ignore[no-untyped-def]
    """Fatura cujo vencimento cai `dias` **antes** de HOJE (negativo = ainda vai vencer)."""
    return _fatura(due_date=HOJE - timedelta(days=dias), **kwargs)


def _com_contato_de_cobranca(account: Account, email: str = "financeiro@cliente.test") -> Contact:
    return Contact.objects.create(
        account=account, first_name="Financeiro", email=email, receives_billing=True
    )


# --- A escada -----------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dias", "esperado"),
    [
        (-5, None),          # cedo demais: o pré-aviso ainda não abriu
        (-3, "pre_aviso"),
        (-1, "pre_aviso"),
        (0, None),           # vence hoje: a janela do pré-aviso fechou e a carência começou
        (1, None),           # carência
        (2, None),           # carência
        (3, "lembrete"),
        (9, "lembrete"),
        (10, "firme"),
        (19, "firme"),
        (20, "escalada"),
        (29, "escalada"),
        (30, "renegociacao"),
        (400, "renegociacao"),
    ],
)
def test_a_escada_padrao_responde_por_dia(dias: int, esperado: str | None) -> None:
    invoice = _vencendo_em(dias)
    degrau = cobranca.degrau_devido(invoice, HOJE)
    assert (degrau.key if degrau else None) == esperado


@pytest.mark.django_db
def test_a_carencia_nao_existe_como_degrau() -> None:
    """O silêncio entre D+0 e D+3 é o degrau. Representá-lo como uma entrada que não faz nada
    convidaria alguém a preenchê-la."""
    chaves = {d.key for d in cobranca.PADRAO}
    assert "carencia" not in chaves
    assert all(cobranca.degrau_devido(_vencendo_em(d), HOJE) is None for d in (0, 1, 2))


@pytest.mark.django_db
def test_o_pre_aviso_atrasado_nao_vira_mentira() -> None:
    """A régua não rodou em D−3 (fim de semana, flag desligada, emissão em cima da hora).

    Sem a janela fechada em D+0, o "sua fatura vence em 3 dias" sairia com a fatura já vencida —
    uma mentira escrita pela casa, e a única do repertório que o cliente consegue conferir sozinho.
    """
    invoice = _vencendo_em(1)
    assert CobrancaContato.objects.filter(invoice=invoice).count() == 0
    assert cobranca.degrau_devido(invoice, HOJE) is None


def _cliente_de_casa() -> Account:
    """Cliente com mais de um ano de casa. `created_at` é `auto_now_add`, então só o `update` o
    move."""
    account = AccountFactory()
    Account.objects.filter(pk=account.pk).update(created_at=timezone.now() - timedelta(days=800))
    account.refresh_from_db()
    return account


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dias", "esperado"),
    [(3, None), (5, "lembrete"), (12, "lembrete"), (20, "escalada"), (30, "renegociacao")],
)
def test_relacao_longa_atrasa_o_lembrete_e_nao_tem_degrau_firme(
    dias: int, esperado: str | None
) -> None:
    """Requisito da seção Segurança da RFC: cinco dias de atraso de um cliente antigo não é o
    mesmo evento que reincidência.

    Uma fatura por cenário, e de propósito: duas faturas vencidas do mesmo cliente já **são**
    reincidência, e o teste passaria a medir outra coisa.
    """
    antigo = _cliente_de_casa()
    assert cobranca.regua_para(antigo, HOJE) is cobranca.RELACAO_LONGA
    assert "firme" not in {d.key for d in cobranca.RELACAO_LONGA}

    degrau = cobranca.degrau_devido(_vencendo_em(dias, account=antigo), HOJE)
    assert (degrau.key if degrau else None) == esperado


@pytest.mark.django_db
def test_relacao_longa_exige_ausencia_de_reincidencia() -> None:
    antigo = _cliente_de_casa()
    InvoiceFactory(
        account=antigo, status=Invoice.Status.PAID, number="2025-0009",
        due_date=HOJE - timedelta(days=200),
        paid_at=timezone.make_aware(
            timezone.datetime(2026, 3, 1, 12, 0)
        ),
    )
    assert cobranca.reincidente(antigo, HOJE) is True
    assert cobranca.regua_para(antigo, HOJE) is cobranca.PADRAO


@pytest.mark.django_db
def test_a_reincidencia_ignora_a_propria_fatura() -> None:
    """Sem esta exclusão, toda fatura vencida tornaria o próprio cliente reincidente — e a
    `RELACAO_LONGA` seria inalcançável exatamente quando ela serve para alguma coisa."""
    antigo = _cliente_de_casa()
    atrasada = _vencendo_em(12, account=antigo, status=Invoice.Status.OVERDUE)

    assert cobranca.reincidente(antigo, HOJE) is True
    assert cobranca.reincidente(antigo, HOJE, ignorando=atrasada) is False
    assert cobranca.regua_para(antigo, HOJE, ignorando=atrasada) is cobranca.RELACAO_LONGA


def _insatisfacao(account: Account, quando: date | None = None) -> SatisfactionRecord:
    """Insatisfação **declarada** e vigente — a que troca a escada (FDD 037, ADR 0032)."""
    return SatisfactionRecord.objects.create(
        account=account,
        nivel=SatisfactionRecord.Nivel.DISSATISFIED,
        fonte=SatisfactionRecord.Fonte.DECLARED,
        happened_on=quando or HOJE,
        note="Disse na call que a entrega do marco 2 atrasou duas vezes.",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dias", "esperado"),
    [(-2, "pre_aviso"), (1, None), (5, "lembrete"), (10, "escalada"), (30, "renegociacao")],
)
def test_a_relacao_tensa_troca_o_degrau_firme_pela_escalada(dias: int, esperado: str | None) -> None:
    """A régua **não cala**: ela para de endurecer e passa a acordar gente (ADR 0032).

    O `firme` não existe e a escalada interna ocupa a janela que era dele (D+10) — quem então
    recua é uma pessoa, declarando a suspensão com dono, prazo e motivo.
    """
    account = AccountFactory()
    _insatisfacao(account)
    assert cobranca.regua_para(account, HOJE) is cobranca.RELACAO_TENSA
    assert "firme" not in {d.key for d in cobranca.RELACAO_TENSA}

    degrau = cobranca.degrau_devido(_vencendo_em(dias, account=account), HOJE)
    assert (degrau.key if degrau else None) == esperado


@pytest.mark.django_db
def test_a_escada_tensa_reusa_as_chaves_existentes() -> None:
    """Chave nova faria o mesmo lembrete sair duas vezes para quem trocasse de escada entre duas
    execuções — e trocar de escada aqui é fácil: basta alguém registrar a insatisfação de ontem."""
    tensa = {d.key for d in cobranca.RELACAO_TENSA}

    assert tensa <= {d.key for d in cobranca.PADRAO}


@pytest.mark.django_db
def test_a_tensao_vence_a_relacao_longa() -> None:
    """Um cliente de anos e insatisfeito é o caso mais perigoso da carteira, e a escada desenhada
    para proteger o cliente antigo não pode absorvê-lo."""
    antigo = _cliente_de_casa()
    assert cobranca.regua_para(antigo, HOJE) is cobranca.RELACAO_LONGA

    _insatisfacao(antigo)

    assert cobranca.regua_para(antigo, HOJE) is cobranca.RELACAO_TENSA


@pytest.mark.django_db
@pytest.mark.parametrize("dias", [89, 91])
def test_a_insatisfacao_envelhece_e_a_escada_volta(dias: int) -> None:
    account = AccountFactory()
    _insatisfacao(account, HOJE - timedelta(days=dias))

    esperada = cobranca.RELACAO_TENSA if dias == 89 else cobranca.PADRAO
    assert cobranca.regua_para(account, HOJE) is esperada


@pytest.mark.django_db
def test_a_satisfacao_nao_produz_avaliacao_muda() -> None:
    """Critério de aceite 3: nenhum caminho novo faz `avaliar` devolver uma avaliação sem degrau,
    e nenhuma constante de motivo nova existe. Quem recua é gente (RFC 0004, "Segurança")."""
    account = AccountFactory()
    _insatisfacao(account)

    avaliacao = cobranca.avaliar(_vencendo_em(10, account=account), HOJE)

    assert avaliacao.degrau is not None
    assert avaliacao.motivo == ""


def _entrega_em_frangalhos(account: Account, **kwargs) -> Project:
    """Um projeto cuja saúde é **crítica** pelos sinais que o `health.py` já mede.

    Nada aqui escreve o nível à mão: o limiar é o de `health._level` e é ele que este cenário
    exercita. Se os pesos dos sinais mudarem, a asserção do fim aponta o cenário — que é o que se
    quer — em vez de deixar a trava sendo testada contra um projeto saudável.
    """
    ontem = timezone.localdate() - timedelta(days=1)
    project = ProjectFactory(engagement__account=account, due_date=ontem, **kwargs)
    for indice in range(4):
        Milestone.objects.create(
            project=project, title=f"Marco {indice}", due_date=ontem, owner=project.owner
        )
    for indice in range(2):
        Meeting.objects.create(
            project=project, title=f"Reunião {indice}", date=ontem,
            status=Meeting.Status.SCHEDULED,
        )
    Pendencia.objects.create(
        project=project, title="Decisão travada", status=Pendencia.Status.OPEN,
        party=WorkItem.Party.CLIENT,
    )
    assert health.assess_project_health(project)["level"] == health.CRITICAL
    return project


@pytest.mark.django_db
def test_a_entrega_critica_troca_a_escada() -> None:
    """A outra metade da camada 5 (FDD 038): a régua reage ao **nosso** trabalho, não só ao que o
    cliente disse. Mesma escada da insatisfação declarada — para de endurecer e acorda gente."""
    account = AccountFactory()
    assert cobranca.regua_para(account, HOJE) is cobranca.PADRAO

    _entrega_em_frangalhos(account)

    assert cobranca.entrega_critica(account, HOJE) is True
    assert cobranca.regua_para(account, HOJE) is cobranca.RELACAO_TENSA
    # E não cala: em D+12 sai a escalada interna, no lugar do degrau firme.
    degrau = cobranca.degrau_devido(_vencendo_em(12, account=account), HOJE)
    assert degrau is not None and degrau.key == "escalada"


@pytest.mark.django_db
def test_a_escada_da_entrega_reusa_as_chaves_existentes() -> None:
    """Uma escada própria para a entrega faria o mesmo lembrete sair duas vezes para quem trocasse
    de escada entre duas execuções — e aqui basta um marco vencer para a troca acontecer."""
    account = AccountFactory()
    _entrega_em_frangalhos(account)

    regua = cobranca.regua_para(account, HOJE)

    assert regua is cobranca.RELACAO_TENSA
    assert {d.key for d in regua} <= {d.key for d in cobranca.PADRAO}


@pytest.mark.django_db
def test_a_tensao_por_entrega_vence_a_relacao_longa() -> None:
    """Um cliente de anos com a entrega em frangalhos é o mesmo caso perigoso do cliente de anos
    insatisfeito: a escada que existe para protegê-lo não pode absorvê-lo."""
    antigo = _cliente_de_casa()
    assert cobranca.regua_para(antigo, HOJE) is cobranca.RELACAO_LONGA

    _entrega_em_frangalhos(antigo)

    assert cobranca.regua_para(antigo, HOJE) is cobranca.RELACAO_TENSA


@pytest.mark.django_db
def test_projeto_concluido_em_frangalhos_nao_troca_a_escada() -> None:
    """É o caso que faz uma trava apodrecer: um crítico congelado no passado a deixaria ligada para
    sempre, e uma trava que nunca desliga é uma trava que ninguém respeita."""
    account = AccountFactory()
    projeto = _entrega_em_frangalhos(account)
    assert cobranca.regua_para(account, HOJE) is cobranca.RELACAO_TENSA

    projeto.status = Project.Status.COMPLETED
    projeto.save(update_fields=["status"])

    assert cobranca.entrega_critica(account, HOJE) is False
    assert cobranca.regua_para(account, HOJE) is cobranca.PADRAO


@pytest.mark.django_db
def test_cliente_sem_projeto_continua_na_padrao() -> None:
    """A régua pergunta por cliente, e fatura sem projeto existe — a guarda não pode estourar nem
    inventar tensão onde não há entrega nenhuma."""
    account = AccountFactory()

    assert cobranca.entrega_critica(account, HOJE) is False
    assert cobranca.causa_da_tensao(account, HOJE) is None
    assert cobranca.regua_para(account, HOJE) is cobranca.PADRAO


@pytest.mark.django_db
def test_projeto_saudavel_nao_troca_a_escada() -> None:
    """O complemento: cercar tudo não é cercar. Se qualquer projeto trocasse a escada, o teste de
    cima passaria por ausência de projeto e não por ausência de crítico."""
    account = AccountFactory()
    ProjectFactory(engagement__account=account)

    assert cobranca.entrega_critica(account, HOJE) is False
    assert cobranca.regua_para(account, HOJE) is cobranca.PADRAO


@pytest.mark.django_db
def test_a_causa_da_tensao_nomeia_as_duas_origens() -> None:
    """A escada é a mesma nas três causas; o que muda é o que a tela diz. Sem o nome, o painel diz
    "régua tensa" e não diz por quê — e as duas condutas que ele deveria sugerir são diferentes."""
    so_satisfacao = AccountFactory()
    _insatisfacao(so_satisfacao)
    so_entrega = AccountFactory()
    _entrega_em_frangalhos(so_entrega)
    ambas = AccountFactory()
    _insatisfacao(ambas)
    _entrega_em_frangalhos(ambas)

    assert cobranca.causa_da_tensao(so_satisfacao, HOJE) == cobranca.TENSAO_SATISFACAO
    assert cobranca.causa_da_tensao(so_entrega, HOJE) == cobranca.TENSAO_ENTREGA
    assert cobranca.causa_da_tensao(ambas, HOJE) == cobranca.TENSAO_AMBAS
    # A mesma escada nos três casos: a causa é rótulo, não decisão.
    for account in (so_satisfacao, so_entrega, ambas):
        assert cobranca.regua_para(account, HOJE) is cobranca.RELACAO_TENSA


@pytest.mark.django_db
def test_a_entrega_critica_nao_produz_avaliacao_muda() -> None:
    """A trava da camada 5 **não suspende e não cala** (ADR 0033): ela troca a escada e escala.
    Quem recua é gente, declarando a suspensão com dono, prazo e motivo."""
    account = AccountFactory()
    _entrega_em_frangalhos(account)

    avaliacao = cobranca.avaliar(_vencendo_em(12, account=account), HOJE)

    assert avaliacao.degrau is not None
    assert avaliacao.motivo == ""
    assert not CobrancaSuspensao.objects.exists()


@pytest.mark.django_db
def test_pagamento_no_prazo_nao_e_reincidencia() -> None:
    account = AccountFactory()
    InvoiceFactory(
        account=account, status=Invoice.Status.PAID,
        due_date=HOJE - timedelta(days=30),
        paid_at=timezone.make_aware(timezone.datetime(2026, 8, 3, 9, 0)),
    )
    assert cobranca.reincidente(account, HOJE) is False


# --- As guardas, uma por uma --------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "estado",
    [Invoice.Status.DRAFT, Invoice.Status.PAID, Invoice.Status.CANCELLED,
     Invoice.Status.RENEGOTIATED],
)
def test_estado_nao_cobravel_nao_tem_degrau(estado: str) -> None:
    invoice = _vencendo_em(12, status=estado)
    assert cobranca.avaliar(invoice, HOJE).motivo == cobranca.ESTADO_NAO_COBRAVEL


@pytest.mark.django_db
def test_suspensao_ativa_cala_e_suspensao_vencida_devolve() -> None:
    invoice = _vencendo_em(12)
    suspensao = CobrancaSuspensao.objects.create(
        invoice=invoice, owner=invoice.account.owner, until=HOJE, reason="Entrega atrasada."
    )
    assert cobranca.avaliar(invoice, HOJE).motivo == cobranca.SUSPENSA

    # `until` é inclusivo: no dia seguinte a régua volta sozinha, sem intervenção.
    assert cobranca.degrau_devido(invoice, HOJE + timedelta(days=1)).key == "firme"

    suspensao.until = HOJE + timedelta(days=10)
    suspensao.save()
    assert cobranca.avaliar(invoice, HOJE + timedelta(days=1)).motivo == cobranca.SUSPENSA


@pytest.mark.django_db
def test_suspensao_do_cliente_cala_todas_as_faturas_dele() -> None:
    account = AccountFactory()
    uma = _vencendo_em(12, account=account)
    outra = _vencendo_em(30, account=account)
    CobrancaSuspensao.objects.create(
        account=account, owner=account.owner, until=HOJE + timedelta(days=5), reason="Renegociando."
    )
    assert cobranca.degrau_devido(uma, HOJE) is None
    assert cobranca.degrau_devido(outra, HOJE) is None


@pytest.mark.django_db
def test_suspensao_levantada_nao_cala_mais() -> None:
    invoice = _vencendo_em(12)
    CobrancaSuspensao.objects.create(
        invoice=invoice, owner=invoice.account.owner, until=HOJE + timedelta(days=30),
        reason="Engano.", lifted_at=timezone.now(),
    )
    assert cobranca.degrau_devido(invoice, HOJE).key == "firme"


@pytest.mark.django_db
def test_o_teto_de_frequencia_e_por_cliente_somando_todas_as_faturas() -> None:
    """Quem tem três vencidas recebe um e-mail, não três."""
    account = AccountFactory()
    uma = _vencendo_em(12, account=account)
    outra = _vencendo_em(4, account=account)
    CobrancaContato.objects.create(
        invoice=uma, account=account, degrau="firme", canal=CobrancaContato.Canal.EMAIL,
        sent_on=HOJE, subject="x", body="y",
    )
    assert cobranca.avaliar(outra, HOJE).motivo == cobranca.TETO_DE_FREQUENCIA
    # Passados os cinco dias, a franquia volta.
    assert cobranca.pode_contatar(account, HOJE + timedelta(days=5)) is True
    assert cobranca.pode_contatar(account, HOJE + timedelta(days=4)) is False


@pytest.mark.django_db
def test_o_teto_nao_cala_a_escalada_interna() -> None:
    """O teto protege a caixa de entrada do cliente. A escalada não chega lá, e atrasá-la seria
    calar justamente o degrau que existe para acordar gente."""
    account = AccountFactory()
    uma = _vencendo_em(4, account=account)
    outra = _vencendo_em(22, account=account)
    CobrancaContato.objects.create(
        invoice=uma, account=account, degrau="lembrete", canal=CobrancaContato.Canal.EMAIL,
        sent_on=HOJE, subject="x", body="y",
    )
    assert cobranca.degrau_devido(outra, HOJE).key == "escalada"


@pytest.mark.django_db
def test_aviso_interno_nao_gasta_a_franquia_do_cliente() -> None:
    account = AccountFactory()
    uma = _vencendo_em(22, account=account)
    outra = _vencendo_em(4, account=account)
    CobrancaContato.objects.create(
        invoice=uma, account=account, degrau="escalada", canal=CobrancaContato.Canal.INTERNO,
        sent_on=HOJE, subject="x", body="y",
    )
    assert cobranca.degrau_devido(outra, HOJE).key == "lembrete"


@pytest.mark.django_db
def test_degrau_gasto_nao_se_repete() -> None:
    invoice = _vencendo_em(12)
    CobrancaContato.objects.create(
        invoice=invoice, account=invoice.account, degrau="firme",
        canal=CobrancaContato.Canal.EMAIL, sent_on=HOJE, subject="x", body="y",
    )
    assert cobranca.avaliar(invoice, HOJE).motivo == cobranca.DEGRAU_GASTO


# --- O job --------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_flag_desligada_e_um_no_op_silencioso() -> None:
    """A régua nasce desligada (FDD 036, "O pressuposto que não se cumpriu")."""
    _vencendo_em(12)
    resumo = cobranca.executar(HOJE)
    assert resumo["motivo"] == cobranca.FLAG_DESLIGADA
    assert CobrancaContato.objects.count() == 0
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_a_regua_nao_roda_em_fim_de_semana() -> None:
    _vencendo_em(12)
    sabado = date(2026, 9, 5)
    assert sabado.weekday() == 5
    resumo = cobranca.executar(sabado)
    assert resumo["motivo"] == cobranca.FIM_DE_SEMANA
    assert CobrancaContato.objects.count() == 0


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_o_pre_aviso_sai_por_email_ao_contato_de_cobranca() -> None:
    invoice = _vencendo_em(-3)
    _com_contato_de_cobranca(invoice.account)
    Contact.objects.create(account=invoice.account, first_name="Técnico", email="tech@cliente.test")

    resumo = cobranca.executar(HOJE)

    assert resumo["contatos"] == 1
    (enviado,) = mail.outbox
    # Só quem recebe cobrança. O contato técnico existe e não entra.
    assert enviado.to == ["financeiro@cliente.test"]
    assert "vence" in enviado.subject
    contato = CobrancaContato.objects.get()
    assert contato.degrau == "pre_aviso"
    assert contato.canal == CobrancaContato.Canal.EMAIL
    assert contato.sent_by_id is None  # nulo = automático
    assert contato.body == enviado.body  # a prova é o texto que saiu


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_sem_contato_de_cobranca_o_degrau_vira_escalada_interna() -> None:
    """Falha fechada: cala quando não sabe, e cala em voz alta."""
    invoice = _vencendo_em(4)

    cobranca.executar(HOJE)

    contato = CobrancaContato.objects.get()
    assert contato.degrau == "lembrete"
    assert contato.canal == CobrancaContato.Canal.INTERNO
    assert contato.to_email == ""
    assert "recebe cobrança" in contato.body
    assert Notification.objects.filter(user=invoice.account.owner, kind="cobranca").exists()


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_a_escalada_acorda_o_dono_do_cliente_e_os_admins_nao_a_equipe() -> None:
    """O destinatário é quem responde pela relação, não a equipe do projeto — e por isso a
    notificação sai **sem** `project=`, cujo filtro recortaria por participação."""
    dono = UserFactory(role=User.Role.SALES)
    admin = UserFactory(role=User.Role.ADMIN)
    entrega = UserFactory(role=User.Role.DELIVERY)
    account = AccountFactory(owner=dono)
    projeto = ProjectFactory(engagement__account=account)
    ProjectMemberFactory(project=projeto, user=entrega)
    _vencendo_em(22, account=account, project=projeto)

    resumo = cobranca.executar(HOJE)

    assert resumo["escaladas"] == 1
    avisados = set(Notification.objects.filter(kind="cobranca").values_list("user_id", flat=True))
    assert dono.pk in avisados
    assert admin.pk in avisados
    assert entrega.pk not in avisados


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_o_resumo_conta_os_calados_e_por_que() -> None:
    """Um job de cobrança que não manda nada é o caso comum; sem os motivos, a única leitura
    possível do silêncio é supor que ele quebrou."""
    calada = _vencendo_em(12)
    CobrancaSuspensao.objects.create(
        invoice=calada, owner=calada.account.owner, until=HOJE, reason="Entrega atrasada."
    )
    _vencendo_em(1)  # carência

    resumo = cobranca.executar(HOJE)

    assert resumo["avaliadas"] == 2
    assert resumo["calados"] == {cobranca.SUSPENSA: 1, cobranca.SEM_DEGRAU: 1}
    assert resumo["contatos"] == 0


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_uma_passada_nao_manda_dois_emails_ao_mesmo_cliente() -> None:
    """Quem tem duas faturas vencidas recebe um e-mail, não dois — **dentro da mesma passada**.

    O teto é a única dimensão que o próprio laço altera, e o job passou a ler tudo de um contexto
    pré-carregado (FDD 038). Sem contar o envio no contexto, a franquia continuaria constando livre
    depois do primeiro e-mail e o segundo sairia — regressão que a consulta fatura a fatura não
    tinha, e que nenhum orçamento de query acusaria.
    """
    account = AccountFactory()
    _com_contato_de_cobranca(account)
    _vencendo_em(4, account=account)
    _vencendo_em(5, account=account)

    resumo = cobranca.executar(HOJE)

    assert resumo["avaliadas"] == 2
    assert resumo["contatos"] == 1
    assert resumo["calados"] == {cobranca.TETO_DE_FREQUENCIA: 1}
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_a_passada_reage_a_entrega_critica_sem_suspender_nada() -> None:
    """Ponta a ponta da camada 5: em D+12 o cliente com entrega crítica recebe a **escalada
    interna** no lugar do degrau firme, e nenhuma suspensão nasce do job (ADR 0033)."""
    dono = UserFactory(role=User.Role.SALES)
    account = AccountFactory(owner=dono)
    _com_contato_de_cobranca(account)
    _entrega_em_frangalhos(account)
    _vencendo_em(12, account=account)

    resumo = cobranca.executar(HOJE)

    assert resumo["escaladas"] == 1
    assert resumo["contatos"] == 0
    assert CobrancaContato.objects.get().degrau == "escalada"
    # A escalada acorda gente e **não** fala com o cliente: o contato de cobrança não recebe nada
    # (o e-mail que sai é a cópia da notificação interna).
    destinos = {endereco for enviado in mail.outbox for endereco in enviado.to}
    assert "financeiro@cliente.test" not in destinos
    assert not CobrancaSuspensao.objects.exists()


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_o_email_que_nao_sai_nao_grava_contato(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registro gravado sem o envio ter acontecido é a classe de defeito que a homologação de
    integrações achou três vezes. Aqui ela custaria duas mentiras: o degrau constaria gasto (e a
    `UniqueConstraint` impediria a retentativa) e a tela diria que o cliente foi avisado."""
    invoice = _vencendo_em(4)
    _com_contato_de_cobranca(invoice.account)

    def explode(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("SMTP fora do ar")

    monkeypatch.setattr(cobranca, "send_mail", explode)

    resumo = cobranca.executar(HOJE)

    assert resumo["falhas"] == 1
    assert CobrancaContato.objects.count() == 0


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_o_comando_aceita_um_dia_fixo() -> None:
    invoice = _vencendo_em(4)
    _com_contato_de_cobranca(invoice.account)

    call_command("run_dunning", f"--hoje={HOJE.isoformat()}")

    assert CobrancaContato.objects.get().degrau == "lembrete"


@pytest.mark.django_db
def test_o_comando_recusa_uma_data_invalida() -> None:
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("run_dunning", "--hoje=ontem")


def test_o_valor_sai_em_formato_brasileiro() -> None:
    assert cobranca.moeda(Decimal("10000.01")) == "R$ 10.000,01"
    assert cobranca.moeda(Decimal("999.50")) == "R$ 999,50"


# --- O contrato -----------------------------------------------------------------------------


@pytest.fixture
def admin_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return api


@pytest.mark.django_db
def test_a_lista_de_cobranca_e_so_leitura(admin_api: APIClient) -> None:
    """Um POST aqui criaria a prova de um contato que não aconteceu."""
    invoice = _vencendo_em(12)
    CobrancaContato.objects.create(
        invoice=invoice, account=invoice.account, degrau="firme",
        canal=CobrancaContato.Canal.EMAIL, sent_on=HOJE, subject="x", body="y",
    )
    assert len(admin_api.get("/api/v1/cobranca/").json()) == 1
    assert admin_api.post("/api/v1/cobranca/", {}, format="json").status_code == 405


@pytest.mark.django_db
def test_a_rota_de_suspensoes_nao_e_engolida_pelo_detalhe_de_cobranca(admin_api: APIClient) -> None:
    """`^cobranca/(?P<pk>[^/.]+)/$` casaria com `cobranca/suspensoes/` lendo "suspensoes" como pk."""
    assert admin_api.get("/api/v1/cobranca/suspensoes/").status_code == 200


@pytest.mark.django_db
def test_suspender_exige_dono_prazo_e_motivo(admin_api: APIClient) -> None:
    invoice = _vencendo_em(12)
    dono = invoice.account.owner

    sem_motivo = admin_api.post(
        "/api/v1/cobranca/suspensoes/",
        {"invoice": invoice.pk, "owner": dono.pk, "until": "2026-10-01", "reason": "  "},
        format="json",
    )
    assert sem_motivo.status_code == 400

    nos_dois = admin_api.post(
        "/api/v1/cobranca/suspensoes/",
        {"invoice": invoice.pk, "account": invoice.account_id, "owner": dono.pk,
         "until": "2026-10-01", "reason": "Entrega atrasada."},
        format="json",
    )
    assert nos_dois.status_code == 400

    criada = admin_api.post(
        "/api/v1/cobranca/suspensoes/",
        {"invoice": invoice.pk, "owner": dono.pk, "until": "2026-10-01",
         "reason": "Entrega atrasada."},
        format="json",
    )
    assert criada.status_code == 201
    assert CobrancaSuspensao.objects.get().created_by_id is not None


@pytest.mark.django_db
def test_levantar_uma_suspensao_tem_autor_e_carimbo(admin_api: APIClient) -> None:
    invoice = _vencendo_em(12)
    suspensao = CobrancaSuspensao.objects.create(
        invoice=invoice, owner=invoice.account.owner, until=HOJE + timedelta(days=30),
        reason="Engano.",
    )
    resp = admin_api.post(f"/api/v1/cobranca/suspensoes/{suspensao.pk}/levantar/")
    assert resp.status_code == 200
    suspensao.refresh_from_db()
    assert suspensao.lifted_at is not None
    assert suspensao.lifted_by_id is not None
    # Levantar duas vezes é conflito de estado, não um segundo levantamento.
    assert admin_api.post(
        f"/api/v1/cobranca/suspensoes/{suspensao.pk}/levantar/"
    ).status_code == 409


@override_settings(DUNNING_ENABLED=True)  # o envio manual também passa pela flag
@pytest.mark.django_db
def test_enviar_manualmente_grava_o_autor_e_o_texto_revisado(admin_api: APIClient) -> None:
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)

    resp = admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "firme", "subject": "Sobre a fatura", "body": "Texto revisado por gente."},
        format="json",
    )

    assert resp.status_code == 201
    contato = CobrancaContato.objects.get()
    assert contato.sent_by_id is not None  # preenchido = uma pessoa apertou enviar
    assert contato.body == "Texto revisado por gente."
    assert mail.outbox[0].body == "Texto revisado por gente."


@override_settings(DUNNING_ENABLED=True)  # o envio manual também passa pela flag
@pytest.mark.django_db
def test_enviar_recusa_o_degrau_ja_gasto_com_409(admin_api: APIClient) -> None:
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)
    corpo = {"degrau": "firme", "body": "Texto."}
    assert admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/", corpo, format="json"
    ).status_code == 201
    assert admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/", corpo, format="json"
    ).status_code == 409


@override_settings(DUNNING_ENABLED=True)  # o envio manual também passa pela flag
@pytest.mark.django_db
def test_enviar_recusa_durante_a_suspensao(admin_api: APIClient) -> None:
    """Recuar é declarado; passar por cima em silêncio faria a declaração não valer nada."""
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)
    CobrancaSuspensao.objects.create(
        invoice=invoice, owner=invoice.account.owner,
        until=timezone.localdate() + timedelta(days=10), reason="Cliente insatisfeito.",
    )
    resp = admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "Texto."}, format="json",
    )
    assert resp.status_code == 409
    assert CobrancaContato.objects.count() == 0


@override_settings(DUNNING_ENABLED=True)  # o envio manual também passa pela flag
@pytest.mark.django_db
def test_enviar_recusa_fatura_paga(admin_api: APIClient) -> None:
    invoice = _vencendo_em(12, status=Invoice.Status.PAID)
    _com_contato_de_cobranca(invoice.account)
    resp = admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "Texto."}, format="json",
    )
    assert resp.status_code == 409


@override_settings(DUNNING_ENABLED=True)  # o envio manual também passa pela flag
@pytest.mark.django_db
def test_enviar_exige_texto_e_degrau_conhecido(admin_api: APIClient) -> None:
    invoice = _vencendo_em(12)
    assert admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "carinhoso", "body": "Texto."}, format="json",
    ).status_code == 400
    assert admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "   "}, format="json",
    ).status_code == 400


@override_settings(DUNNING_ENABLED=True)  # o envio manual também passa pela flag
@pytest.mark.django_db
def test_o_e_mail_que_nao_sai_pela_api_nao_grava_contato(
    admin_api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)

    def explode(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("SMTP fora do ar")

    monkeypatch.setattr(cobranca, "send_mail", explode)

    resp = admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "Texto."}, format="json",
    )
    assert resp.status_code == 502
    assert CobrancaContato.objects.count() == 0


# --- Camada 4: rascunho e classificação ---------------------------------------------------------


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_rascunhar_devolve_texto_e_nao_envia(
    admin_api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0031: o texto de IA nunca sai sozinho."""
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)
    monkeypatch.setattr(
        ai, "complete", lambda s, u, **_: ("Olá, sobre a fatura...", {"prompt_tokens": 1})
    )

    resp = admin_api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/rascunhar/", {"degrau": "firme"}, format="json"
    )

    assert resp.status_code == 200
    assert resp.json()["text"] == "Olá, sobre a fatura..."
    assert resp.json()["degrau"] == "firme"
    assert mail.outbox == []
    assert CobrancaContato.objects.count() == 0


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_rascunhar_sem_degrau_aplicavel_recusa(
    admin_api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A view chama `degrau_devido(invoice)` sem `hoje`, então o relógio que ela alcança precisa
    # estar congelado no mesmo dia usado pela fixture. Assim o caso continua na carência em
    # qualquer data de execução, inclusive depois de 02/09/2026.
    monkeypatch.setattr(cobranca.timezone, "localdate", lambda: HOJE)
    complete = Mock()
    monkeypatch.setattr(ai, "complete", complete)
    invoice = _vencendo_em(1)  # carência: a régua não indica degrau nenhum hoje
    resp = admin_api.post(f"/api/v1/invoices/{invoice.pk}/cobranca/rascunhar/", {}, format="json")
    assert resp.status_code == 400
    complete.assert_not_called()


@pytest.mark.django_db
def test_o_sinal_e_lido_do_json_e_o_desconhecido_e_descartado() -> None:
    from apps.core.views import sinal_do_texto

    assert sinal_do_texto('{"sinal": "unable_to_pay"}') == "unable_to_pay"
    assert sinal_do_texto('Claro!\n```json\n{"sinal": "forgot"}\n```') == "forgot"
    assert sinal_do_texto('{"sinal": "com_raiva"}') == ""
    assert sinal_do_texto("não consegui classificar") == ""
    assert sinal_do_texto('["forgot"]') == ""


@pytest.mark.django_db
def test_o_sinal_legado_e_tolerado_e_traduzido_para_o_canonico() -> None:
    """Tolerância de release (issue #122, fatia 5.2): a IA pode responder com cache ou variação
    do prompt anterior, e os três tokens antigos ainda traduzem — nunca persistem como vieram."""
    from apps.core.views import sinal_do_texto

    assert sinal_do_texto('{"sinal": "esqueceu"}') == "forgot"
    assert sinal_do_texto('{"sinal": "nao_pode"}') == "unable_to_pay"
    assert sinal_do_texto('{"sinal": "insatisfeito"}') == "dissatisfied"


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_classificar_grava_o_sinal_e_nao_age(
    admin_api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoice = _vencendo_em(12)
    activity = ActivityFactory(
        account=invoice.account, invoice=invoice, summary="Cliente disse que o caixa apertou."
    )
    monkeypatch.setattr(
        ai, "complete", lambda s, u, **_: ('{"sinal": "unable_to_pay"}', {"prompt_tokens": 1})
    )

    resp = admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    assert resp.status_code == 200
    activity.refresh_from_db()
    assert activity.dunning_signal == Activity.DunningSignal.UNABLE_TO_PAY
    # Classificar é leitura: nada foi suspenso, renegociado nem cobrado.
    assert CobrancaSuspensao.objects.count() == 0
    assert CobrancaContato.objects.count() == 0
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.ISSUED


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_classificar_com_sinal_legado_grava_o_canonico_pela_tolerancia(
    admin_api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O prompt pede os canônicos, mas a IA pode responder com cache do prompt anterior — a
    tolerância de release (issue #122, fatia 5.2) grava o canônico, nunca o token legado."""
    activity = ActivityFactory()
    monkeypatch.setattr(
        ai, "complete", lambda s, u, **_: ('{"sinal": "esqueceu"}', {"prompt_tokens": 1})
    )

    resp = admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    assert resp.status_code == 200
    activity.refresh_from_db()
    assert activity.dunning_signal == Activity.DunningSignal.FORGOT


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_classificar_sem_sinal_utilizavel_e_502(
    admin_api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gravar um valor chutado mandaria alguém insistir com quem está insatisfeito."""
    activity = ActivityFactory()
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: ("sei lá", {"prompt_tokens": 1}))

    resp = admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    assert resp.status_code == 502
    activity.refresh_from_db()
    assert activity.dunning_signal == ""


@pytest.mark.django_db
def test_o_sinal_nao_se_grava_por_patch(admin_api: APIClient) -> None:
    """O sinal é ato com procedência (a `AiInteraction`), não campo."""
    activity = ActivityFactory()
    resp = admin_api.patch(
        f"/api/v1/activities/{activity.pk}/", {"cobranca_sinal": "insatisfeito"}, format="json"
    )
    assert resp.status_code == 200
    activity.refresh_from_db()
    assert activity.dunning_signal == ""


@pytest.mark.django_db
def test_a_atividade_recusa_fatura_de_outro_cliente(admin_api: APIClient) -> None:
    activity = ActivityFactory()
    de_outro = _vencendo_em(12)
    resp = admin_api.patch(
        f"/api/v1/activities/{activity.pk}/", {"invoice": de_outro.pk}, format="json"
    )
    assert resp.status_code == 400


# --- Permissões ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_vendas_le_cobranca_suspende_e_nao_envia() -> None:
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))

    assert api.get("/api/v1/cobranca/").status_code == 200
    assert api.post(
        "/api/v1/cobranca/suspensoes/",
        {"invoice": invoice.pk, "owner": invoice.account.owner_id, "until": "2026-12-01",
         "reason": "Cliente insatisfeito."},
        format="json",
    ).status_code == 201
    assert api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "Texto."}, format="json",
    ).status_code == 403
    assert api.post(
        f"/api/v1/invoices/{invoice.pk}/cobranca/rascunhar/", {}, format="json"
    ).status_code == 403


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_a_corrida_entre_duas_execucoes_para_no_banco(monkeypatch: pytest.MonkeyPatch) -> None:
    """Duas réguas no mesmo tique (deploy sobreposto, scheduler escalado por engano).

    A guarda de `avaliar` é uma leitura, e leitura perde corrida. Quem arbitra é a
    `UniqueConstraint(invoice, degrau)`, e o `IntegrityError` que ela levanta é contado como
    "degrau gasto" — não como falha, porque é a idempotência funcionando.
    """
    invoice = _vencendo_em(12)
    _com_contato_de_cobranca(invoice.account)
    CobrancaContato.objects.create(
        invoice=invoice, account=invoice.account, degrau="firme",
        canal=CobrancaContato.Canal.EMAIL, sent_on=HOJE - timedelta(days=30), subject="x", body="y",
    )
    # Simula a outra execução tendo lido "cabe firme" antes de esta gravar. A assinatura espelha a
    # de `avaliar` inclusive no `contexto=`, que `executar` passa desde a FDD 038: um duplo que
    # aceita menos que o original faria este teste medir a assinatura em vez da corrida.
    monkeypatch.setattr(
        cobranca, "avaliar",
        lambda inv, dia=None, contexto=None: cobranca.Avaliacao(cobranca.PADRAO[2], ""),
    )

    resumo = cobranca.executar(HOJE)

    assert resumo["falhas"] == 0
    assert resumo["calados"] == {cobranca.DEGRAU_GASTO: 1}
    assert CobrancaContato.objects.filter(invoice=invoice, degrau="firme").count() == 1


# --- Achados da revisão do diff (FDD 036) ------------------------------------------------------
# Os três nasceram de leitura e foram confirmados por execução antes de virar correção. Ficam aqui
# porque cada um é uma guarda que sairia calada no próximo refactor.


@pytest.mark.django_db
def test_a_escalada_alcanca_o_superusuario_e_nao_so_o_papel_admin() -> None:
    """`createsuperuser` cria com `role` no default, e ele é o único admin de uma instalação nova.

    Filtrar por `role=admin` repetiria aqui o defeito que a FDD 017 corrigiu no SPA: quem autoriza
    no backend é `User.is_admin_role`, que é `role == admin **ou** is_superuser`. Numa instalação
    recém-subida, filtrar só pelo papel manda a escalada para ninguém — e o degrau é gasto uma vez.
    """
    root = User.objects.create_superuser("root", "root@example.test", "x")
    assert root.role != User.Role.ADMIN and root.is_admin_role
    dono = UserFactory(role=User.Role.SALES)
    cliente = AccountFactory(owner=dono)

    assert root in cobranca._internos(cliente)


@pytest.mark.django_db
def test_escalada_sem_ninguem_a_acordar_nao_gasta_o_degrau() -> None:
    """O "pular silencioso" que a RFC recusa, na direção que ninguém olha.

    Sem destinatário interno, gravar o contato produziria o pior dos dois mundos: a régua pararia
    de falar com o cliente (o degrau interno assumiu) e ninguém ficaria sabendo. O degrau não é
    gasto, a falha é contada, e ele volta a caber quando existir a quem escalar.
    """
    dono = UserFactory(role=User.Role.SALES, is_active=False)
    cliente = AccountFactory(owner=dono)
    fatura = _vencendo_em(21, account=cliente, status=Invoice.Status.OVERDUE)
    assert cobranca._internos(cliente) == []

    with pytest.raises(cobranca.SemDestinatarioInterno):
        cobranca.aplicar(fatura, cobranca.degrau_devido(fatura, HOJE), HOJE)

    assert not CobrancaContato.objects.filter(invoice=fatura).exists()
    # E continua devido: a condição é consertável por gente, e a régua espera.
    assert cobranca.degrau_devido(fatura, HOJE).key == "escalada"


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=False)
def test_o_envio_manual_tambem_respeita_a_flag() -> None:
    """A flag é o interruptor da funcionalidade, não só do relógio.

    Sem esta guarda, "Régua de cobrança: desligada" na tela de Configurações seria mentira: o job
    calaria e a API seguiria mandando cobrança ao cliente.
    """
    admin = UserFactory(role=User.Role.ADMIN)
    fatura = _vencendo_em(5)
    _com_contato_de_cobranca(fatura.account)
    api = APIClient()
    api.force_authenticate(admin)

    resposta = api.post(
        f"/api/v1/invoices/{fatura.pk}/cobranca/enviar/",
        {"degrau": "lembrete", "body": "texto revisado"},
        format="json",
    )

    assert resposta.status_code == 503
    assert not CobrancaContato.objects.exists()
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_suspensao_aceita_correcao_parcial_do_motivo() -> None:
    """`PATCH` só com o motivo não pode ser recusado por "vale para exatamente uma fatura ou um
    cliente" — a suspensão em disco já responde essa pergunta, e recusar aqui obrigaria a reenviar
    o vínculo a cada correção de texto."""
    from apps.core.serializers import CobrancaSuspensaoSerializer

    admin = UserFactory(role=User.Role.ADMIN)
    suspensao = CobrancaSuspensao.objects.create(
        account=AccountFactory(), owner=admin, until=HOJE + timedelta(days=7), reason="entrega atrasada"
    )

    serializer = CobrancaSuspensaoSerializer(suspensao, data={"reason": "renegociando"}, partial=True)

    assert serializer.is_valid(), serializer.errors


# --- O painel -----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_o_painel_traz_a_relacao_a_vista(admin_api: APIClient) -> None:
    """Critério de aceite 7 da FDD 036 e a exigência da seção Segurança da RFC: health, tempo de
    casa e valor do cliente **na mesma linha** do próximo degrau."""
    antigo = _cliente_de_casa()
    projeto = ProjectFactory(engagement__account=antigo)
    invoice = _vencendo_em(12, account=antigo, project=projeto)
    InvoiceFactory(
        account=antigo, status=Invoice.Status.PAID, number="2025-0100",
        amount=Decimal("40000.00"), due_date=HOJE - timedelta(days=200),
        paid_at=timezone.make_aware(timezone.datetime(2026, 2, 1, 9, 0)),
    )

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["invoice"] == invoice.pk
    assert linha["client_name"] == antigo.name
    assert linha["dias_de_atraso"] == (timezone.localdate() - invoice.due_date).days
    assert linha["health_level"] == "saudável"
    assert linha["tempo_de_casa_dias"] >= 800
    assert linha["reincidente"] is False
    assert linha["regua"] == "relacao_longa"
    # String e não número: `Decimal` pelo encoder do DRF viraria float, e centavo em ponto
    # flutuante é como se perde um centavo que ninguém acha seis meses depois.
    assert linha["recebido_do_cliente"] == "40000.00"
    assert linha["amount"] == "1000.00"
    assert linha["suspensao"] is None


@pytest.mark.django_db
def test_o_painel_traz_a_satisfacao_vigente_com_a_fonte(admin_api: APIClient) -> None:
    """A camada 5 na mesma linha (FDD 037): nível, fonte e idade ao lado do próximo degrau.

    A **fonte** vai junto e não é detalhe: é ela que diz se aquilo é o cliente falando ou a nossa
    leitura sobre ele — a diferença entre o que muda a escada e o que não muda.
    """
    account = AccountFactory()
    invoice = _fatura(due_date=timezone.localdate() - timedelta(days=12), account=account)
    SatisfactionRecord.objects.create(
        account=account, nivel=SatisfactionRecord.Nivel.NEUTRAL, fonte=SatisfactionRecord.Fonte.PERCEIVED,
        happened_on=timezone.localdate() - timedelta(days=4),
    )

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["invoice"] == invoice.pk
    assert linha["satisfacao_nivel"] == SatisfactionRecord.Nivel.NEUTRAL
    assert linha["satisfacao_fonte"] == SatisfactionRecord.Fonte.PERCEIVED
    assert linha["satisfacao_dias"] == 4
    # A percebida aparece e **não** troca a escada.
    assert linha["regua"] == "padrao"


@pytest.mark.django_db
def test_o_painel_nomeia_a_regua_tensa(admin_api: APIClient) -> None:
    account = AccountFactory()
    _fatura(due_date=timezone.localdate() - timedelta(days=12), account=account)
    SatisfactionRecord.objects.create(
        account=account, nivel=SatisfactionRecord.Nivel.DISSATISFIED, fonte=SatisfactionRecord.Fonte.DECLARED,
        happened_on=timezone.localdate(), note="Reclamou do atraso do marco 2.",
    )

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["regua"] == "relacao_tensa"
    assert linha["satisfacao_fonte"] == SatisfactionRecord.Fonte.DECLARED
    # O degrau firme deu lugar à escalada interna, e a linha não ficou muda.
    assert linha["proximo_degrau"] == "escalada"
    assert linha["motivo"] == ""


@pytest.mark.django_db
def test_o_painel_nomeia_a_causa_da_tensao(admin_api: APIClient) -> None:
    """A escada é a mesma nas duas origens, e é por isso que a causa vai na linha (FDD 038): sem
    ela a tela diria "relação tensa" e quem lê não saberia se conserta a entrega ou liga para o
    cliente."""
    account = AccountFactory()
    _fatura(due_date=timezone.localdate() - timedelta(days=12), account=account)
    _entrega_em_frangalhos(account)

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["regua"] == "relacao_tensa"
    assert linha["tensao_causa"] == cobranca.TENSAO_ENTREGA
    assert linha["satisfacao_nivel"] is None
    # A régua não ficou muda por causa da entrega: o degrau firme deu lugar à escalada interna.
    assert linha["proximo_degrau"] == "escalada"
    assert linha["motivo"] == ""


@pytest.mark.django_db
def test_o_painel_mostra_o_pior_health_do_cliente_e_nao_o_da_fatura(admin_api: APIClient) -> None:
    """A linha não pode contradizer o relógio (FDD 038): a guarda olha **todos** os projetos ativos
    do cliente, então mostrar o health do projeto da fatura diria "saudável" com a régua tensa."""
    account = AccountFactory()
    saudavel = ProjectFactory(engagement__account=account)
    _entrega_em_frangalhos(account)
    # A fatura está presa ao projeto **saudável**: é exatamente o caso em que as duas leituras
    # discordavam.
    _fatura(due_date=timezone.localdate() - timedelta(days=12), account=account, project=saudavel)

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["health_level"] == health.CRITICAL
    assert linha["regua"] == "relacao_tensa"


@pytest.mark.django_db
def test_o_painel_sem_projeto_ativo_nao_inventa_health(admin_api: APIClient) -> None:
    _fatura(due_date=timezone.localdate() - timedelta(days=12))

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["health_level"] is None
    assert linha["tensao_causa"] is None


@pytest.mark.django_db
def test_o_painel_traz_o_sinal_da_ia_como_leitura_por_registrar(admin_api: APIClient) -> None:
    """O `dunning_signal` ganha leitor (FDD 038): a resposta classificada aparece na linha como
    **leitura ainda não registrada**, com data, e é o atalho para uma pessoa registrar.

    Não é satisfação: nada aqui move o Health Score nem a escada — só o registro humano move
    (ADR 0032).
    """
    account = AccountFactory()
    _fatura(due_date=timezone.localdate() - timedelta(days=12), account=account)
    velha = ActivityFactory(
        account=account, dunning_signal=Activity.DunningSignal.FORGOT,
        happened_on=timezone.localdate() - timedelta(days=9),
    )
    ultima = ActivityFactory(
        account=account, dunning_signal=Activity.DunningSignal.DISSATISFIED,
        happened_on=timezone.localdate() - timedelta(days=2),
    )

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["sinal_activity"] == ultima.pk != velha.pk
    assert linha["sinal_kind"] == Activity.DunningSignal.DISSATISFIED
    assert linha["sinal_display"] == "Insatisfeito"
    assert linha["sinal_em"] == str(ultima.happened_on)
    # A leitura da IA **não** é registro: a escada segue a padrão e a satisfação vigente é nenhuma.
    assert linha["regua"] == "padrao"
    assert linha["satisfacao_nivel"] is None


@pytest.mark.django_db
def test_o_sinal_some_da_linha_depois_de_registrado(admin_api: APIClient) -> None:
    """Sem a ligação `source_activity`, o atalho insistiria para sempre — inclusive depois de a
    pessoa ter feito exatamente o que ele pedia."""
    account = AccountFactory()
    _fatura(due_date=timezone.localdate() - timedelta(days=12), account=account)
    activity = ActivityFactory(
        account=account, dunning_signal=Activity.DunningSignal.DISSATISFIED,
        happened_on=timezone.localdate() - timedelta(days=2),
    )

    (antes,) = admin_api.get("/api/v1/cobranca/painel/").json()
    assert antes["sinal_activity"] == activity.pk

    SatisfactionRecord.objects.create(
        account=account, source_activity=activity, nivel=SatisfactionRecord.Nivel.DISSATISFIED,
        fonte=SatisfactionRecord.Fonte.DECLARED, happened_on=activity.happened_on,
        note="Disse que a entrega do marco 2 atrasou duas vezes.",
    )

    (depois,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert depois["sinal_activity"] is None
    assert depois["sinal_kind"] is None
    assert depois["sinal_display"] is None
    assert depois["sinal_em"] is None
    # E agora sim a escada mudou — porque houve **registro**, não porque a IA leu.
    assert depois["regua"] == "relacao_tensa"
    assert depois["tensao_causa"] == cobranca.TENSAO_SATISFACAO


@pytest.mark.django_db
def test_o_painel_sem_registro_de_satisfacao_diz_nada_em_vez_de_omitir(
    admin_api: APIClient,
) -> None:
    _fatura(due_date=timezone.localdate() - timedelta(days=12))

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["satisfacao_nivel"] is None
    assert linha["satisfacao_fonte"] is None
    assert linha["satisfacao_dias"] is None


@pytest.mark.django_db
def test_o_painel_nomeia_o_degrau_e_quando_a_janela_abriu(admin_api: APIClient) -> None:
    invoice = _fatura(due_date=timezone.localdate() - timedelta(days=12))

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["proximo_degrau"] == "firme"
    assert linha["proximo_degrau_display"] == "Cobrança firme"
    # A janela do `firme` abre em D+10 — no passado, porque ele já cabe hoje.
    assert linha["proximo_degrau_em"] == str(invoice.due_date + timedelta(days=10))
    assert linha["motivo"] == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cenario", "motivo"),
    [("suspensa", cobranca.SUSPENSA), ("gasto", cobranca.DEGRAU_GASTO),
     ("teto", cobranca.TETO_DE_FREQUENCIA), ("carencia", cobranca.SEM_DEGRAU)],
)
def test_o_painel_nomeia_o_silencio(admin_api: APIClient, cenario: str, motivo: str) -> None:
    """Uma tela que só diz "nada hoje" ensina quem a usa a não confiar nela."""
    hoje = timezone.localdate()
    invoice = _fatura(due_date=hoje - timedelta(days=12))
    if cenario == "suspensa":
        CobrancaSuspensao.objects.create(
            invoice=invoice, owner=invoice.account.owner, until=hoje + timedelta(days=5),
            reason="Entrega atrasada.",
        )
    elif cenario == "gasto":
        CobrancaContato.objects.create(
            invoice=invoice, account=invoice.account, degrau="firme",
            canal=CobrancaContato.Canal.INTERNO, sent_on=hoje - timedelta(days=30),
            subject="x", body="y",
        )
    elif cenario == "teto":
        outra = _fatura(due_date=hoje - timedelta(days=40), account=invoice.account)
        CobrancaContato.objects.create(
            invoice=outra, account=invoice.account, degrau="lembrete",
            canal=CobrancaContato.Canal.EMAIL, sent_on=hoje, subject="x", body="y",
        )
    else:
        invoice.due_date = hoje - timedelta(days=1)
        invoice.save()

    linhas = admin_api.get("/api/v1/cobranca/painel/").json()
    linha = next(item for item in linhas if item["invoice"] == invoice.pk)

    assert linha["proximo_degrau"] is None
    assert linha["motivo"] == motivo


@pytest.mark.django_db
def test_o_painel_mostra_a_suspensao_com_prazo_e_dono(admin_api: APIClient) -> None:
    hoje = timezone.localdate()
    invoice = _fatura(due_date=hoje - timedelta(days=12))
    suspensao = CobrancaSuspensao.objects.create(
        account=invoice.account, owner=invoice.account.owner, until=hoje + timedelta(days=7),
        reason="Cliente insatisfeito.",
    )

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert linha["suspensao"]["id"] == suspensao.pk
    assert linha["suspensao"]["until"] == str(suspensao.until)
    assert linha["suspensao"]["owner"] == invoice.account.owner_id


@pytest.mark.django_db
def test_o_painel_so_lista_faturas_cobraveis(admin_api: APIClient) -> None:
    _fatura(due_date=timezone.localdate() - timedelta(days=12))
    for estado in (Invoice.Status.PAID, Invoice.Status.CANCELLED, Invoice.Status.DRAFT):
        _fatura(status=estado, due_date=timezone.localdate() - timedelta(days=40))

    linhas = admin_api.get("/api/v1/cobranca/painel/").json()

    assert len(linhas) == 1
    assert linhas[0]["status"] == Invoice.Status.ISSUED


@pytest.mark.django_db
def test_o_painel_nao_leva_custo_margem_nem_roi(admin_api: APIClient) -> None:
    """A mesma cerca comercial do rascunho de tom: o painel mostra o que já foi **recebido**, e
    nunca o que a casa calcula sobre si mesma."""
    projeto = ProjectFactory(actual_value=Decimal("250000.00"))
    _fatura(
        account=projeto.engagement.account, project=projeto, due_date=timezone.localdate() - timedelta(days=12)
    )

    (linha,) = admin_api.get("/api/v1/cobranca/painel/").json()

    assert "250000" not in str(linha)
    assert not {"actual_value", "roi", "roi_snapshot", "score", "signals"} & set(linha)


@pytest.mark.django_db
def test_o_painel_responde_com_a_flag_desligada_e_diz_isso(admin_api: APIClient) -> None:
    """É leitura, e serve para decidir se vale ligar. Mas prometer um degrau que não vai sair
    seria a tela mentindo por conta própria."""
    _fatura(due_date=timezone.localdate() - timedelta(days=12))

    (desligada,) = admin_api.get("/api/v1/cobranca/painel/").json()
    assert desligada["regua_ligada"] is False
    assert desligada["proximo_degrau"] == "firme"

    with override_settings(DUNNING_ENABLED=True):
        (ligada,) = admin_api.get("/api/v1/cobranca/painel/").json()
    assert ligada["regua_ligada"] is True


@pytest.mark.django_db
def test_o_painel_nao_e_engolido_pelo_detalhe_de_cobranca(admin_api: APIClient) -> None:
    """`^cobranca/(?P<pk>[^/.]+)/$` casaria com `cobranca/painel/` lendo "painel" como pk."""
    assert admin_api.get("/api/v1/cobranca/painel/").status_code == 200


@pytest.mark.django_db
def test_vendas_le_o_painel_e_entrega_nao() -> None:
    _fatura(due_date=timezone.localdate() - timedelta(days=12))

    vendas = APIClient()
    vendas.force_authenticate(UserFactory(role=User.Role.SALES))
    assert vendas.get("/api/v1/cobranca/painel/").status_code == 200

    entrega = APIClient()
    entrega.force_authenticate(UserFactory(role=User.Role.DELIVERY))
    assert entrega.get("/api/v1/cobranca/painel/").status_code == 403


@pytest.mark.django_db
def test_o_contexto_pre_carregado_da_a_mesma_resposta_da_consulta_individual() -> None:
    """O risco real da pré-carga não é a query — é divergir da decisão que ela substitui.

    Mesmo teste que a FDD 022 escreveu para `assess_projects_health`: se o agrupamento errar um
    `account_id`, a tela passa a mostrar o degrau do vizinho, e nenhum orçamento de query notaria.
    Os cenários são deliberadamente diferentes entre si para os resultados não coincidirem por acaso.
    """
    hoje = timezone.localdate()
    calada = _fatura(due_date=hoje - timedelta(days=12))
    CobrancaSuspensao.objects.create(
        invoice=calada, owner=calada.account.owner, until=hoje + timedelta(days=3), reason="x."
    )
    gasta = _fatura(due_date=hoje - timedelta(days=12))
    CobrancaContato.objects.create(
        invoice=gasta, account=gasta.account, degrau="firme", canal=CobrancaContato.Canal.INTERNO,
        sent_on=hoje - timedelta(days=30), subject="x", body="y",
    )
    no_teto = _fatura(due_date=hoje - timedelta(days=4))
    CobrancaContato.objects.create(
        invoice=_fatura(due_date=hoje - timedelta(days=40), account=no_teto.account),
        account=no_teto.account, degrau="lembrete", canal=CobrancaContato.Canal.EMAIL,
        sent_on=hoje, subject="x", body="y",
    )
    antigo = _cliente_de_casa()
    longa = _fatura(due_date=hoje - timedelta(days=12), account=antigo)
    normal = _fatura(due_date=hoje - timedelta(days=25))
    # Um cliente antigo **e** insatisfeito: o caso em que a escolha da escada muda, e o único em
    # que a pré-carga poderia divergir da consulta ao guardar a satisfação já escolhida — a
    # percebida de hoje esconderia a declarada de ontem.
    tenso = _cliente_de_casa()
    _insatisfacao(tenso, hoje - timedelta(days=1))
    SatisfactionRecord.objects.create(
        account=tenso, nivel=SatisfactionRecord.Nivel.SATISFIED, fonte=SatisfactionRecord.Fonte.PERCEIVED,
        happened_on=hoje,
    )
    tensa = _fatura(due_date=hoje - timedelta(days=12), account=tenso)
    # E um cliente tenso pela **entrega** (FDD 038), com dois projetos ativos de saúdes diferentes:
    # é o caso em que guardar o health do projeto da fatura, e não o pior do cliente, faria o lote
    # divergir da consulta.
    em_frangalhos = AccountFactory()
    saudavel = ProjectFactory(engagement__account=em_frangalhos)
    _entrega_em_frangalhos(em_frangalhos)
    critica = _fatura(due_date=hoje - timedelta(days=12), account=em_frangalhos, project=saudavel)

    faturas = [calada, gasta, no_teto, longa, normal, tensa, critica]
    contexto = cobranca.contexto_do_painel(faturas, hoje)

    for invoice in faturas:
        em_lote = cobranca.avaliar(invoice, hoje, contexto=contexto)
        individual = cobranca.avaliar(invoice, hoje)
        assert em_lote == individual, f"fatura {invoice.pk} divergiu"
        assert cobranca.regua_para(
            invoice.account, hoje, ignorando=invoice, contexto=contexto
        ) is cobranca.regua_para(invoice.account, hoje, ignorando=invoice)
        # A satisfação da linha do painel: de qualquer fonte, e a mesma pelos dois caminhos.
        # É aqui que guardar a **escolha** em vez dos registros divergiria — o cliente `tenso`
        # tem uma percebida de hoje por cima de uma declarada de ontem.
        em_lote_satisfacao = cobranca.satisfacao_vigente(invoice.account, hoje, contexto=contexto)
        individual_satisfacao = cobranca.satisfacao_vigente(invoice.account, hoje)
        assert (em_lote_satisfacao and em_lote_satisfacao.pk) == (
            individual_satisfacao and individual_satisfacao.pk
        )
        # A guarda da entrega pelos dois caminhos, e a causa que a tela mostra junto dela.
        assert cobranca.entrega_critica(
            invoice.account, hoje, contexto=contexto
        ) is cobranca.entrega_critica(invoice.account, hoje)
        assert cobranca.causa_da_tensao(
            invoice.account, hoje, contexto=contexto
        ) == cobranca.causa_da_tensao(invoice.account, hoje)
    assert cobranca.contexto_do_painel([], hoje).atrasos_por_cliente == {}


@pytest.mark.django_db
def test_um_contexto_de_outro_dia_e_recusado() -> None:
    """Silêncio (ou fala) calculado com o recorte do dia errado não deixaria nada vermelho."""
    hoje = timezone.localdate()
    invoice = _fatura(due_date=hoje - timedelta(days=12))
    contexto = cobranca.contexto_do_painel([invoice], hoje)

    with pytest.raises(ValueError):
        cobranca.avaliar(invoice, hoje + timedelta(days=1), contexto=contexto)
