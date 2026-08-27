"""A projeção do estado de engenharia do GitHub (FDD 041, ADR 0046).

Cobre o que a superfície do DAP GH-41 r1 depende de o backend garantir: assinatura, os dois
níveis de idempotência, os três erros distintos, a regra de obsolescência calculada aqui e a
reconciliação como rede de baixo do webhook.
"""

from __future__ import annotations

import hmac
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import github_projection
from apps.core.github_issues import (
    GitHubIssuesError,
    IssueSnapshot,
    PullRequestSnapshot,
    aggregate_check_runs,
)
from apps.core.models import EngineeringHandoff, GithubDelivery, GithubProjection

from .factories import (
    EngineeringHandoffFactory,
    GithubProjectionFactory,
    ProvisionedHandoffFactory,
)

SECRET = "segredo-de-fixture"
REPO = "acme/repo"


def assinatura(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()


def instante(minutos: int = 0) -> str:
    return (datetime(2026, 8, 27, 12, 0, tzinfo=UTC) + timedelta(minutes=minutos)).isoformat()


def payload_issue(numero: int, estado: str = "open", *, minutos: int = 0, titulo: str = "T") -> dict:
    return {
        "repository": {"full_name": REPO},
        "issue": {
            "number": numero,
            "state": estado,
            "title": titulo,
            "updated_at": instante(minutos),
        },
    }


def payload_pr(numero: int, issue: int, sha: str, *, minutos: int = 0, **pr: object) -> dict:
    corpo = {"number": numero, "state": "open", "head": {"sha": sha},
             "updated_at": instante(minutos), "title": "PR", "body": f"Closes #{issue}"}
    corpo.update(pr)
    return {"repository": {"full_name": REPO}, "pull_request": corpo}


# --- Assinatura ----------------------------------------------------------------


@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_assinatura_valida_do_corpo_cru() -> None:
    body = b'{"a": 1}'
    assert github_projection.verify_signature(body, {"X-Hub-Signature-256": assinatura(body)})


@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_assinatura_de_outro_segredo_nao_passa() -> None:
    body = b'{"a": 1}'
    assert not github_projection.verify_signature(
        body, {"X-Hub-Signature-256": assinatura(body, "outro")}
    )


@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_header_sem_prefixo_sha256_nao_passa() -> None:
    body = b'{"a": 1}'
    cru = assinatura(body).removeprefix("sha256=")
    assert not github_projection.verify_signature(body, {"X-Hub-Signature-256": cru})
    assert not github_projection.verify_signature(body, {})


@override_settings(GITHUB_WEBHOOK_SECRET="")
def test_sem_segredo_configurado_recusa_em_vez_de_aceitar() -> None:
    """Falha fechada (ADR 0018): não se aceita o que não se consegue verificar."""
    assert not github_projection.is_configured()
    with pytest.raises(github_projection.NotConfigured):
        github_projection.verify_signature(b"{}", {"X-Hub-Signature-256": "sha256=x"})


# --- Vínculo PR → Issue --------------------------------------------------------


def test_palavras_de_fechamento_ligam_o_pr_a_issue() -> None:
    achados = github_projection.linked_issue_numbers(
        "Closes #41 e fixes acme/repo#37, resolves outro/repo#9", REPO
    )
    assert achados == (41, 37)


def test_mencao_sem_palavra_de_fechamento_nao_liga() -> None:
    assert github_projection.linked_issue_numbers("Ver #41 para contexto", REPO) == ()


# --- Agregação de CI -----------------------------------------------------------


def test_agregacao_de_check_runs() -> None:
    assert aggregate_check_runs([]) == "none"
    assert aggregate_check_runs([("in_progress", "")]) == "pending"
    assert aggregate_check_runs([("completed", "success"), ("queued", "")]) == "pending"
    assert aggregate_check_runs([("completed", "success"), ("completed", "failure")]) == "failure"
    assert aggregate_check_runs([("completed", "success"), ("completed", "skipped")]) == "success"


# --- Aplicação de evento -------------------------------------------------------


@pytest.mark.django_db
def test_evento_de_issue_cria_a_projecao_do_handoff() -> None:
    handoff = ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)

    resultado = github_projection.receive("issues", "d-1", payload_issue(41, "closed", titulo="X"))

    assert resultado.applied == 1
    projecao = GithubProjection.objects.get(handoff=handoff)
    assert projecao.issue_state == GithubProjection.IssueState.CLOSED
    assert projecao.issue_title == "X"
    assert projecao.observed_via == GithubProjection.ObservedVia.WEBHOOK
    assert projecao.reference == "acme/repo#41"


@pytest.mark.django_db
def test_evento_de_pr_grava_numero_estado_e_sha() -> None:
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    github_projection.receive("issues", "d-1", payload_issue(41))

    github_projection.receive("pull_request", "d-2", payload_pr(90, 41, "a" * 40, minutos=1))

    projecao = GithubProjection.objects.get()
    assert projecao.pr_number == 90
    assert projecao.pr_state == GithubProjection.PrState.OPEN
    assert projecao.head_sha == "a" * 40


@pytest.mark.django_db
def test_pr_com_merge_e_terminal_esperado_e_nao_done() -> None:
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    github_projection.receive("issues", "d-1", payload_issue(41))

    github_projection.receive(
        "pull_request",
        "d-2",
        payload_pr(90, 41, "a" * 40, minutos=1, state="closed", merged=True),
    )

    assert GithubProjection.objects.get().pr_state == GithubProjection.PrState.MERGED


@pytest.mark.django_db
def test_sha_novo_apaga_o_ci_do_sha_velho() -> None:
    """Um verde certo sobre a revisão errada é pior que nenhum selo."""
    projecao = GithubProjectionFactory(
        handoff__repository=REPO,
        handoff__github_issue_number=41,
        head_sha="a" * 40,
        ci_state=GithubProjection.CiState.SUCCESS,
        pr_number=90,
        source_updated_at=timezone.now() - timedelta(hours=1),
    )

    github_projection.receive("pull_request", "d-9", payload_pr(90, 41, "b" * 40, minutos=5))

    projecao.refresh_from_db()
    assert projecao.head_sha == "b" * 40
    assert projecao.ci_state == GithubProjection.CiState.NONE


@pytest.mark.django_db
def test_check_suite_verde_pinta_o_ci_pelo_sha() -> None:
    projecao = GithubProjectionFactory(handoff__repository=REPO, head_sha="c" * 40)

    resultado = github_projection.receive(
        "check_suite",
        "d-3",
        {
            "repository": {"full_name": REPO},
            "check_suite": {
                "head_sha": "c" * 40,
                "status": "completed",
                "conclusion": "success",
                "updated_at": instante(2),
            },
        },
    )

    projecao.refresh_from_db()
    assert resultado.applied == 1
    assert projecao.ci_state == GithubProjection.CiState.SUCCESS


@pytest.mark.django_db
def test_check_run_isolado_nao_promove_o_conjunto_a_verde() -> None:
    """Um job que passou não diz nada sobre os outros doze; quem afirma verde é o `check_suite`."""
    projecao = GithubProjectionFactory(
        handoff__repository=REPO, head_sha="c" * 40, ci_state=GithubProjection.CiState.PENDING
    )

    github_projection.receive(
        "check_run",
        "d-4",
        {
            "repository": {"full_name": REPO},
            "check_run": {
                "head_sha": "c" * 40,
                "status": "completed",
                "conclusion": "success",
                "completed_at": instante(2),
            },
        },
    )

    projecao.refresh_from_db()
    assert projecao.ci_state == GithubProjection.CiState.PENDING


@pytest.mark.django_db
def test_check_run_reprovado_ja_pinta_de_vermelho() -> None:
    projecao = GithubProjectionFactory(
        handoff__repository=REPO, head_sha="c" * 40, ci_state=GithubProjection.CiState.PENDING
    )

    github_projection.receive(
        "check_run",
        "d-5",
        {
            "repository": {"full_name": REPO},
            "check_run": {
                "head_sha": "c" * 40,
                "status": "completed",
                "conclusion": "failure",
                "completed_at": instante(2),
            },
        },
    )

    projecao.refresh_from_db()
    assert projecao.ci_state == GithubProjection.CiState.FAILURE


@pytest.mark.django_db
def test_status_do_commit_tambem_alimenta_o_ci() -> None:
    projecao = GithubProjectionFactory(handoff__repository=REPO, head_sha="c" * 40)

    github_projection.receive(
        "status",
        "d-6",
        {
            "repository": {"full_name": REPO},
            "sha": "c" * 40,
            "state": "failure",
            "updated_at": instante(3),
        },
    )

    projecao.refresh_from_db()
    assert projecao.ci_state == GithubProjection.CiState.FAILURE


@pytest.mark.django_db
def test_evento_desconhecido_e_no_op_e_nao_registra_entrega() -> None:
    resultado = github_projection.receive("ping", "d-7", {"repository": {"full_name": REPO}})

    assert resultado.detail == "Evento ignorado."
    assert not GithubDelivery.objects.exists()


@pytest.mark.django_db
def test_evento_de_repositorio_sem_handoff_nao_cria_nada() -> None:
    resultado = github_projection.receive("issues", "d-8", payload_issue(41))

    assert resultado.applied == 0
    assert not GithubProjection.objects.exists()


@pytest.mark.django_db
def test_handoff_arquivado_some_do_alcance_do_webhook() -> None:
    handoff = ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    handoff.archive()

    github_projection.receive("issues", "d-1", payload_issue(41))

    assert not GithubProjection.objects.exists()


# --- Idempotência --------------------------------------------------------------


@pytest.mark.django_db
def test_entrega_repetida_e_no_op_pela_identidade_de_entrega() -> None:
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    github_projection.receive("issues", "d-1", payload_issue(41, "open", minutos=0))
    primeiro = GithubProjection.objects.get().observed_at

    resultado = github_projection.receive("issues", "d-1", payload_issue(41, "closed", minutos=5))

    assert resultado.duplicate
    projecao = GithubProjection.objects.get()
    assert projecao.issue_state == GithubProjection.IssueState.OPEN
    assert projecao.observed_at == primeiro
    assert GithubDelivery.objects.count() == 1


@pytest.mark.django_db
def test_entrega_fora_de_ordem_nao_sobrescreve_o_estado_atual() -> None:
    """O critério de aceite da Issue #41: reentrega atrasada com SHA velho não vence o atual."""
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    github_projection.receive("issues", "d-1", payload_issue(41))
    github_projection.receive("pull_request", "d-2", payload_pr(90, 41, "b" * 40, minutos=10))

    resultado = github_projection.receive(
        "pull_request", "d-3", payload_pr(90, 41, "a" * 40, minutos=1)
    )

    projecao = GithubProjection.objects.get()
    assert resultado.discarded == 1
    assert resultado.applied == 0
    assert projecao.head_sha == "b" * 40


@pytest.mark.django_db
def test_evento_do_mesmo_instante_e_aceito() -> None:
    """A guarda descarta o **anterior**, não o simultâneo — senão o reenvio legítimo sumiria."""
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    github_projection.receive("issues", "d-1", payload_issue(41, "open", minutos=5))

    resultado = github_projection.receive("issues", "d-2", payload_issue(41, "closed", minutos=5))

    assert resultado.applied == 1
    assert GithubProjection.objects.get().issue_state == GithubProjection.IssueState.CLOSED


# --- Obsolescência -------------------------------------------------------------


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
def test_obsolescencia_e_decidida_pelo_backend() -> None:
    fresca = GithubProjectionFactory()
    velha = GithubProjectionFactory(observed_at=timezone.now() - timedelta(hours=3))

    assert not fresca.is_stale()
    assert velha.is_stale()
    assert velha.age_seconds() >= 3 * 3600


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=0)
def test_limiar_zero_desliga_a_regra() -> None:
    assert not GithubProjectionFactory(observed_at=timezone.now() - timedelta(days=9)).is_stale()


# --- Reconciliação -------------------------------------------------------------


class FakeGithub:
    """Dublê de leitura. Sem I/O: o que se testa aqui é a decisão, não o `urllib`."""

    def __init__(
        self,
        *,
        issue: IssueSnapshot | None = None,
        pr: PullRequestSnapshot | None = None,
        ci: str = "none",
        erro: Exception | None = None,
    ) -> None:
        self.issue = issue or IssueSnapshot(
            state="closed", title="Do GitHub", updated_at=timezone.now()
        )
        self.pr = pr
        self.ci = ci
        self.erro = erro
        self.chamadas: list[str] = []

    def get_issue(self, repository: str, number: int) -> IssueSnapshot:
        self.chamadas.append(f"issue:{number}")
        if self.erro:
            raise self.erro
        return self.issue

    def get_pull_request(self, repository: str, number: int) -> PullRequestSnapshot:
        self.chamadas.append(f"pr:{number}")
        assert self.pr is not None
        return self.pr

    def get_check_state(self, repository: str, sha: str) -> str:
        self.chamadas.append(f"ci:{sha}")
        return self.ci


def erro_http(status: int) -> GitHubIssuesError:
    causa = urllib.error.HTTPError("https://api.github.com", status, "no", None, None)  # type: ignore[arg-type]
    erro = GitHubIssuesError(f"GitHub HTTP {status}")
    erro.__cause__ = causa
    return erro


@pytest.mark.django_db
def test_reconciliacao_cria_a_projecao_que_o_webhook_nunca_trouxe() -> None:
    """A rede de baixo: um webhook que não chegou não avisa que não chegou."""
    handoff = ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    cliente = FakeGithub()

    relatorio = github_projection.reconcile(client=cliente)

    projecao = GithubProjection.objects.get(handoff=handoff)
    assert relatorio.created == 1
    assert projecao.issue_state == GithubProjection.IssueState.CLOSED
    assert projecao.issue_title == "Do GitHub"
    assert projecao.observed_via == GithubProjection.ObservedVia.RECONCILIATION


@pytest.mark.django_db
def test_reconciliacao_ignora_handoff_nao_provisionado() -> None:
    EngineeringHandoffFactory(status=EngineeringHandoff.Status.PENDING)

    relatorio = github_projection.reconcile(client=FakeGithub())

    assert relatorio.created == 0
    assert not GithubProjection.objects.exists()


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
def test_reconciliacao_recupera_o_evento_perdido_e_deixa_a_fresca_em_paz() -> None:
    velha = GithubProjectionFactory(
        handoff__repository=REPO,
        observed_at=timezone.now() - timedelta(hours=4),
        issue_state=GithubProjection.IssueState.OPEN,
        pr_number=90,
        head_sha="a" * 40,
    )
    fresca = GithubProjectionFactory(handoff__repository=REPO)
    cliente = FakeGithub(
        pr=PullRequestSnapshot(
            number=90, state="closed", merged=True, head_sha="b" * 40, updated_at=timezone.now()
        ),
        ci="success",
    )

    relatorio = github_projection.reconcile(client=cliente)

    velha.refresh_from_db()
    assert relatorio.refreshed == 1
    assert relatorio.skipped == 1
    assert velha.issue_state == GithubProjection.IssueState.CLOSED
    assert velha.pr_state == GithubProjection.PrState.MERGED
    assert velha.head_sha == "b" * 40
    assert velha.ci_state == GithubProjection.CiState.SUCCESS
    assert velha.observed_via == GithubProjection.ObservedVia.RECONCILIATION
    assert fresca.observed_via == GithubProjection.ObservedVia.WEBHOOK


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
@pytest.mark.parametrize(
    ("erro", "esperado"),
    [
        (erro_http(500), GithubProjection.ErrorKind.UNAVAILABLE),
        (GitHubIssuesError("timeout"), GithubProjection.ErrorKind.UNAVAILABLE),
        (erro_http(403), GithubProjection.ErrorKind.FORBIDDEN),
        (erro_http(401), GithubProjection.ErrorKind.FORBIDDEN),
        (erro_http(404), GithubProjection.ErrorKind.MISSING),
    ],
)
def test_os_tres_erros_sao_distinguiveis_e_nenhum_apaga_a_projecao(
    erro: Exception, esperado: str
) -> None:
    """A ação corretiva de cada um é diferente, e é ela que decide quem age."""
    projecao = GithubProjectionFactory(
        handoff__repository=REPO,
        observed_at=timezone.now() - timedelta(hours=4),
        issue_state=GithubProjection.IssueState.CLOSED,
        head_sha="a" * 40,
        ci_state=GithubProjection.CiState.SUCCESS,
    )

    relatorio = github_projection.reconcile(client=FakeGithub(erro=erro))

    projecao.refresh_from_db()
    assert relatorio.failed == 1
    assert projecao.last_error_kind == esperado
    assert projecao.last_error_at is not None
    # O último estado conhecido continua **inteiro**: a tela o neutraliza, o backend não o apaga.
    assert projecao.issue_state == GithubProjection.IssueState.CLOSED
    assert projecao.ci_state == GithubProjection.CiState.SUCCESS


@pytest.mark.django_db
def test_falha_na_primeira_leitura_nao_cria_linha_sem_estado_observado() -> None:
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)

    relatorio = github_projection.reconcile(client=FakeGithub(erro=erro_http(404)))

    assert relatorio.failed == 1
    assert not GithubProjection.objects.exists()


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
def test_reconciliacao_bem_sucedida_limpa_o_erro_anterior() -> None:
    projecao = GithubProjectionFactory(
        handoff__repository=REPO,
        observed_at=timezone.now() - timedelta(hours=4),
        last_error_kind=GithubProjection.ErrorKind.FORBIDDEN,
        last_error_at=timezone.now() - timedelta(hours=1),
    )

    github_projection.reconcile(client=FakeGithub())

    projecao.refresh_from_db()
    assert projecao.last_error_kind == ""
    assert projecao.last_error_at is None


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
def test_reconciliacao_nao_baixa_o_carimbo_do_github() -> None:
    """Baixá-lo reabriria a janela que a guarda de ordem fecha."""
    recente = timezone.now()
    projecao = GithubProjectionFactory(
        handoff__repository=REPO,
        observed_at=timezone.now() - timedelta(hours=4),
        source_updated_at=recente,
    )
    antigo = IssueSnapshot(state="open", title="T", updated_at=recente - timedelta(days=1))

    github_projection.reconcile(client=FakeGithub(issue=antigo))

    projecao.refresh_from_db()
    assert projecao.source_updated_at == recente


@pytest.mark.django_db
def test_o_comando_sem_token_nao_toca_em_projecao(capsys: pytest.CaptureFixture[str]) -> None:
    """Erro de configuração não se disfarça de incidente do fornecedor."""
    from django.core.management import call_command

    projecao = GithubProjectionFactory(observed_at=timezone.now() - timedelta(days=2))

    with override_settings(GITHUB_TOKEN=""):
        call_command("reconcile_github_projections")

    projecao.refresh_from_db()
    assert projecao.last_error_kind == ""
    assert "GITHUB_TOKEN" in capsys.readouterr().out


@pytest.mark.django_db
def test_o_agendador_conhece_a_reconciliacao() -> None:
    from apps.core import scheduler

    assert "github_projection" in {job.name for job in scheduler.jobs()}


def test_json_do_payload_nao_precisa_de_repositorio_para_ser_ignorado() -> None:
    assert github_projection.parse_event("issues", json.loads("{}")) is None


# --- Payload malformado --------------------------------------------------------


@pytest.mark.parametrize(
    ("evento", "payload"),
    [
        ("issues", {"repository": {"full_name": REPO}, "issue": {"state": "open"}}),
        ("issues", {"repository": {"full_name": REPO}, "issue": {"number": 1, "state": "?"}}),
        ("pull_request", {"repository": {"full_name": REPO}, "pull_request": {"state": "open"}}),
        (
            "pull_request",
            {"repository": {"full_name": REPO}, "pull_request": {"number": 1, "state": "?"}},
        ),
        ("check_suite", {"repository": {"full_name": REPO}, "check_suite": {}}),
        ("check_run", {"repository": {"full_name": REPO}, "check_run": {}}),
        ("status", {"repository": {"full_name": REPO}, "state": "success"}),
        ("status", {"repository": {"full_name": REPO}, "sha": "c" * 40, "state": "?"}),
        ("deployment", {"repository": {"full_name": REPO}}),
    ],
)
def test_payload_sem_o_que_projetar_e_ignorado(evento: str, payload: dict) -> None:
    """Nada aqui pode levantar: exceção no parse viraria 500 e reentrega em laço."""
    assert github_projection.parse_event(evento, payload) is None


@pytest.mark.django_db
def test_check_suite_sem_sha_conhecido_alcanca_pelo_numero_do_pr() -> None:
    """O SHA é o caminho preciso; o número do PR é o que sobra quando ele ainda não chegou."""
    projecao = GithubProjectionFactory(handoff__repository=REPO, pr_number=90, head_sha="")

    github_projection.receive(
        "check_suite",
        "d-20",
        {
            "repository": {"full_name": REPO},
            "check_suite": {
                "head_sha": "z" * 40,
                "status": "in_progress",
                "conclusion": None,
                "updated_at": instante(4),
                "pull_requests": [{"number": 90}, {"nao": "tem numero"}, "lixo"],
            },
        },
    )

    projecao.refresh_from_db()
    assert projecao.ci_state == GithubProjection.CiState.PENDING


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=0)
def test_limiar_zero_faz_a_reconciliacao_reler_tudo() -> None:
    projecao = GithubProjectionFactory(handoff__repository=REPO, pr_number=90)
    cliente = FakeGithub(
        pr=PullRequestSnapshot(
            number=90, state="open", merged=False, head_sha="", updated_at=timezone.now()
        )
    )

    relatorio = github_projection.reconcile(client=cliente)

    projecao.refresh_from_db()
    assert relatorio.refreshed == 1
    assert projecao.pr_state == GithubProjection.PrState.OPEN


@pytest.mark.django_db
def test_o_comando_com_token_reporta_o_que_reconciliou(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from django.core.management import call_command

    monkeypatch.setattr(
        github_projection, "reconcile", lambda: github_projection.ReconcileReport(refreshed=2)
    )

    with override_settings(GITHUB_TOKEN="ghp_test"):
        call_command("reconcile_github_projections")

    assert "2 atualizada(s)" in capsys.readouterr().out
