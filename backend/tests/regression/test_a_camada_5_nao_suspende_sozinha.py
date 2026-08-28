"""Regressão: a trava da camada 5 **troca a escada; ela não suspende e não cala** (FDD 038).

É a segunda vez que o produto recusa a leitura literal de *"travas de relação plugadas nos sinais
de saúde e satisfação"* (RFC 0004, camada 5), e agora a recusa cobre a camada inteira. A seção
Segurança da mesma RFC proíbe o que essa leitura produz: *"recuar precisa ser declarado […] nunca
um 'pular' silencioso; vira desculpa para nunca cobrar, e o recebível estraga invisível"*.

O oráculo é duplo, e as duas metades morrem de jeitos diferentes:

1. **Nenhuma `CobrancaSuspensao` nasce de caminho de domínio.** Suspender é ato de gente, com dono,
   prazo e motivo, e chega por requisição. Um `objects.create()` conveniente dentro de `executar` —
   "o cliente está em frangalhos, melhor não cobrar agora" — pareceria cuidado e produziria
   exatamente a suspensão sem dono que a RFC recusa.
2. **A régua nunca fica muda por causa de health.** Nenhuma constante de motivo nova existe, e
   `avaliar` continua devolvendo degrau para o cliente com a entrega em frangalhos. Um
   `return Avaliacao(None, ENTREGA_CRITICA)` seria uma linha, passaria em qualquer teste de
   comportamento da escada, e calaria a cobrança de quem a casa está devendo — sem ninguém
   responder por isso.

É a invariante que um refactor bem intencionado apaga em silêncio, exatamente como a da ADR 0032.
"""

from datetime import date, timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import cobranca, health
from apps.core.models import (
    Account,
    CobrancaSuspensao,
    Contact,
    Invoice,
    Meeting,
    Milestone,
    Pendencia,
    Project,
    WorkItem,
)
from apps.core.tests.factories import AccountFactory, InvoiceFactory, ProjectFactory

HOJE = date(2026, 9, 2)  # quarta-feira, como no resto da suíte de cobrança

pytestmark = pytest.mark.django_db


def _entrega_em_frangalhos(account: Account) -> Project:
    """Projeto ativo com saúde **crítica**, pelos sinais que o `health.py` já mede.

    A asserção do fim é parte do cenário: se os pesos mudarem, este arquivo precisa falhar
    apontando o cenário, e não passar silenciosamente medindo um projeto saudável.
    """
    ontem = timezone.localdate() - timedelta(days=1)
    project = ProjectFactory(client=account, due_date=ontem)
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


def _vencida(account: Account, dias: int, numero: str) -> Invoice:
    return InvoiceFactory(
        account=account, status=Invoice.Status.OVERDUE, number=numero,
        due_date=HOJE - timedelta(days=dias),
    )


# --- Metade 1: ninguém recua sozinho ------------------------------------------


@override_settings(DUNNING_ENABLED=True)
def test_a_passada_da_regua_nao_cria_suspensao() -> None:
    """O job roda sobre a carteira com a entrega em frangalhos e não recua por conta própria."""
    account = AccountFactory()
    Contact.objects.create(
        account=account, first_name="Financeiro", email="financeiro@cliente.test",
        receives_billing=True,
    )
    _entrega_em_frangalhos(account)
    _vencida(account, 12, "2026-0001")

    cobranca.executar(HOJE)

    assert not CobrancaSuspensao.objects.exists()


def test_nenhum_caminho_de_dominio_cria_suspensao() -> None:
    """As funções que a tela e o job chamam, todas de uma vez: nenhuma delas recua.

    Quem cria `CobrancaSuspensao` é a viewset, via requisição, com dono e prazo no corpo — e é isso
    que faz o recuo ser declarado em vez de silencioso.
    """
    account = AccountFactory()
    _entrega_em_frangalhos(account)
    invoice = _vencida(account, 12, "2026-0002")

    cobranca.regua_para(account, HOJE, ignorando=invoice)
    cobranca.entrega_critica(account, HOJE)
    cobranca.causa_da_tensao(account, HOJE)
    cobranca.avaliar(invoice, HOJE)
    cobranca.painel(HOJE)

    assert not CobrancaSuspensao.objects.exists()


# --- Metade 2: a régua não fica muda ------------------------------------------


def test_a_entrega_critica_nao_cala_a_regua() -> None:
    """Ela troca a escada e escala. Parar de falar seria o "pular silencioso" com outro nome."""
    account = AccountFactory()
    _entrega_em_frangalhos(account)
    invoice = _vencida(account, 12, "2026-0003")

    avaliacao = cobranca.avaliar(invoice, HOJE)

    assert cobranca.regua_para(account, HOJE, ignorando=invoice) is cobranca.RELACAO_TENSA
    assert avaliacao.degrau is not None
    assert avaliacao.degrau.destino == cobranca.INTERNO  # escalada: acorda gente
    assert avaliacao.motivo == ""


@pytest.mark.parametrize("dias", [-2, 5, 10, 30])
def test_a_escada_da_entrega_responde_em_toda_a_janela(dias: int) -> None:
    """Em nenhum ponto da régua a entrega crítica produz silêncio novo: o que muda é qual degrau
    cabe, e o único buraco continua sendo a carência, que já existia."""
    account = AccountFactory()
    _entrega_em_frangalhos(account)
    invoice = _vencida(account, dias, f"2026-01{dias:02d}")

    com_frangalhos = cobranca.avaliar(invoice, HOJE)
    sem_frangalhos = cobranca.avaliar(
        _vencida(AccountFactory(), dias, f"2026-02{dias:02d}"), HOJE
    )

    assert com_frangalhos.degrau is not None
    # O silêncio possível é o mesmo dos dois lados — nunca um motivo que só a entrega produz.
    assert com_frangalhos.motivo == sem_frangalhos.motivo == ""


#: As constantes de texto que o módulo tem o direito de ter, por nome. Sete são motivos de
#: silêncio, dois são destinos de degrau e três são causas de tensão — estas últimas **não** calam
#: nada, só rotulam a tela.
CONSTANTES_CONHECIDAS = {
    "SEM_DEGRAU", "ESTADO_NAO_COBRAVEL", "SUSPENSA", "DEGRAU_GASTO", "TETO_DE_FREQUENCIA",
    "FIM_DE_SEMANA", "FLAG_DESLIGADA",
    "CLIENTE", "INTERNO",
    "TENSAO_SATISFACAO", "TENSAO_ENTREGA", "TENSAO_AMBAS",
}


def test_nenhuma_constante_de_motivo_nova_existe() -> None:
    """O oráculo estrutural, e o mais barato de todos: a régua tem sete motivos legítimos de calar,
    e nenhum deles é sobre a **nossa** entrega.

    A lista é por nome de propósito. Um `ENTREGA_CRITICA = "entrega_critica"` novo reprova aqui
    antes de existir um teste de comportamento para ele — que é o único momento em que alguém ainda
    vai ler o argumento da RFC em vez de completar o padrão que o arquivo sugere.
    """
    constantes = {
        nome
        for nome, valor in vars(cobranca).items()
        if nome.isupper() and isinstance(valor, str) and not nome.startswith("_")
    }

    assert constantes == CONSTANTES_CONHECIDAS
