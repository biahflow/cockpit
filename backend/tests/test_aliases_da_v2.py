"""A `/api/v2/` nasce, e a chave legada morre nela — leitura, escrita e filtro (issue #122).

`docs/ontology/aliases.md` sempre deu o mesmo prazo às rotas e às chaves de payload legadas: a
`/api/v2/`. Esta suíte é o que faz esse prazo existir em código, e ela tem três metades:

1. **O mapa e a execução não divergem.** `openapi_aliases.ALIASES_DEPRECIADOS` é o mesmo mapa que
   marca `deprecated: true` no `openapi.yaml` e o que `AliasesDaV1Mixin` lê para tirar a chave da
   resposta na v2. Os testes iteram o mapa — nunca copiam a lista dele —, então acrescentar um
   componente sem serializer que o execute fica vermelho aqui, e não em produção.
2. **A v2 recusa em vez de calar.** Chave legada no corpo e parâmetro legado na query respondem
   400 dizendo o nome canônico. O default do DRF (ignorar chave desconhecida) faria um `POST`
   legado responder 201 sem gravar o vínculo — o modo de falha mudo que a issue recusou.
3. **A v1 não muda.** As rotas, os `basename` e as chaves continuam como sempre. As seis
   regressões de `tests/regression/*_sobrevive_na_v1.py` são a prova principal disso e passam sem
   edição; o que se afirma aqui é a fronteira — a rota canônica não existe na v1 e a legada não
   existe na v2.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml
from django.conf import settings
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.core import ai, journey
from apps.core import serializers as modulo_de_serializers
from apps.core.models import (
    Activity,
    Case,
    CobrancaSuspensao,
    Contact,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    Document,
    DunningContact,
    Invoice,
    JourneyPhase,
    Meeting,
    PhaseEvent,
    PipelineStage,
    Project,
    ProjectPhase,
    SatisfactionRecord,
    SignatureRequest,
    User,
    Vertical,
)
from apps.core.openapi_aliases import (
    ALIASES_DEPRECIADOS,
    ALIASES_DEPRECIADOS_DE_DICT_CRU,
    ALIASES_DEPRECIADOS_NO_ESQUEMA,
    CANONICO_DA_CHAVE,
    excluir_a_v2_do_contrato,
)
from apps.core.serializers import (
    AliasesDaV1Mixin,
    _componente_do_serializer,
    _versao_do_contexto,
)
from apps.core.tests.factories import (
    AccountFactory,
    ActivityFactory,
    ArtifactFactory,
    CommercialOpportunityFactory,
    EngagementFactory,
    InvoiceFactory,
    LeadFactory,
    ProcessFactory,
    ProcessStepFactory,
    ProjectFactory,
    UserFactory,
    digital_employee_medido,
)
from apps.core.versioning import (
    V1,
    V2,
    VersaoPeloCaminho,
    frase_da_chave_removida,
    frase_da_chave_sem_sucessora,
    frase_do_parametro_removido,
    frase_do_valor_removido,
    versao_de,
)


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _requisicao(caminho: str) -> Request:
    """Uma requisição com a versão determinada pelo caminho, como no runtime.

    Passa pelo `VersaoPeloCaminho` de verdade em vez de cravar `request.version`: é a classe que
    responde "qual versão é esta", e um teste que a contorna afirmaria sobre um atributo em vez de
    sobre o mecanismo.
    """
    request = Request(APIRequestFactory().get(caminho))
    request.version = VersaoPeloCaminho().determine_version(request)
    return request


def _serializer_do_componente(componente: str) -> Any:
    return getattr(modulo_de_serializers, f"{componente}Serializer")


# ---------------------------------------------------------------------------------------------
# 1. O mapa e a execução não divergem
# ---------------------------------------------------------------------------------------------


def test_todo_componente_do_mapa_tem_serializer_que_executa_a_remocao() -> None:
    """A guarda que impede o mapa e a adoção de divergirem.

    Sem ela, uma entrada nova em `ALIASES_DEPRECIADOS` marcaria a chave como `deprecated` no
    contrato e a v2 continuaria emitindo-a — o contrato prometendo uma ausência que a resposta não
    cumpre, que é pior que não anunciar nada.
    """
    relatorio: list[str] = []
    for componente, propriedades in ALIASES_DEPRECIADOS.items():
        try:
            classe = _serializer_do_componente(componente)
        except AttributeError:
            relatorio.append(f"{componente}: nenhum {componente}Serializer em apps.core.serializers")
            continue
        if not issubclass(classe, AliasesDaV1Mixin):
            relatorio.append(f"{componente}: {classe.__name__} não herda AliasesDaV1Mixin")
            continue
        instancia = classe()
        if _componente_do_serializer(instancia) != componente:
            relatorio.append(
                f"{componente}: o serializer resolve para "
                f"{_componente_do_serializer(instancia)!r} — declare COMPONENTE_OPENAPI"
            )
            continue
        for propriedade in propriedades:
            if propriedade not in instancia.fields:
                relatorio.append(f"{componente}.{propriedade}: o serializer não declara a chave")

    assert relatorio == [], (
        "ALIASES_DEPRECIADOS e a adoção do mixin divergiram — o mapa anuncia uma depreciação que "
        "ninguém executa:\n  " + "\n  ".join(relatorio)
    )


def test_o_mapa_de_dict_cru_nao_tem_serializer_e_nao_se_sobrepoe_ao_outro() -> None:
    """A guarda simétrica da de cima, para o segundo mapa não virar a saída fácil dela.

    `ALIASES_DEPRECIADOS_DE_DICT_CRU` existe porque um `inline_serializer` não tem
    `<Componente>Serializer` por onde `AliasesDaV1Mixin` passe — a remoção é da view
    (`views._sem_chaves_legadas`). Sem esta guarda, mover uma entrada legítima para lá seria o jeito
    de fazer a guarda de cima calar sobre um componente que **tem** serializer: o mapa anunciaria a
    depreciação, o mixin não a executaria, e a v2 continuaria emitindo a chave.

    A segunda metade — os dois mapas disjuntos — é o que impede a mesma entrada de existir duas
    vezes com listas diferentes, que é a divergência silenciosa de sempre.
    """
    com_serializer = [
        componente
        for componente in ALIASES_DEPRECIADOS_DE_DICT_CRU
        if hasattr(modulo_de_serializers, f"{componente}Serializer")
    ]

    assert com_serializer == [], (
        "componente com serializer declarado em ALIASES_DEPRECIADOS_DE_DICT_CRU — ele pertence a "
        f"ALIASES_DEPRECIADOS, onde o mixin o executa: {com_serializer}"
    )
    assert not (set(ALIASES_DEPRECIADOS) & set(ALIASES_DEPRECIADOS_DE_DICT_CRU))
    assert set(ALIASES_DEPRECIADOS_NO_ESQUEMA) == (
        set(ALIASES_DEPRECIADOS) | set(ALIASES_DEPRECIADOS_DE_DICT_CRU)
    )


def _fase_ativa(project: Any) -> ProjectPhase:
    journey.materialize_journey(project)
    fase = ProjectPhase.objects.filter(project=project).first()
    assert fase is not None
    return fase


# Um construtor por componente do mapa. A declaração é comparada com o mapa no teste abaixo, então
# entrada nova sem caso de leitura fica vermelha — a lista não é uma cópia que envelhece sozinha.
CONSTRUTORES: dict[str, Callable[[], Any]] = {
    "Account": lambda: AccountFactory(),
    "Activity": lambda: ActivityFactory(),
    "Artifact": lambda: ArtifactFactory(),
    "Case": lambda: Case.objects.create(project=ProjectFactory(), title="Case de teste"),
    "CobrancaSuspensao": lambda: CobrancaSuspensao.objects.create(
        account=AccountFactory(),
        owner=UserFactory(),
        until=timezone.localdate() + timedelta(days=7),
        reason="Entrega atrasada por nossa conta.",
    ),
    "CommercialOpportunity": lambda: CommercialOpportunityFactory(),
    "Contact": lambda: Contact.objects.create(account=AccountFactory(), first_name="Ana"),
    "DigitalEmployee": lambda: digital_employee_medido(
        ProjectFactory(),
        baseline=Decimal("40.00"),
        current=Decimal("12.00"),
        name="Triagem",
        kpi_label="Horas por semana",
    ),
    "Document": lambda: Document.objects.create(
        account=AccountFactory(), original_name="contrato.pdf", uploaded_by=UserFactory()
    ),
    "DunningContact": lambda: DunningContact.objects.create(
        invoice=(fatura := InvoiceFactory()),
        account=fatura.account,
        dunning_step=DunningContact.DunningStep.REMINDER,
        canal=DunningContact.Canal.INTERNO,
        sent_on=timezone.localdate(),
    ),
    "Invoice": lambda: InvoiceFactory(),
    "Lead": lambda: LeadFactory(),
    "PhaseEvent": lambda: PhaseEvent.objects.create(
        project=(fase := _fase_ativa(ProjectFactory())).project,
        project_phase=fase,
        kind=PhaseEvent.Kind.GATE_RECORDED,
        gate_decision=ProjectPhase.GateDecision.GO,
    ),
    "Process": lambda: ProcessFactory(),
    "ProcessStep": lambda: ProcessStepFactory(),
    "Project": lambda: ProjectFactory(),
    "ProjectPhase": lambda: _fase_ativa(ProjectFactory()),
    "SatisfactionRecord": lambda: SatisfactionRecord.objects.create(
        account=AccountFactory(),
        nivel=SatisfactionRecord.Nivel.PROMOTER,
        fonte=SatisfactionRecord.Fonte.DECLARED,
        happened_on=timezone.localdate(),
    ),
}


def test_o_mapa_inteiro_tem_caso_de_leitura() -> None:
    """A tabela acima cobre o mapa, e não uma cópia dele feita um dia e esquecida depois."""
    assert set(CONSTRUTORES) == set(ALIASES_DEPRECIADOS)


@pytest.mark.django_db
@pytest.mark.parametrize("componente", sorted(ALIASES_DEPRECIADOS))
def test_a_v2_nao_emite_o_alias_e_a_v1_continua_emitindo(componente: str) -> None:
    """O contrato do drop, componente a componente, iterando o mapa.

    As duas metades importam: sem a asserção sobre a v1 este teste passaria com um serializer que
    perdeu a chave nas **duas** versões — que é exatamente a quebra da `/api/v1/` que a
    `docs/ontology/aliases.md` §2 proíbe até o sunset.
    """
    instancia = CONSTRUTORES[componente]()
    classe = _serializer_do_componente(componente)

    da_v1 = classe(instancia, context={"request": _requisicao("/api/v1/qualquer/")}).data
    da_v2 = classe(instancia, context={"request": _requisicao("/api/v2/qualquer/")}).data

    for propriedade in ALIASES_DEPRECIADOS[componente]:
        assert propriedade in da_v1, f"{componente}.{propriedade} sumiu da /api/v1/"
        assert propriedade not in da_v2, f"{componente}.{propriedade} ainda sai na /api/v2/"


@pytest.mark.django_db
def test_o_serializer_sem_requisicao_se_comporta_como_v1() -> None:
    """O portal, os agentes e os testes de unidade instanciam serializer fora de requisição.

    O default explícito é o que impede a v2 de vazar para quem nunca a pediu: sem ele, um
    serializer sem `request` no contexto perderia as chaves legadas por omissão.
    """
    conta = AccountFactory()
    serializer = modulo_de_serializers.AccountSerializer(conta)

    assert _versao_do_contexto(serializer) == V1
    assert versao_de(None) == V1
    assert "status" in serializer.data


def test_a_versao_sai_do_prefixo_do_caminho() -> None:
    """O mecanismo inteiro, medido direto: o prefixo diz a versão e nada mais decide."""
    esquema = VersaoPeloCaminho()
    fabrica = APIRequestFactory()

    assert esquema.determine_version(fabrica.get("/api/v2/accounts/")) == V2
    assert esquema.determine_version(fabrica.get("/api/v1/clients/")) == V1
    # Fora da API — o default é `v1`, e não um erro: quem chama isto é o serializer sem requisição.
    assert esquema.determine_version(fabrica.get("/admin/")) == V1


# ---------------------------------------------------------------------------------------------
# 2. As rotas: canônicas na v2, legadas na v1, nenhuma das duas nos dois lugares
# ---------------------------------------------------------------------------------------------


PARES_DE_ROTA: tuple[tuple[str, str], ...] = (
    ("clients", "accounts"),
    ("opportunities", "commercial-opportunities"),
    ("processos", "processes"),
    ("processo-etapas", "process-steps"),
    # O quinto par entrou na fatia 5.3, quando a classe ganhou nome canônico: enquanto ela se
    # chamava `Satisfacao`, a rota não tinha para onde ir (`docs/ontology/aliases.md`).
    ("satisfacoes", "satisfaction-records"),
)


@pytest.mark.django_db
@pytest.mark.parametrize(("legada", "canonica"), PARES_DE_ROTA)
def test_a_rota_legada_e_da_v1_e_a_canonica_e_da_v2(
    admin_client: APIClient, legada: str, canonica: str
) -> None:
    """Os cinco pares que a `docs/ontology/aliases.md` marcou para morrer na v2."""
    assert admin_client.get(f"/api/v1/{legada}/").status_code == 200
    assert admin_client.get(f"/api/v2/{canonica}/").status_code == 200
    assert admin_client.get(f"/api/v2/{legada}/").status_code == 404
    assert admin_client.get(f"/api/v1/{canonica}/").status_code == 404


@pytest.mark.django_db
def test_a_rota_que_nao_muda_responde_nas_duas_versoes(admin_client: APIClient) -> None:
    """Só cinco prefixos mudam; os outros 52 são a mesma rota sob os dois prefixos de versão."""
    assert admin_client.get("/api/v1/contacts/").status_code == 200
    assert admin_client.get("/api/v2/contacts/").status_code == 200
    # Fora do router, e pela mesma fábrica: as rotas explícitas já nascem canônicas.
    assert admin_client.get("/api/v2/config/").status_code == 200


@pytest.mark.django_db
def test_a_ordem_de_cobranca_vale_nos_dois_routers(admin_client: APIClient) -> None:
    """`cobranca/suspensoes` antes de `cobranca` — a ordem que o `registry` carrega de graça.

    Registrada depois, a rota de detalhe de `cobranca` sequestraria `cobranca/suspensoes/` lendo
    "suspensoes" como pk, e o sintoma seria um 404 de detalhe onde deveria haver uma coleção.
    """
    for prefixo in ("/api/v1/", "/api/v2/"):
        resposta = admin_client.get(f"{prefixo}cobranca/suspensoes/")
        assert resposta.status_code == 200, prefixo
        assert isinstance(resposta.data, list), prefixo


def test_os_nomes_de_url_da_v1_nao_mudaram_e_os_da_v2_nao_colidem() -> None:
    """`reverse()` é o que a issue #67 protegeu ao fixar os `basename`; a v2 entra ao lado dele.

    Sem o prefixo `v2-`, os nomes das duas versões colidiriam e `reverse("client-detail")`
    devolveria o alvo da última incluída — a v1 quebrando sem ninguém ter tocado nela.
    """
    assert reverse("client-list") == "/api/v1/clients/"
    assert reverse("client-detail", args=[7]) == "/api/v1/clients/7/"
    assert reverse("v2-client-list") == "/api/v2/accounts/"
    assert reverse("v2-client-detail", args=[7]) == "/api/v2/accounts/7/"
    # As rotas fora do router seguem a mesma regra de nome.
    assert reverse("config") == "/api/v1/config/"
    assert reverse("v2-config") == "/api/v2/config/"
    # E a raiz de cada router, que também é um nome de URL.
    assert reverse("api-root") == "/api/v1/"
    assert reverse("v2-api-root") == "/api/v2/"


# ---------------------------------------------------------------------------------------------
# 3. A escrita e o filtro: recusa dizendo o nome canônico
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_chave_legada_no_corpo_da_v2_e_400_dizendo_a_canonica(admin_client: APIClient) -> None:
    conta = AccountFactory()

    resposta = admin_client.post(
        "/api/v2/contacts/", {"client": conta.pk, "first_name": "Ana"}, format="json"
    )

    assert resposta.status_code == 400
    assert "client" in resposta.data
    assert "use 'account'" in str(resposta.data["client"])
    assert not Contact.objects.exists()


@pytest.mark.django_db
def test_a_chave_canonica_no_corpo_da_v2_cria(admin_client: APIClient) -> None:
    conta = AccountFactory()

    resposta = admin_client.post(
        "/api/v2/contacts/", {"account": conta.pk, "first_name": "Ana"}, format="json"
    )

    assert resposta.status_code == 201
    assert Contact.objects.get().account_id == conta.pk


@pytest.mark.django_db
def test_a_chave_legada_no_corpo_da_v1_continua_normalizando(admin_client: APIClient) -> None:
    """A contraprova da recusa acima: o que a v2 nega, a v1 aceita e traduz, como sempre."""
    conta = AccountFactory()

    resposta = admin_client.post(
        "/api/v1/contacts/", {"client": conta.pk, "first_name": "Ana"}, format="json"
    )

    assert resposta.status_code == 201
    assert Contact.objects.get().account_id == conta.pk


@pytest.mark.django_db
def test_o_parametro_legado_na_v2_e_400_dizendo_o_canonico(admin_client: APIClient) -> None:
    """Aceito e ignorado, `?client=` devolveria a lista inteira com cara de lista filtrada."""
    conta = AccountFactory()
    Contact.objects.create(account=conta, first_name="Ana")

    resposta = admin_client.get(f"/api/v2/contacts/?client={conta.pk}")

    assert resposta.status_code == 400
    assert "?account=" in str(resposta.data)


@pytest.mark.django_db
def test_o_parametro_canonico_filtra_na_v2_e_o_legado_na_v1(admin_client: APIClient) -> None:
    conta = AccountFactory()
    outra = AccountFactory()
    Contact.objects.create(account=conta, first_name="Ana")
    Contact.objects.create(account=outra, first_name="Bruno")

    da_v2 = admin_client.get(f"/api/v2/contacts/?account={conta.pk}")
    da_v1 = admin_client.get(f"/api/v1/contacts/?client={conta.pk}")

    assert da_v2.status_code == 200
    assert [linha["first_name"] for linha in da_v2.data] == ["Ana"]
    assert da_v1.status_code == 200
    assert [linha["first_name"] for linha in da_v1.data] == ["Ana"]


# ---------------------------------------------------------------------------------------------
# 4. O contrato publicado descreve a v1, e só ela — por ora
# ---------------------------------------------------------------------------------------------


def test_o_openapi_commitado_nao_descreve_a_v2() -> None:
    """A v2 entra no `openapi.yaml` quando a forma dele for verdadeira (fatia 3, artefato próprio).

    Publicá-la agora emitiria caminhos apontando para componentes que ainda mostram as
    chaves-alias, e `deprecated: true` não é `ausente`: o contrato diria que
    `GET /api/v2/accounts/` devolve `status`, que é justamente o que a v2 não faz.
    """
    contrato = yaml.safe_load(
        (Path(settings.BASE_DIR) / "openapi.yaml").read_text(encoding="utf-8")
    )
    caminhos = list(contrato["paths"])

    assert [caminho for caminho in caminhos if caminho.startswith("/api/v2/")] == []
    assert any(caminho.startswith("/api/v1/") for caminho in caminhos)


def test_o_hook_do_esquema_filtra_a_v2_e_preserva_a_v1() -> None:
    """O mecanismo do teste acima, medido direto — e por palavra-chave, como o pacote o chama."""
    endpoints = [
        ("/api/v1/accounts/", "^/api/v1/accounts/$", "GET", object()),
        ("/api/v2/accounts/", "^/api/v2/accounts/$", "GET", object()),
        ("/api/v1/contacts/", "^/api/v1/contacts/$", "POST", object()),
    ]

    restantes = excluir_a_v2_do_contrato(endpoints=endpoints)

    assert [caminho for caminho, *_ in restantes] == ["/api/v1/accounts/", "/api/v1/contacts/"]


# ---------------------------------------------------------------------------------------------
# 5. Os quatro pontos que a fatia 1 não alcançava, e a lacuna do read-only (issue #122, fatia 3a)
# ---------------------------------------------------------------------------------------------


# Sem `ESIGN_PROVIDER`: o registro local do `NullProvider` (ADR 0059), longe da rede — o mesmo
# ajuste da regressão `test_o_alias_signer_email_sobrevive_na_v1.py`.
_REGISTRO_LOCAL_DE_ASSINATURA = override_settings(
    ESIGN_ENABLED=True, ESIGN_PROVIDER="", ESIGN_HOUSE_SIGNER_EMAIL=""
)


@pytest.mark.django_db
@_REGISTRO_LOCAL_DE_ASSINATURA
def test_signer_email_e_400_na_v2_e_continua_criando_na_v1(admin_client: APIClient) -> None:
    """`_signers_do_pedido` não passa por serializer — a recusa mora na view, não no mixin."""
    document = Document.objects.create(
        account=AccountFactory(), original_name="contrato.pdf", uploaded_by=UserFactory(),
        kind=Document.Kind.COMMERCIAL_CONTRACT,
    )

    da_v2 = admin_client.post(
        reverse("v2-document-request-signature", args=[document.pk]),
        {"signer_email": "quem.assina@cliente.test"},
        format="json",
    )

    assert da_v2.status_code == 400
    assert "use 'signers'" in str(da_v2.data["detail"])
    assert not SignatureRequest.objects.exists()

    da_v1 = admin_client.post(
        reverse("document-request-signature", args=[document.pk]),
        {"signer_email": "quem.assina@cliente.test"},
        format="json",
    )

    assert da_v1.status_code == 201
    assert SignatureRequest.objects.get().signer_email == "quem.assina@cliente.test"


def _fase_ativa_com_gate(project: Any) -> ProjectPhase:
    """A mesma preparação de `test_o_alias_do_gate_sobrevive_na_v1.py`: a fase ativa exige gate."""
    journey.materialize_journey(project)
    ativa = ProjectPhase.objects.filter(
        project=project, status=ProjectPhase.Status.ACTIVE
    ).first()
    assert ativa is not None
    JourneyPhase.objects.filter(pk=ativa.phase_id).update(requires_gate=True)
    ativa.refresh_from_db()
    return ativa


@pytest.mark.django_db
def test_outcome_e_400_na_v2_e_decision_continua_funcionando(admin_client: APIClient) -> None:
    """A recusa vem antes do `or` que lê as duas chaves — `outcome` nunca chega a ser lido na v2."""
    project = ProjectFactory()
    fase = _fase_ativa_com_gate(project)

    recusado = admin_client.post(
        reverse("v2-project-apply-gate", args=[project.pk]),
        {"outcome": "no_go", "notes": "tentativa com o alias"},
        format="json",
    )

    assert recusado.status_code == 400
    assert "use 'decision'" in str(recusado.data["detail"])
    fase.refresh_from_db()
    assert fase.gate_decision == ""

    aceito = admin_client.post(
        reverse("v2-project-apply-gate", args=[project.pk]),
        {"decision": "no_go", "notes": "pela chave canônica"},
        format="json",
    )

    assert aceito.status_code == 200
    fase.refresh_from_db()
    assert fase.gate_decision == "no_go"


@pytest.mark.django_db
def test_o_painel_de_cobranca_tem_os_dois_pares_na_v1_e_so_o_canonico_na_v2(
    admin_client: APIClient,
) -> None:
    """`cobranca.painel()` emite os dois; a view tira o par legado só na v2."""
    invoice = InvoiceFactory(status=Invoice.Status.ISSUED)

    (linha_v1,) = admin_client.get("/api/v1/cobranca/painel/").json()
    (linha_v2,) = admin_client.get("/api/v2/cobranca/painel/").json()

    assert linha_v1["account"] == invoice.account_id
    assert linha_v1["account_name"] == invoice.account.name
    assert linha_v1["client"] == invoice.account_id
    assert linha_v1["client_name"] == invoice.account.name

    assert linha_v2["account"] == invoice.account_id
    assert linha_v2["account_name"] == invoice.account.name
    assert "client" not in linha_v2
    assert "client_name" not in linha_v2


def _reuniao_de_discovery() -> Meeting:
    return Meeting.objects.create(
        project=ProjectFactory(), title="Discovery", date=timezone.localdate(),
        transcript="O faturamento é conferido nota a nota.",
    )


def _responde_com(monkeypatch: pytest.MonkeyPatch, texto: str) -> None:
    monkeypatch.setattr(
        ai, "complete", lambda s, u, **_: (texto, {"prompt_tokens": 5, "completion_tokens": 3}),
    )


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_a_action_de_ia_troca_a_chave_por_versao(
    admin_client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`processos` na v1, `processes` na v2 — a chave troca, não convive (issue #122, fatia 3a)."""
    mapa = '[{"name": "Faturamento mensal", "etapas": [], "achados": []}]'

    reuniao_v1 = _reuniao_de_discovery()
    _responde_com(monkeypatch, mapa)
    da_v1 = admin_client.post(reverse("meeting-estruturar", args=[reuniao_v1.pk]))
    assert da_v1.status_code == 200, da_v1.data
    assert [p["name"] for p in da_v1.data["processos"]] == ["Faturamento mensal"]
    assert "processes" not in da_v1.data

    reuniao_v2 = _reuniao_de_discovery()
    _responde_com(monkeypatch, mapa)
    da_v2 = admin_client.post(reverse("v2-meeting-estruturar", args=[reuniao_v2.pk]))
    assert da_v2.status_code == 200, da_v2.data
    assert [p["name"] for p in da_v2.data["processes"]] == ["Faturamento mensal"]
    assert "processos" not in da_v2.data


@pytest.mark.django_db
def test_o_alias_so_de_leitura_no_corpo_da_v2_e_recusado(admin_client: APIClient) -> None:
    """A lacuna que a fatia 1 registrou: `client`/`kpi_baseline` eram `read_only` e ignorados."""
    conta = AccountFactory()
    engagement = EngagementFactory(account=conta)

    projeto = admin_client.post(
        "/api/v2/projects/",
        {
            "name": "Projeto novo",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
            "engagement": engagement.pk,
            "client": conta.pk,
        },
        format="json",
    )

    assert projeto.status_code == 400
    assert "use 'account'" in str(projeto.data["client"])
    assert not Project.objects.exists()

    ativo = DigitalEmployee.objects.create(project=ProjectFactory(), name="Triagem")

    medicao = admin_client.patch(
        f"/api/v2/digital-employees/{ativo.pk}/", {"kpi_baseline": "999.00"}, format="json"
    )

    assert medicao.status_code == 400
    assert medicao.data["kpi_baseline"] == [frase_da_chave_sem_sucessora("kpi_baseline")]

    # A contraprova: na v1 a mesma chave continua sendo aceita e ignorada (regressão da §2d).
    ignorado = admin_client.patch(
        f"/api/v1/digital-employees/{ativo.pk}/", {"kpi_baseline": "999.00"}, format="json"
    )
    assert ignorado.status_code == 200


@pytest.mark.django_db
def test_status_continua_funcionando_em_componente_sem_entrada_no_mapa(
    admin_client: APIClient,
) -> None:
    """ARMADILHA: `status` é campo real de outros serializers — a recusa é por componente."""
    conta = AccountFactory()
    origem = CommercialOpportunityFactory(
        account=conta, stage=PipelineStage.objects.get(kind="won")
    )

    resposta = admin_client.post(
        "/api/v2/engagements/",
        {
            "account": conta.pk,
            "name": "Mandato de teste",
            "status": "paused",
            # A invariante 13 (migração `0074`) exige o instrumento assinado que originou o
            # mandato; o teste não é sobre proveniência, só sobre `status` continuar gravável.
            "originating_commercial_opportunity": origem.pk,
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["status"] == "paused"


# ---------------------------------------------------------------------------------------------
# 6. As chaves «client» residuais, que nunca tinham entrado no mapa (issue #122, fatia 4a)
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_o_nome_da_conta_sai_pelos_dois_nomes_na_v1_e_so_pelo_canonico_na_v2(
    admin_client: APIClient,
) -> None:
    """`client_name` era projeção sem canônica: a v2 nasceria sem nome nenhum para a conta.

    Um representativo dos cinco `ModelSerializer` que a fatia 4a acertou — a iteração de
    `test_a_v2_nao_emite_o_alias_e_a_v1_continua_emitindo` já cobre a **ausência** nos outros
    quatro; o que se afirma aqui é a metade que ela não vê, a canônica **presente** nas duas.
    """
    fatura = InvoiceFactory()

    da_v1 = admin_client.get(f"/api/v1/invoices/{fatura.pk}/").json()
    da_v2 = admin_client.get(f"/api/v2/invoices/{fatura.pk}/").json()

    assert da_v1["account_name"] == da_v1["client_name"] == fatura.account.name
    assert da_v2["account_name"] == fatura.account.name
    assert "client_name" not in da_v2


@pytest.mark.django_db
def test_a_vertical_do_projeto_sai_pelos_dois_nomes_na_v1_e_so_pelo_canonico_na_v2(
    admin_client: APIClient,
) -> None:
    """`client_vertical`/`client_vertical_name` — projeção sobre `engagement.account.vertical`.

    Nunca houve coluna `Project.client_vertical`: o campo do modelo é `Account.vertical`, e o que
    a fatia 4a paga é a **chave de payload** (`docs/ontology/aliases.md` §2c).
    """
    vertical = Vertical.objects.create(name="Igrejas", slug="igrejas")
    conta = AccountFactory(vertical=vertical)
    projeto = ProjectFactory(engagement=EngagementFactory(account=conta))

    da_v1 = admin_client.get(f"/api/v1/projects/{projeto.pk}/").json()
    da_v2 = admin_client.get(f"/api/v2/projects/{projeto.pk}/").json()

    assert da_v1["account_vertical"] == da_v1["client_vertical"] == vertical.pk
    assert da_v1["account_vertical_name"] == da_v1["client_vertical_name"] == "Igrejas"
    assert da_v2["account_vertical"] == vertical.pk
    assert da_v2["account_vertical_name"] == "Igrejas"
    assert "client_vertical" not in da_v2
    assert "client_vertical_name" not in da_v2


@pytest.mark.django_db
def test_a_visao_agregada_de_contas_troca_a_chave_por_versao(admin_client: APIClient) -> None:
    """`clients` na v1, `accounts` na v2 — a chave envolve a lista inteira, então **troca**.

    Mesmo precedente de `processos`/`processes` na action de IA (fatia 3a): duplicar pagaria o
    corpo do grid duas vezes, e aqui — ao contrário do resto do payload legado — não há um par que
    saia junto.
    """
    conta = AccountFactory()

    da_v1 = admin_client.get("/api/v1/clients/overview/").json()
    da_v2 = admin_client.get("/api/v2/accounts/overview/").json()

    assert [linha["client_id"] for linha in da_v1["clients"]] == [conta.pk]
    assert "accounts" not in da_v1
    # `client_id` some da própria linha na v2 desde a fatia 4c — a linha lê pela canônica.
    assert [linha["account_id"] for linha in da_v2["accounts"]] == [conta.pk]
    assert "clients" not in da_v2


@pytest.mark.django_db
def test_o_recorte_do_roi_por_conta_troca_a_chave_por_versao(admin_client: APIClient) -> None:
    """`roi.by_client` na v1, `roi.by_account` na v2 — a segunda chave da fatia 4a que **troca**.

    Mesmo precedente da visão agregada logo acima e de `processos`/`processes` na action de IA: a
    chave envolve a lista inteira do recorte, e duplicá-la pagaria o recorte duas vezes.

    A conta nasce com projeto, receita e custo de propósito. Um recorte vazio sai `[]` nas duas
    versões e passaria este teste sem provar nada sobre a chave que o envolve — que é justamente o
    que se afirma aqui.
    """
    conta = AccountFactory(name="Conta do Recorte")
    ProjectFactory(
        engagement=EngagementFactory(account=conta),
        actual_value=Decimal("1000"),
        cost=Decimal("400"),
    )

    da_v1 = admin_client.get("/api/v1/analytics/").json()["roi"]
    da_v2 = admin_client.get("/api/v2/analytics/").json()["roi"]

    assert [linha["label"] for linha in da_v1["by_client"]] == ["Conta do Recorte"]
    assert "by_account" not in da_v1
    assert [linha["label"] for linha in da_v2["by_account"]] == ["Conta do Recorte"]
    assert "by_client" not in da_v2


@pytest.mark.django_db
def test_a_visao_compacta_da_entrega_tem_os_dois_nomes_na_v1_e_so_o_canonico_na_v2(
    admin_client: APIClient,
) -> None:
    """O segundo dict cru, e por isso o segundo chamador de `views._sem_chaves_legadas`."""
    projeto = ProjectFactory()

    (linha_v1,) = admin_client.get("/api/v1/projects/timeline-overview/").json()
    (linha_v2,) = admin_client.get("/api/v2/projects/timeline-overview/").json()

    nome = projeto.engagement.account.name
    assert linha_v1["account_name"] == linha_v1["client_name"] == nome
    assert linha_v2["account_name"] == nome
    assert "client_name" not in linha_v2


@pytest.mark.django_db
def test_o_alias_de_nome_no_corpo_da_v2_e_recusado(admin_client: APIClient) -> None:
    """A recusa por componente vale para as chaves novas: `client_name` diz `account_name`.

    Não há escrita por nenhuma das duas (são projeção), e é justamente por isso que a recusa
    importa: sem ela a chave cairia no campo `read_only` do DRF, aceita e ignorada — o modo de
    falha mudo que a decisão 3 da ADR 0066 recusou.
    """
    fatura = InvoiceFactory()

    resposta = admin_client.patch(
        f"/api/v2/invoices/{fatura.pk}/", {"client_name": "Outra Conta"}, format="json"
    )

    assert resposta.status_code == 400
    assert "use 'account_name'" in str(resposta.data["client_name"])


def test_todo_valor_nao_nulo_de_canonico_da_chave_cobre_aliases_depreciados() -> None:
    """A guarda do mapa novo: toda chave de `ALIASES_DEPRECIADOS` tem entrada em `CANONICO_DA_CHAVE`.

    Sem ela, uma chave nova em `ALIASES_DEPRECIADOS` seria recusada na v2 sem saber o que dizer —
    `CANONICO_DA_CHAVE.get(antiga)` devolveria `None` por ausência, e a recusa mentiria dizendo
    "sem sucessora" para uma chave que tem uma.
    """
    todas_as_chaves_depreciadas = {
        chave
        for propriedades in ALIASES_DEPRECIADOS_NO_ESQUEMA.values()
        for chave in propriedades
    }

    assert todas_as_chaves_depreciadas <= set(CANONICO_DA_CHAVE)


# ---------------------------------------------------------------------------------------------
# 7. As linhas cruas do overview pagam a lacuna declarada (issue #122, fatia 4c)
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_linha_do_overview_agregado_paga_a_lacuna_declarada(admin_client: APIClient) -> None:
    """`client_id`/`status` de cada linha do grid — a lacuna que a ADR 0066 (emenda da fatia 4a)
    declarou fora do contrato por ser dict cru sem item tipado no esquema. A fatia 4c paga na
    resposta: as duas legadas continuam na v1 ao lado das canônicas, e somem na v2.
    """
    conta = AccountFactory()

    (linha_v1,) = admin_client.get("/api/v1/clients/overview/").json()["clients"]
    (linha_v2,) = admin_client.get("/api/v2/accounts/overview/").json()["accounts"]

    assert linha_v1["account_id"] == linha_v1["client_id"] == conta.pk
    assert linha_v1["lifecycle_status"] == linha_v1["status"] == conta.lifecycle_status
    assert linha_v2["account_id"] == conta.pk
    assert linha_v2["lifecycle_status"] == conta.lifecycle_status
    assert "client_id" not in linha_v2
    assert "status" not in linha_v2


@pytest.mark.django_db
def test_o_detalhe_do_overview_paga_a_mesma_lacuna(admin_client: APIClient) -> None:
    """A mesma dívida na rota de detalhe — uma linha só, sem lista a indexar por cima."""
    conta = AccountFactory()

    da_v1 = admin_client.get(reverse("client-overview-detail", args=[conta.pk])).json()
    da_v2 = admin_client.get(reverse("v2-client-overview-detail", args=[conta.pk])).json()

    assert da_v1["account_id"] == da_v1["client_id"] == conta.pk
    assert da_v1["lifecycle_status"] == da_v1["status"] == conta.lifecycle_status
    assert da_v2["account_id"] == conta.pk
    assert da_v2["lifecycle_status"] == conta.lifecycle_status
    assert "client_id" not in da_v2
    assert "status" not in da_v2


# ---------------------------------------------------------------------------------------------
# 8. O VALOR do enum também atravessa por versão — a área do blueprint (issue #122, fatia 5.1)
#
# Mecanismo novo, e diferente do resto do arquivo: `ALIASES_DEPRECIADOS`/`ALIASES_DE_ENTRADA`
# tratam **chave** de payload; aqui o campo `area` nunca mudou de nome, só o que ele persiste
# mudou de idioma (D10). Por isso o par de mapas é outro
# (`AliasesDaV1Mixin.VALORES_DE_ENTRADA`/`QueryParamFilterMixin.filter_valores_legados`) e a
# recusa da v2 também é outra: no corpo, quem fala é o `choices` do DRF (400 padrão); só no filtro,
# onde ninguém valida nada, é que existe frase dedicada (`versioning.frase_do_valor_removido`).
# ---------------------------------------------------------------------------------------------


def _migracao_0084() -> Any:
    """O módulo da migração, importado por caminho — `0084...` não é identificador Python."""
    return importlib.import_module("apps.core.migrations.0084_a_area_do_blueprint_fala_ingles")


@pytest.mark.django_db
def test_a_migracao_traduz_os_cinco_pares_e_a_reversa_e_simetrica() -> None:
    """A primeira migração de VALOR do repositório — testada como função, e não só como estado.

    O banco de teste já rodou a `0084` (o schema tem os choices ingleses); o que falta comprovar é
    que o `RunPython` traduz as cinco linhas certas nos dois sentidos. `.update()` no queryset,
    como o forward faz, contorna `full_clean()` — é assim que se põe um valor pt-BR na coluna sem
    passar pela validação que esta própria migração torna obsoleta.
    """
    from django.apps import apps as registro_de_apps

    modulo = _migracao_0084()
    pares = modulo._PARES_PT_PARA_EN

    blueprints = {
        antigo: DigitalEmployeeBlueprint.objects.create(name=f"Bloco {antigo}")
        for antigo, _novo in pares
    }
    for antigo, blueprint in blueprints.items():
        DigitalEmployeeBlueprint.objects.filter(pk=blueprint.pk).update(area=antigo)

    modulo.traduzir_para_ingles(registro_de_apps, None)
    for antigo, novo in pares:
        blueprints[antigo].refresh_from_db()
        assert blueprints[antigo].area == novo

    modulo.traduzir_para_portugues(registro_de_apps, None)
    for antigo, _novo in pares:
        blueprints[antigo].refresh_from_db()
        assert blueprints[antigo].area == antigo


@pytest.mark.django_db
def test_nenhum_blueprint_tem_valor_pt_e_os_choices_sao_os_novos() -> None:
    """A prova de estado, complementar à de função: o catálogo atual só conhece os choices novos."""
    DigitalEmployeeBlueprint.objects.create(name="Bloco padrão")

    valores_portugueses = {"comercial", "financeiro", "rh", "juridico", "atendimento"}
    persistidos = set(DigitalEmployeeBlueprint.objects.values_list("area", flat=True))

    assert not (persistidos & valores_portugueses)
    assert tuple(DigitalEmployeeBlueprint.Area.values) == (
        "commercial", "finance", "hr", "legal", "support",
    )


@pytest.mark.django_db
def test_o_valor_legado_no_corpo_da_v1_normaliza_e_o_display_continua_pt(
    admin_client: APIClient,
) -> None:
    """Quem escrevia `"comercial"` ontem continua funcionando hoje — e o que persiste é o canônico."""
    resposta = admin_client.post(
        "/api/v1/digital-employee-blueprints/", {"name": "SDR", "area": "comercial"}, format="json"
    )

    assert resposta.status_code == 201
    assert resposta.data["area"] == "commercial"
    assert resposta.data["area_display"] == "Comercial"
    assert DigitalEmployeeBlueprint.objects.get().area == "commercial"


@pytest.mark.django_db
def test_o_valor_legado_no_corpo_da_v2_e_400_de_choices_do_drf(admin_client: APIClient) -> None:
    """A v2 não traduz nem recusa com frase própria: quem fala é o `choices` do campo, de graça."""
    resposta = admin_client.post(
        "/api/v2/digital-employee-blueprints/", {"name": "SDR", "area": "comercial"}, format="json"
    )

    assert resposta.status_code == 400
    assert "comercial" in str(resposta.data["area"])
    assert not DigitalEmployeeBlueprint.objects.exists()


@pytest.mark.django_db
def test_o_valor_canonico_no_corpo_da_v2_cria(admin_client: APIClient) -> None:
    resposta = admin_client.post(
        "/api/v2/digital-employee-blueprints/", {"name": "SDR", "area": "commercial"}, format="json"
    )

    assert resposta.status_code == 201
    assert DigitalEmployeeBlueprint.objects.get().area == "commercial"


@pytest.mark.django_db
def test_o_filtro_aceita_o_valor_legado_e_o_canonico_na_v1(admin_client: APIClient) -> None:
    DigitalEmployeeBlueprint.objects.create(
        name="SDR", area=DigitalEmployeeBlueprint.Area.COMMERCIAL
    )
    DigitalEmployeeBlueprint.objects.create(
        name="Cobrador", area=DigitalEmployeeBlueprint.Area.FINANCE
    )

    pelo_legado = admin_client.get("/api/v1/digital-employee-blueprints/?area=comercial")
    pelo_canonico = admin_client.get("/api/v1/digital-employee-blueprints/?area=commercial")

    assert [b["name"] for b in pelo_legado.json()] == ["SDR"]
    assert [b["name"] for b in pelo_canonico.json()] == ["SDR"]


@pytest.mark.django_db
def test_o_filtro_com_valor_legado_na_v2_e_400_dizendo_o_canonico(admin_client: APIClient) -> None:
    """Lista vazia seria o silêncio que a #122 recusa — a v2 recusa o valor, e diz qual usar."""
    DigitalEmployeeBlueprint.objects.create(
        name="SDR", area=DigitalEmployeeBlueprint.Area.COMMERCIAL
    )

    resposta = admin_client.get("/api/v2/digital-employee-blueprints/?area=comercial")

    assert resposta.status_code == 400
    assert "?area=" in str(resposta.data)
    assert "use 'commercial'" in str(resposta.data)


@pytest.mark.django_db
def test_o_filtro_com_valor_canonico_continua_funcionando_na_v2(admin_client: APIClient) -> None:
    DigitalEmployeeBlueprint.objects.create(
        name="SDR", area=DigitalEmployeeBlueprint.Area.COMMERCIAL
    )
    DigitalEmployeeBlueprint.objects.create(
        name="Cobrador", area=DigitalEmployeeBlueprint.Area.FINANCE
    )

    resposta = admin_client.get("/api/v2/digital-employee-blueprints/?area=commercial")

    assert [b["name"] for b in resposta.json()] == ["SDR"]


# ---------------------------------------------------------------------------------------------
# 9. Os TRÊS renomes juntos — Activity.DunningSignal (issue #122, fatia 5.2)
#
# Diferente da seção 8: ali só o VALOR mudou (a classe já nascia inglesa). Aqui classe, campo
# (`cobranca_sinal` → `dunning_signal`) e valor atravessam juntos (D10), e o campo é `read_only` —
# não há `ALIASES_DE_ENTRADA`/`VALORES_DE_ENTRADA` a testar, porque não há caminho de escrita
# direta. O que a v2 recusa é a CHAVE (mecanismo da seção 3/8 de `ALIASES_DEPRECIADOS`), não o
# valor — o valor nunca chega a ser aceito na v2 porque a chave já morreu ali.
# ---------------------------------------------------------------------------------------------


def _migracao_0085() -> Any:
    """O módulo da migração, importado por caminho — `0085...` não é identificador Python."""
    return importlib.import_module("apps.core.migrations.0085_o_sinal_de_cobranca_fala_ingles")


@pytest.mark.django_db
def test_a_migracao_0085_traduz_os_tres_pares_do_sinal_e_a_reversa_e_simetrica() -> None:
    """A segunda migração de VALOR do repositório, e a primeira depois de um `RenameField`.

    O banco de teste já rodou a `0085` (o schema tem `dunning_signal` com os choices ingleses); o
    que falta comprovar é que o `RunPython` traduz as três linhas certas nos dois sentidos, sobre o
    nome de coluna **novo** — o mesmo molde de teste da `0084`, adaptado ao campo renomeado.
    """
    from django.apps import apps as registro_de_apps

    modulo = _migracao_0085()
    pares = modulo._PARES_PT_PARA_EN

    activities = {antigo: ActivityFactory() for antigo, _novo in pares}
    for antigo, activity in activities.items():
        Activity.objects.filter(pk=activity.pk).update(dunning_signal=antigo)

    modulo.traduzir_para_ingles(registro_de_apps, None)
    for antigo, novo in pares:
        activities[antigo].refresh_from_db()
        assert activities[antigo].dunning_signal == novo

    modulo.traduzir_para_portugues(registro_de_apps, None)
    for antigo, _novo in pares:
        activities[antigo].refresh_from_db()
        assert activities[antigo].dunning_signal == antigo


@pytest.mark.django_db
def test_nenhuma_activity_tem_sinal_pt_e_os_choices_sao_os_novos() -> None:
    """A prova de estado, complementar à de função: o enum atual só conhece os choices novos."""
    ActivityFactory()

    valores_portugueses = {"esqueceu", "nao_pode", "insatisfeito"}
    persistidos = set(Activity.objects.values_list("dunning_signal", flat=True))

    assert not (persistidos & valores_portugueses)
    assert tuple(Activity.DunningSignal.values) == ("forgot", "unable_to_pay", "dissatisfied")


@pytest.mark.django_db
def test_a_leitura_da_v1_emite_os_quatro_e_a_v2_so_os_canonicos(admin_client: APIClient) -> None:
    """`GET /activities/` — o par canônico e o par legado na v1, e só o canônico na v2."""
    activity = ActivityFactory(dunning_signal=Activity.DunningSignal.DISSATISFIED)

    da_v1 = admin_client.get(f"/api/v1/activities/{activity.pk}/").json()
    da_v2 = admin_client.get(f"/api/v2/activities/{activity.pk}/").json()

    assert da_v1["dunning_signal"] == "dissatisfied"
    assert da_v1["dunning_signal_display"] == "Insatisfeito"
    assert da_v1["cobranca_sinal"] == "dissatisfied"
    assert da_v1["cobranca_sinal_display"] == "Insatisfeito"

    assert da_v2["dunning_signal"] == "dissatisfied"
    assert da_v2["dunning_signal_display"] == "Insatisfeito"
    assert "cobranca_sinal" not in da_v2
    assert "cobranca_sinal_display" not in da_v2


@pytest.mark.django_db
def test_a_chave_legada_do_sinal_no_corpo_da_v2_e_400_dizendo_a_canonica(
    admin_client: APIClient,
) -> None:
    """A lacuna do read-only (decisão 3a): `cobranca_sinal` era ignorado em silêncio na v2."""
    activity = ActivityFactory()

    resposta = admin_client.patch(
        f"/api/v2/activities/{activity.pk}/", {"cobranca_sinal": "forgot"}, format="json"
    )

    assert resposta.status_code == 400
    assert resposta.data["cobranca_sinal"] == [
        frase_da_chave_removida("cobranca_sinal", "dunning_signal")
    ]
    activity.refresh_from_db()
    assert activity.dunning_signal == ""

    # A contraprova: a v1 continua aceitando a chave legada — read-only, então ignorada, como
    # sempre foi (regressão de `test_o_sinal_nao_se_grava_por_patch`).
    ignorado = admin_client.patch(
        f"/api/v1/activities/{activity.pk}/", {"cobranca_sinal": "forgot"}, format="json"
    )
    assert ignorado.status_code == 200
    activity.refresh_from_db()
    assert activity.dunning_signal == ""


# ---------------------------------------------------------------------------------------------
# 10. Classe, tabela e DOIS enums de valor — SatisfactionRecord (issue #122, fatia 5.3)
#
# Terceira família de D10, e a que combina os dois mecanismos anteriores num serializer só: o de
# VALOR da seção 8 (`VALORES_DE_ENTRADA`/`filter_valores_legados`, porque `nivel` e `fonte` são
# graváveis, ao contrário do sinal read-only da seção 9) e o de ROTA da seção 2, que ganha o
# quinto par. A novidade é a **tabela**: `RenameModel` puro, sem `Meta.db_table` a preservar,
# porque a pk desta família não é uma das seis identidades externas da `aliases.md` §2b — o
# registro sequer atravessa para o portal do cliente (ADR 0032).
# ---------------------------------------------------------------------------------------------


def _migracao_0086() -> Any:
    """O módulo da migração, importado por caminho — `0086...` não é identificador Python."""
    return importlib.import_module("apps.core.migrations.0086_a_satisfacao_fala_ingles")


def _satisfacao(**kwargs: Any) -> SatisfactionRecord:
    campos: dict[str, Any] = {
        "account": AccountFactory(),
        "nivel": SatisfactionRecord.Nivel.NEUTRAL,
        "fonte": SatisfactionRecord.Fonte.DECLARED,
        "happened_on": timezone.localdate(),
    }
    campos.update(kwargs)
    return SatisfactionRecord.objects.create(**campos)


@pytest.mark.django_db
def test_a_migracao_0086_traduz_os_seis_pares_e_a_reversa_e_simetrica() -> None:
    """A terceira migração de VALOR, e a primeira com **dois** enums na mesma tabela.

    O mapa da `0086` é campo → pares, um nível a mais que o da `0084`/`0085`, e é isso que este
    teste percorre: sem a chave do campo, a reversa teria de saber de cabeça qual lista pertence a
    qual coluna. `.update()` no queryset contorna `full_clean()` — é assim que se põe um valor
    pt-BR na coluna sem passar pela validação que esta própria migração torna obsoleta.
    """
    from django.apps import apps as registro_de_apps

    modulo = _migracao_0086()
    mapa = modulo._PARES_PT_PARA_EN
    assert set(mapa) == {"nivel", "fonte"}
    assert sum(len(pares) for pares in mapa.values()) == 6

    registros: dict[tuple[str, str], SatisfactionRecord] = {}
    for campo, pares in mapa.items():
        for antigo, _novo in pares:
            registro = _satisfacao(note="Registro do par.")
            SatisfactionRecord.objects.filter(pk=registro.pk).update(**{campo: antigo})
            registros[(campo, antigo)] = registro

    modulo.traduzir_para_ingles(registro_de_apps, None)
    for campo, pares in mapa.items():
        for antigo, novo in pares:
            registros[(campo, antigo)].refresh_from_db()
            assert getattr(registros[(campo, antigo)], campo) == novo

    modulo.traduzir_para_portugues(registro_de_apps, None)
    for campo, pares in mapa.items():
        for antigo, _novo in pares:
            registros[(campo, antigo)].refresh_from_db()
            assert getattr(registros[(campo, antigo)], campo) == antigo


@pytest.mark.django_db
def test_nenhum_registro_tem_valor_pt_e_os_choices_sao_os_novos() -> None:
    """A prova de estado, complementar à de função: os dois enums só conhecem os choices novos."""
    _satisfacao()

    valores_portugueses = {
        "promotor", "satisfeito", "neutro", "insatisfeito", "declarada", "percebida",
    }
    persistidos = set(SatisfactionRecord.objects.values_list("nivel", flat=True)) | set(
        SatisfactionRecord.objects.values_list("fonte", flat=True)
    )

    assert not (persistidos & valores_portugueses)
    assert tuple(SatisfactionRecord.Nivel.values) == (
        "promoter", "satisfied", "neutral", "dissatisfied",
    )
    assert tuple(SatisfactionRecord.Fonte.values) == ("declared", "perceived")


@pytest.mark.django_db
def test_a_tabela_renomeou_e_a_linha_sobreviveu_com_a_mesma_pk() -> None:
    """O que a `aliases.md` §2b exige de todo renome: só o rótulo muda.

    A tabela é `core_satisfactionrecord` — o `RenameModel` renomeou em lugar, como a `0069` fez
    com as quatro da Fase 6 — e a pk continua sendo a da linha, não uma nova. Sem esta asserção o
    renome passaria igual se alguém tivesse feito modelo novo mais migração de dados, que é
    exatamente o caminho que a §2b proíbe.
    """
    registro = _satisfacao()

    assert SatisfactionRecord._meta.db_table == "core_satisfactionrecord"
    assert SatisfactionRecord.objects.get(pk=registro.pk).pk == registro.pk


@pytest.mark.django_db
def test_o_valor_legado_no_corpo_da_v1_normaliza_nos_dois_campos(admin_client: APIClient) -> None:
    """Quem escrevia `"neutro"`/`"declarada"` ontem continua funcionando — e persiste o canônico."""
    conta = AccountFactory()

    resposta = admin_client.post(
        "/api/v1/satisfacoes/",
        {
            "account": conta.pk,
            "nivel": "neutro",
            "fonte": "declarada",
            "happened_on": str(timezone.localdate()),
        },
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["nivel"] == "neutral"
    assert resposta.data["fonte"] == "declared"
    # O rótulo é superfície e não atravessou: continua pt-BR nas duas versões.
    assert resposta.data["nivel_display"] == "Neutro"
    assert resposta.data["fonte_display"] == "Declarada pelo cliente"
    registro = SatisfactionRecord.objects.get()
    assert (registro.nivel, registro.fonte) == ("neutral", "declared")


@pytest.mark.django_db
@pytest.mark.parametrize(("campo", "legado"), [("nivel", "neutro"), ("fonte", "declarada")])
def test_o_valor_legado_no_corpo_da_v2_e_400_de_choices_na_satisfacao(
    admin_client: APIClient, campo: str, legado: str
) -> None:
    """A v2 não traduz nem recusa com frase própria: quem fala é o `choices` do campo, de graça."""
    corpo: dict[str, Any] = {
        "account": AccountFactory().pk,
        "nivel": "neutral",
        "fonte": "declared",
        "happened_on": str(timezone.localdate()),
    }
    corpo[campo] = legado

    resposta = admin_client.post("/api/v2/satisfaction-records/", corpo, format="json")

    assert resposta.status_code == 400
    assert legado in str(resposta.data[campo])
    assert not SatisfactionRecord.objects.exists()


@pytest.mark.django_db
def test_o_valor_canonico_no_corpo_da_v2_cria_a_satisfacao(admin_client: APIClient) -> None:
    resposta = admin_client.post(
        "/api/v2/satisfaction-records/",
        {
            "account": AccountFactory().pk,
            "nivel": "promoter",
            "fonte": "perceived",
            "happened_on": str(timezone.localdate()),
        },
        format="json",
    )

    assert resposta.status_code == 201
    registro = SatisfactionRecord.objects.get()
    assert (registro.nivel, registro.fonte) == ("promoter", "perceived")


@pytest.mark.django_db
def test_o_filtro_aceita_o_valor_legado_e_o_canonico_na_v1_nos_dois_campos(admin_client: APIClient) -> None:
    conta = AccountFactory()
    neutro = _satisfacao(account=conta)
    _satisfacao(
        account=conta,
        nivel=SatisfactionRecord.Nivel.PROMOTER,
        fonte=SatisfactionRecord.Fonte.PERCEIVED,
    )

    pelo_legado = admin_client.get("/api/v1/satisfacoes/?nivel=neutro&fonte=declarada")
    pelo_canonico = admin_client.get("/api/v1/satisfacoes/?nivel=neutral&fonte=declared")

    assert [r["id"] for r in pelo_legado.json()] == [neutro.pk]
    assert [r["id"] for r in pelo_canonico.json()] == [neutro.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parametro", "canonico"), [("nivel=neutro", "neutral"), ("fonte=declarada", "declared")]
)
def test_o_filtro_com_valor_legado_na_v2_e_400_por_campo_da_satisfacao(
    admin_client: APIClient, parametro: str, canonico: str
) -> None:
    """Lista vazia seria o silêncio que a #122 recusa — a v2 recusa o valor, e diz qual usar."""
    _satisfacao()

    resposta = admin_client.get(f"/api/v2/satisfaction-records/?{parametro}")

    assert resposta.status_code == 400
    assert f"use '{canonico}'" in str(resposta.data)


@pytest.mark.django_db
def test_o_filtro_com_valor_canonico_continua_funcionando_na_v2_na_satisfacao(admin_client: APIClient) -> None:
    conta = AccountFactory()
    neutro = _satisfacao(account=conta)
    _satisfacao(account=conta, nivel=SatisfactionRecord.Nivel.PROMOTER)

    resposta = admin_client.get("/api/v2/satisfaction-records/?nivel=neutral")

    assert [r["id"] for r in resposta.json()] == [neutro.pk]


# ---------------------------------------------------------------------------------------------
# 11. A última família — DunningContact (issue #122, fatia 5.4)
#
# Ela junta tudo o que as três anteriores fizeram em separado: classe e **tabela** (como a 5.3),
# **campo** (como a 5.2) e **valor** (como as três). E traz duas superfícies que nenhuma delas
# tinha, porque o degrau não é campo de serializer gravável:
#
# * o valor chega no **corpo de uma `@action`** (`rascunhar`/`enviar`), onde o mixin de serializer
#   não passa e **não existe** validação de `choices` do DRF para recusar de graça na v2 — quem
#   valida é a própria action, contra as réguas de `cobranca.py`. Sem tradução, `pre_aviso` na v2
#   viraria "Degrau desconhecido", um erro que aponta para o lugar errado;
# * o **nome do parâmetro** de filtro mudou junto com o campo (`?degrau=` → `?dunning_step=`), o
#   que exigiu `filter_field_aliases` também no laço de `filter_exact_fields` — sem ele o filtro
#   legado deixaria de filtrar em silêncio na v1, devolvendo a lista inteira.
#
# A **rota** `/cobranca/` não ganha par canônico: ela nomeia a família de cobrança, que continua
# sem coinagem (`CobrancaSuspensao`, `cobranca.py`), e não a classe que acabou de ganhar a dela.
# ---------------------------------------------------------------------------------------------


def _migracao_0087() -> Any:
    """O módulo da migração, importado por caminho — `0087...` não é identificador Python."""
    return importlib.import_module("apps.core.migrations.0087_o_contato_de_cobranca_fala_ingles")


def _fatura_cobravel() -> Invoice:
    """Emitida e vencida há 12 dias: o degrau `firm` é o que cabe, e há a quem cobrar."""
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED,
        number=f"2026-{Invoice.objects.count() + 1:04d}",
        due_date=timezone.localdate() - timedelta(days=12),
    )
    Contact.objects.create(
        account=fatura.account, first_name="Financeiro",
        email="financeiro@cliente.test", receives_billing=True,
    )
    return fatura


def _contato(**kwargs: Any) -> DunningContact:
    fatura = kwargs.pop("invoice", None) or InvoiceFactory()
    campos: dict[str, Any] = {
        "invoice": fatura,
        "account": fatura.account,
        "dunning_step": DunningContact.DunningStep.REMINDER,
        "canal": DunningContact.Canal.EMAIL,
        "sent_on": timezone.localdate(),
    }
    campos.update(kwargs)
    return DunningContact.objects.create(**campos)


@pytest.mark.django_db
def test_a_migracao_0087_traduz_os_cinco_pares_do_degrau_e_a_reversa_e_simetrica() -> None:
    """A quarta e última migração de VALOR, no molde da `0084`/`0085`/`0086`.

    `.update()` no queryset, como o forward faz, contorna `full_clean()` — é assim que se põe um
    valor pt-BR na coluna sem passar pela validação que esta própria migração torna obsoleta.
    """
    from django.apps import apps as registro_de_apps

    modulo = _migracao_0087()
    pares = modulo._PARES_PT_PARA_EN
    assert len(pares) == 5

    contatos = {antigo: _contato() for antigo, _novo in pares}
    for antigo, contato in contatos.items():
        DunningContact.objects.filter(pk=contato.pk).update(dunning_step=antigo)

    modulo.traduzir_para_ingles(registro_de_apps, None)
    for antigo, novo in pares:
        contatos[antigo].refresh_from_db()
        assert contatos[antigo].dunning_step == novo

    modulo.traduzir_para_portugues(registro_de_apps, None)
    for antigo, _novo in pares:
        contatos[antigo].refresh_from_db()
        assert contatos[antigo].dunning_step == antigo


@pytest.mark.django_db
def test_nenhum_contato_tem_degrau_pt_e_os_choices_sao_os_novos() -> None:
    """A prova de estado, complementar à de função: o enum atual só conhece os choices novos."""
    _contato()

    valores_portugueses = {"pre_aviso", "lembrete", "firme", "escalada", "renegociacao"}
    persistidos = set(DunningContact.objects.values_list("dunning_step", flat=True))

    assert not (persistidos & valores_portugueses)
    assert tuple(DunningContact.DunningStep.values) == (
        "pre_notice", "reminder", "firm", "escalation", "renegotiation",
    )


@pytest.mark.django_db
def test_a_tabela_do_contato_renomeou_e_a_linha_sobreviveu_com_a_mesma_pk() -> None:
    """O que a `aliases.md` §2b exige de todo renome: só o rótulo muda.

    Sem esta asserção o renome passaria igual se alguém tivesse feito modelo novo mais migração de
    dados, que é exatamente o caminho que a §2b proíbe.
    """
    contato = _contato()

    assert DunningContact._meta.db_table == "core_dunningcontact"
    assert DunningContact.objects.get(pk=contato.pk).pk == contato.pk


@pytest.mark.django_db
def test_a_leitura_do_contato_na_v1_emite_os_dois_pares_e_a_v2_so_o_canonico(
    admin_client: APIClient,
) -> None:
    """`GET /cobranca/` — `dunning_step` e `degrau` na v1, só o canônico na v2."""
    _contato(dunning_step=DunningContact.DunningStep.FIRM)

    (da_v1,) = admin_client.get("/api/v1/cobranca/").json()
    (da_v2,) = admin_client.get("/api/v2/cobranca/").json()

    assert da_v1["dunning_step"] == da_v1["degrau"] == "firm"
    assert da_v1["dunning_step_display"] == da_v1["degrau_display"] == "Cobrança firme"

    assert da_v2["dunning_step"] == "firm"
    assert da_v2["dunning_step_display"] == "Cobrança firme"
    assert "degrau" not in da_v2
    assert "degrau_display" not in da_v2


@pytest.mark.django_db
def test_a_rota_de_cobranca_responde_igual_nas_duas_versoes(admin_client: APIClient) -> None:
    """A classe ganhou nome canônico e a **rota** não muda — ela nomeia a família, não a classe.

    É a diferença para a fatia 5.3, em que `/satisfacoes/` ganhou o par `/satisfaction-records/`:
    lá o prefixo **era** o nome da classe em português. Aqui `/cobranca/` continua sendo o nome de
    uma família que segue sem coinagem (`CobrancaSuspensao`, `cobranca.py`), e inventar
    `/dunning-contacts/` na v2 batizaria em inglês o que ainda não foi decidido.
    """
    assert admin_client.get("/api/v1/cobranca/").status_code == 200
    assert admin_client.get("/api/v2/cobranca/").status_code == 200
    assert admin_client.get("/api/v2/dunning-contacts/").status_code == 404


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
@pytest.mark.django_db
def test_o_degrau_legado_no_corpo_de_rascunhar_normaliza_na_v1(
    admin_client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quem mandava `"firme"` ontem continua funcionando — e o que volta é o canônico."""
    fatura = _fatura_cobravel()
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: ("Olá...", {"prompt_tokens": 1}))

    resposta = admin_client.post(
        f"/api/v1/invoices/{fatura.pk}/cobranca/rascunhar/", {"degrau": "firme"}, format="json"
    )

    assert resposta.status_code == 200
    assert resposta.json()["degrau"] == "firm"


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
@pytest.mark.django_db
def test_o_degrau_legado_no_corpo_de_rascunhar_na_v2_e_400_dizendo_o_canonico(
    admin_client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E **não** "Degrau desconhecido": o degrau existe, o nome dele é que mudou."""
    fatura = _fatura_cobravel()
    complete = Mock()
    monkeypatch.setattr(ai, "complete", complete)

    resposta = admin_client.post(
        f"/api/v2/invoices/{fatura.pk}/cobranca/rascunhar/", {"degrau": "firme"}, format="json"
    )

    assert resposta.status_code == 400
    assert frase_do_valor_removido("degrau", "firme", "firm") in str(resposta.data)
    complete.assert_not_called()


@override_settings(DUNNING_ENABLED=True)
@pytest.mark.django_db
def test_o_degrau_legado_no_corpo_de_enviar_normaliza_na_v1_e_grava_o_canonico(
    admin_client: APIClient,
) -> None:
    fatura = _fatura_cobravel()

    resposta = admin_client.post(
        f"/api/v1/invoices/{fatura.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "Texto revisado por gente."},
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["dunning_step"] == "firm"
    assert DunningContact.objects.get().dunning_step == "firm"


@override_settings(DUNNING_ENABLED=True)
@pytest.mark.django_db
def test_o_degrau_legado_no_corpo_de_enviar_na_v2_e_400_e_nada_sai(
    admin_client: APIClient,
) -> None:
    """A recusa vem **antes** do envio: nenhum e-mail sai e nenhum contato é gravado."""
    fatura = _fatura_cobravel()

    resposta = admin_client.post(
        f"/api/v2/invoices/{fatura.pk}/cobranca/enviar/",
        {"degrau": "firme", "body": "Texto revisado por gente."},
        format="json",
    )

    assert resposta.status_code == 400
    assert frase_do_valor_removido("degrau", "firme", "firm") in str(resposta.data)
    assert not DunningContact.objects.exists()
    assert mail.outbox == []


@override_settings(DUNNING_ENABLED=True)
@pytest.mark.django_db
def test_o_degrau_canonico_no_corpo_de_enviar_funciona_na_v2(admin_client: APIClient) -> None:
    fatura = _fatura_cobravel()

    resposta = admin_client.post(
        f"/api/v2/invoices/{fatura.pk}/cobranca/enviar/",
        {"degrau": "firm", "body": "Texto revisado por gente."},
        format="json",
    )

    assert resposta.status_code == 201
    assert DunningContact.objects.get().dunning_step == "firm"


@pytest.mark.django_db
def test_o_filtro_do_degrau_aceita_os_dois_nomes_e_os_dois_valores_na_v1(
    admin_client: APIClient,
) -> None:
    """Duas metades num teste só, porque foi um renome só: o **nome** do parâmetro e o **valor**.

    `?degrau=lembrete` é a chamada de quem integrou com a v1 antes desta fatia, e as duas pontas
    dela mudaram de nome no mesmo dia.
    """
    reminder = _contato()
    _contato(dunning_step=DunningContact.DunningStep.FIRM)

    pelo_legado = admin_client.get("/api/v1/cobranca/?degrau=lembrete")
    pelo_canonico = admin_client.get("/api/v1/cobranca/?dunning_step=reminder")
    misto = admin_client.get("/api/v1/cobranca/?dunning_step=lembrete")

    assert [c["id"] for c in pelo_legado.json()] == [reminder.pk]
    assert [c["id"] for c in pelo_canonico.json()] == [reminder.pk]
    assert [c["id"] for c in misto.json()] == [reminder.pk]


@pytest.mark.django_db
def test_o_parametro_legado_do_degrau_na_v2_e_400_dizendo_o_canonico(
    admin_client: APIClient,
) -> None:
    """Sem esta recusa, `?degrau=` seria **ignorado em silêncio** — o filtro sumiria sem aviso."""
    _contato()

    resposta = admin_client.get("/api/v2/cobranca/?degrau=reminder")

    assert resposta.status_code == 400
    assert frase_do_parametro_removido("degrau", "dunning_step") in str(resposta.data)


@pytest.mark.django_db
def test_o_valor_legado_do_degrau_no_filtro_da_v2_e_400_dizendo_o_canonico(
    admin_client: APIClient,
) -> None:
    """Lista vazia seria o silêncio que a #122 recusa — a v2 recusa o valor, e diz qual usar."""
    _contato()

    resposta = admin_client.get("/api/v2/cobranca/?dunning_step=lembrete")

    assert resposta.status_code == 400
    assert frase_do_valor_removido("dunning_step", "lembrete", "reminder") in str(resposta.data)


@pytest.mark.django_db
def test_o_filtro_com_valor_canonico_do_degrau_funciona_na_v2(admin_client: APIClient) -> None:
    reminder = _contato()
    _contato(dunning_step=DunningContact.DunningStep.FIRM)

    resposta = admin_client.get("/api/v2/cobranca/?dunning_step=reminder")

    assert [c["id"] for c in resposta.json()] == [reminder.pk]
