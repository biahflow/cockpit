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

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.core import journey
from apps.core import serializers as modulo_de_serializers
from apps.core.models import (
    Case,
    CobrancaContato,
    CobrancaSuspensao,
    Contact,
    Document,
    PhaseEvent,
    ProjectPhase,
    Satisfacao,
    User,
)
from apps.core.openapi_aliases import ALIASES_DEPRECIADOS, excluir_a_v2_do_contrato
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
    InvoiceFactory,
    LeadFactory,
    ProcessFactory,
    ProcessStepFactory,
    ProjectFactory,
    UserFactory,
    digital_employee_medido,
)
from apps.core.versioning import V1, V2, VersaoPeloCaminho, versao_de


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
    "CobrancaContato": lambda: CobrancaContato.objects.create(
        invoice=(fatura := InvoiceFactory()),
        account=fatura.account,
        degrau=CobrancaContato.Degrau.LEMBRETE,
        canal=CobrancaContato.Canal.INTERNO,
        sent_on=timezone.localdate(),
    ),
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
    "Satisfacao": lambda: Satisfacao.objects.create(
        account=AccountFactory(),
        nivel=Satisfacao.Nivel.PROMOTOR,
        fonte=Satisfacao.Fonte.DECLARADA,
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
)


@pytest.mark.django_db
@pytest.mark.parametrize(("legada", "canonica"), PARES_DE_ROTA)
def test_a_rota_legada_e_da_v1_e_a_canonica_e_da_v2(
    admin_client: APIClient, legada: str, canonica: str
) -> None:
    """Os quatro pares que a `docs/ontology/aliases.md` marcou para morrer na v2."""
    assert admin_client.get(f"/api/v1/{legada}/").status_code == 200
    assert admin_client.get(f"/api/v2/{canonica}/").status_code == 200
    assert admin_client.get(f"/api/v2/{legada}/").status_code == 404
    assert admin_client.get(f"/api/v1/{canonica}/").status_code == 404


@pytest.mark.django_db
def test_a_rota_que_nao_muda_responde_nas_duas_versoes(admin_client: APIClient) -> None:
    """Só quatro prefixos mudam; os outros 53 são a mesma rota sob os dois prefixos de versão."""
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
