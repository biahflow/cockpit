"""Enriquecimento de lead por cadastro público de CNPJ (FDD 030)."""

from __future__ import annotations

import urllib.error

import pytest
from django.test import override_settings

from apps.core import enrichment
from apps.core.models import Lead, Vertical

LIGADO = override_settings(ENRICHMENT_ENABLED=True, ENRICHMENT_PROVIDER="brasilapi")

# O corpo da BrasilAPI, reduzido aos campos que o adaptador lê. Fixture e não chamada real: o
# `fetch` é I/O e fica fora da cobertura, mas o `parse` é puro e é onde mora o contrato.
CORPO = {
    "razao_social": "ACME INDUSTRIA E COMERCIO LTDA",
    "nome_fantasia": "ACME",
    "cnae_fiscal": 6201501,
    "cnae_fiscal_descricao": "Desenvolvimento de programas de computador sob encomenda",
    "porte": "DEMAIS",
    "capital_social": "500000.00",
    "descricao_situacao_cadastral": "ATIVA",
    "municipio": "SAO PAULO",
    "uf": "SP",
    "data_inicio_atividade": "2015-03-10",
}


class ProviderFalso:
    def __init__(self, company: enrichment.Company | None = None, erro: Exception | None = None):
        self.company, self.erro = company, erro
        self.chamadas: list[str] = []

    def fetch(self, cnpj: str) -> enrichment.Company | None:
        self.chamadas.append(cnpj)
        if self.erro is not None:
            raise self.erro
        return self.company


@pytest.fixture
def company() -> enrichment.Company:
    return enrichment.BrasilApiProvider.parse("11222333000181", CORPO)


# --- normalização -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cru,esperado",
    [
        ("11.222.333/0001-81", "11222333000181"),
        ("11222333000181", "11222333000181"),
        ("  11 222 333 0001 81 ", "11222333000181"),
        ("123", ""),
        ("", ""),
        ("não é cnpj", ""),
    ],
)
def test_normalize_cnpj_aceita_pontuado_e_recusa_o_que_nao_tem_catorze_digitos(cru, esperado):
    assert enrichment.normalize_cnpj(cru) == esperado


def test_normalize_cnpj_nao_confere_digito_verificador():
    """Recusar por dígito verificador trocaria um lead por um cadastro limpo.

    Um CNPJ digitado com um erro de digitação tem de chegar ao fornecedor e voltar como "não
    encontrei" — o formulário público não é lugar de reprovar quem quer falar com a casa.
    """
    assert enrichment.normalize_cnpj("11111111111111") == "11111111111111"


# --- tradução do corpo do fornecedor -------------------------------------------------------


def test_parse_traduz_o_corpo_da_brasilapi(company: enrichment.Company):
    assert company.legal_name == "ACME INDUSTRIA E COMERCIO LTDA"
    assert company.trade_name == "ACME"
    assert company.cnae_code == "6201501"
    assert company.size == "DEMAIS"
    assert company.city == "SAO PAULO" and company.state == "SP"


def test_parse_tolera_campo_ausente_e_nulo():
    """Cadastro incompleto é normal — MEI sem nome fantasia, empresa sem capital declarado."""
    vazio = enrichment.BrasilApiProvider.parse("11222333000181", {"razao_social": None})
    assert vazio.legal_name == "" and vazio.cnae_code == "" and vazio.trade_name == ""


# --- inferência de vertical ----------------------------------------------------------------


@pytest.mark.parametrize(
    "cnae,slug",
    [
        ("6201501", "tecnologia"),
        ("8610101", "saude"),
        ("8513900", "educacao"),
        ("4711302", "varejo"),
        ("4120400", "construcao"),
        ("6422100", "financeiro"),
        ("6810201", "imobiliario"),
        ("7020400", "servicos-profissionais"),
        ("4930202", "logistica"),
        ("1091101", "industria"),
    ],
)
def test_infer_vertical_slug_mapeia_a_divisao_do_cnae(cnae, slug):
    assert enrichment.infer_vertical_slug(cnae) == slug


def test_infer_vertical_slug_zero_padded_pega_a_agropecuaria():
    """A divisão 01 chega como `1` quando a fonte entrega inteiro — e agro sumiria do mapa."""
    assert enrichment.infer_vertical_slug("115600") == "agro"


@pytest.mark.parametrize("cnae", ["", "12", "não numérico", "9900000"])
def test_infer_vertical_slug_cala_quando_nao_sabe(cnae):
    """O mapa é incompleto de propósito: sem correspondência, nenhuma vertical."""
    assert enrichment.infer_vertical_slug(cnae) == ""


@pytest.mark.django_db
def test_infer_vertical_so_devolve_vertical_que_o_admin_cadastrou():
    """O mapa sugere; quem decide é o banco. A vertical é taxonomia editável (FDD 026)."""
    assert enrichment.infer_vertical("6201501") is None

    tecnologia = Vertical.objects.create(name="Tecnologia", slug="tecnologia")
    assert enrichment.infer_vertical("6201501") == tecnologia


@pytest.mark.django_db
def test_infer_vertical_ignora_vertical_inativa():
    """Inativa some das escolhas novas por decisão de quem administra — sem exceção aqui."""
    Vertical.objects.create(name="Tecnologia", slug="tecnologia", active=False)
    assert enrichment.infer_vertical("6201501") is None


# --- o laço completo ------------------------------------------------------------------------


@pytest.mark.django_db
@LIGADO
def test_enrich_lead_grava_o_cadastro(monkeypatch, company: enrichment.Company):
    provider = ProviderFalso(company)
    monkeypatch.setattr(enrichment, "get_provider", lambda: provider)
    lead = Lead.objects.create(name="Ana", email="a@x.com", cnpj="11.222.333/0001-81")

    assert enrichment.enrich_lead(lead) is True
    lead.refresh_from_db()
    assert lead.enrichment["cnae_label"].startswith("Desenvolvimento")
    # O fornecedor recebe só dígitos, mesmo com o visitante tendo digitado pontuação.
    assert provider.chamadas == ["11222333000181"]


@pytest.mark.django_db
def test_enrich_lead_e_no_op_com_a_flag_desligada(monkeypatch, company: enrichment.Company):
    provider = ProviderFalso(company)
    monkeypatch.setattr(enrichment, "get_provider", lambda: provider)
    lead = Lead.objects.create(name="Ana", email="a@x.com", cnpj="11222333000181")

    with override_settings(ENRICHMENT_ENABLED=False):
        assert enrichment.enrich_lead(lead) is False
    assert lead.enrichment == {} and provider.chamadas == []


@pytest.mark.django_db
@LIGADO
def test_enrich_lead_nao_chama_o_fornecedor_sem_cnpj(monkeypatch, company: enrichment.Company):
    provider = ProviderFalso(company)
    monkeypatch.setattr(enrichment, "get_provider", lambda: provider)
    lead = Lead.objects.create(name="Ana", email="a@x.com")

    assert enrichment.enrich_lead(lead) is False
    assert provider.chamadas == []


@pytest.mark.django_db
@LIGADO
def test_enrich_lead_engole_falha_do_fornecedor(monkeypatch):
    """A regressão crítica da FDD 030, no nível da unidade. O lead sobrevive intacto."""
    monkeypatch.setattr(
        enrichment, "get_provider", lambda: ProviderFalso(erro=urllib.error.URLError("fora do ar"))
    )
    lead = Lead.objects.create(name="Ana", email="a@x.com", cnpj="11222333000181")

    assert enrichment.enrich_lead(lead) is False
    lead.refresh_from_db()
    assert lead.enrichment == {}


@pytest.mark.django_db
@LIGADO
def test_enrich_lead_aceita_cnpj_desconhecido_do_fornecedor(monkeypatch):
    """CNPJ que não existe devolve `None`, e isso não é erro — é ausência."""
    monkeypatch.setattr(enrichment, "get_provider", lambda: ProviderFalso(None))
    lead = Lead.objects.create(name="Ana", email="a@x.com", cnpj="11222333000181")

    assert enrichment.enrich_lead(lead) is False
    assert lead.enrichment == {}


# --- fornecedor e contexto ------------------------------------------------------------------


def test_get_provider_cai_no_null_sem_fornecedor_nomeado():
    with override_settings(ENRICHMENT_PROVIDER=""):
        assert isinstance(enrichment.get_provider(), enrichment.NullProvider)
    with override_settings(ENRICHMENT_PROVIDER="brasilapi"):
        assert isinstance(enrichment.get_provider(), enrichment.BrasilApiProvider)


@pytest.mark.django_db
def test_null_provider_nao_enriquece(monkeypatch):
    lead = Lead.objects.create(name="Ana", email="a@x.com", cnpj="11222333000181")
    with override_settings(ENRICHMENT_ENABLED=True, ENRICHMENT_PROVIDER=""):
        assert enrichment.enrich_lead(lead) is False


def test_summary_lines_monta_o_contexto_sem_o_cnpj(company: enrichment.Company):
    from dataclasses import asdict

    linhas = enrichment.summary_lines(asdict(company))
    texto = "\n".join(linhas)
    assert "Setor (CNAE): Desenvolvimento de programas" in texto
    assert "Praça: SAO PAULO/SP" in texto
    # O CNPJ não entra: o modelo não precisa dele para julgar fit, e mandá-lo só aumentaria a
    # superfície de dado pessoal enviada ao fornecedor de IA.
    assert "11222333000181" not in texto


def test_summary_lines_e_vazio_sem_enriquecimento():
    assert enrichment.summary_lines({}) == []


def test_summary_lines_omite_campo_em_branco():
    assert enrichment.summary_lines({"legal_name": "ACME", "size": ""}) == ["Razão social: ACME"]


# --- a vertical que o CNAE preenche na conversão --------------------------------------------


@pytest.mark.django_db
def test_conversao_preenche_a_vertical_do_cliente_pelo_cnae():
    """FDD 030: "o enriquecimento deve preencher a vertical do cliente quando conseguir inferi-la".

    A vertical é o instrumento de nicho da FDD 026 — do blueprint ao case —, e até aqui só era
    preenchida à mão no cadastro do cliente. Preenchê-la na conversão é o que faz o enriquecimento
    render duas vezes: uma no `ai_fit`, outra no setor que a proposta e o case vão usar depois.
    """
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.core.models import PipelineStage, User
    from apps.core.tests.factories import PipelineStageFactory, UserFactory

    tecnologia = Vertical.objects.create(name="Tecnologia", slug="tecnologia")
    if not PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).exists():
        PipelineStageFactory(kind=PipelineStage.Kind.OPEN)
    lead = Lead.objects.create(
        name="Ana", email="a@x.com", company="ACME", enrichment={"cnae_code": "6201501"}
    )

    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))
    assert api.post(reverse("lead-convert", args=[lead.id]), {}, format="json").status_code == 201

    lead.refresh_from_db()
    assert lead.client is not None and lead.client.vertical == tecnologia


@pytest.mark.django_db
def test_conversao_sem_cadastro_deixa_o_cliente_sem_vertical():
    """Sem CNAE não há inferência, e o cliente nasce sem setor — o estado que a FDD 026 já trata."""
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.core.models import PipelineStage, User
    from apps.core.tests.factories import PipelineStageFactory, UserFactory

    Vertical.objects.create(name="Tecnologia", slug="tecnologia")
    if not PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).exists():
        PipelineStageFactory(kind=PipelineStage.Kind.OPEN)
    lead = Lead.objects.create(name="Ana", email="a@x.com", company="ACME")

    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))
    assert api.post(reverse("lead-convert", args=[lead.id]), {}, format="json").status_code == 201

    lead.refresh_from_db()
    assert lead.client is not None and lead.client.vertical is None


# --- flag e sonda ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_flag_nao_exige_credencial():
    """Cadastro público não tem chave — cobrar uma recusaria a instalação que está certa."""
    from apps.core import flags

    with override_settings(ENRICHMENT_ENABLED=True):
        assert flags.configured("enrichment") is True
        assert flags.is_enabled("enrichment") is True
    with override_settings(ENRICHMENT_ENABLED=False):
        assert flags.is_enabled("enrichment") is False


def test_sonda_do_null_provider_diz_que_nao_e_sondavel():
    from apps.core import integrations

    with override_settings(ENRICHMENT_PROVIDER=""):
        ok, detalhe = integrations.PROBES["enrichment"]()
    assert ok is True and "nenhum provedor" in detalhe
