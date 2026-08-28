"""A escada perde um degrau, e o Discovery Sprint ganha preço de tabela (ADR 0053).

`discovery_assessment` era a porta gratuita do founding client. Com o Design Partner cobrindo a
entrada em vertical nova, não sobrou trabalho para ele fazer — e um degrau que ninguém vende é
coluna de funil que nunca enche, o mesmo argumento com que a ADR 0048 recusou o PRIORITIZE.

## A remoção é guardada, e a mensagem é o produto principal dela

Remover valor de enum é mudança de contrato em `/api/v1/`. Uma migração que apagasse a linha em
silêncio deixaria `CommercialOpportunity`/`Project` órfãos por `SET_NULL` — venda registrada num
degrau que passa a não existir, e sem nada vermelho em lugar nenhum. Então ela **falha alto**, em
dois casos:

- **vínculo** — qualquer linha apontando para o degrau. Vínculo é história e não se apaga por
  migração; quem o tem reaponta na tela e roda de novo;
- **edição de gente** — o `Service` existe mas nome, preço ou resumo já não são os que a `0050`
  semeou, ou ele foi arquivado. Migração que sobrescreve decisão de gente é migração em que
  ninguém confia, e é o mesmo cuidado que a `0020` e a `0050` já tomam com `get_or_create` e com
  a comparação por nome semeado.

Linha semeada, intocada e sem vínculo: `delete()`. É o caso de todo banco migrado do zero, onde a
`0020` cria o registro em **todo** `migrate` e ninguém nunca o usou.

O critério de vínculo cobre **quatro** FKs, e não as duas que a ADR nomeia: `Invoice.service` e
`DigitalEmployeeBlueprint.service` também são `SET_NULL`, e uma fatura que perde o degrau em
silêncio é dinheiro sem origem. Guarda que aborta a mais é conservadora na direção certa.

## O preço não é sobrescrito quando alguém já o decidiu

O Discovery Sprint passa a custar R$ 3.000 (a ADR mata a faixa 2.500–3.500, o cheio de 5.000 e a
condição piloto). Mas ele está em 0 por acidente de história — a `0020` semeou `discovery_express`
em zero e a `0050` renomeou a chave sem tocar no preço —, e editar preço **é** o caminho normal na
tela Serviços. Então aqui a divergência não aborta: se a linha já não é a semeada, a migração
passa adiante sem escrever. Deletar linha e reescrever número não têm o mesmo peso.

## O reverse recria a chave

`AlterField` de volta com as sete e `get_or_create` da linha semeada com os valores da `0050`; o
preço volta a zero só se ainda estiver nos 3.000 desta migração. Os valores semeados são **copiados
literalmente** da `0050` em vez de importados dela: história congelada não vira dependência de
código.
"""

from django.db import migrations, models

CHAVE = "discovery_assessment"

# Copiado literalmente de `0050_escada_fde_completa.RERROTULACOES` (nome e resumo) e de
# `0020_seed_service_tiers.DEFAULT_TIERS` (preço). Se algum destes três não bater, foi gente que
# editou, e a migração não passa por cima.
NOME_SEMEADO = "Discovery Express + Assessment"
RESUMO_SEMEADO = (
    "Discovery estruturado do processo mais assessment de maturidade em IA, fechando com o "
    "próximo passo recomendado. Gratuito no programa de founding client; pago para os demais."
)
PRECO_SEMEADO = 0

# O degrau que fica, e o preço que a ADR 0053 fixa.
SPRINT = "discovery_sprint"
NOME_SPRINT = "Discovery Sprint"
RESUMO_SPRINT = (
    "Discovery pago de 5–7 dias: walkthrough do processo com P-S-D-T-E-R, achados rotulados "
    "(fato / hipótese / desconhecido), custo do estado atual apurado e Executive Readout com o "
    "ranking por Opportunity Score."
)
PRECO_DE_TABELA = 3000

DEGRAUS_ANTES = [
    ("qualification_call", "Qualification Call"),
    ("discovery_assessment", "Discovery Express + Assessment"),
    ("discovery_sprint", "Discovery Sprint"),
    ("feasibility", "Technical Feasibility (T.O.E.)"),
    ("prove", "PROVE (piloto)"),
    ("scale", "Scale"),
    ("transformation", "Transformation Partnership"),
]
DEGRAUS_DEPOIS = [par for par in DEGRAUS_ANTES if par[0] != CHAVE]

# (modelo, rótulo para a mensagem) — todo FK que aponta para `Service` e some em silêncio.
VINCULOS = [
    ("CommercialOpportunity", "oportunidade(s) comercial(is)"),
    ("Project", "projeto(s)"),
    ("Invoice", "fatura(s)"),
    ("DigitalEmployeeBlueprint", "blueprint(s) de funcionário digital"),
]

# As sete saídas do decision gate (`ProjectPhase.DECISOES_DO_GATE`). Nenhum dado a converter: as
# quatro antigas continuam válidas e as três do PROVE são aditivas — é `choices`, e `choices` não
# toca no banco. Sem esta operação, `makemigrations --check` fica vermelho para sempre.
DECISOES_DO_GATE = [
    ("go", "GO"),
    ("conditional_go", "CONDITIONAL GO"),
    ("redesign", "REDESIGN"),
    ("no_go", "NO-GO"),
    ("scale", "SCALE"),
    ("iterate", "ITERATE"),
    ("stop", "STOP"),
]


def _vinculos(apps) -> list[str]:
    achados = []
    for nome, rotulo in VINCULOS:
        total = apps.get_model("core", nome).objects.filter(service__tier=CHAVE).count()
        if total:
            achados.append(f"{total} {rotulo}")
    return achados


def remover_o_degrau(apps, schema_editor):
    Service = apps.get_model("core", "Service")

    presos = _vinculos(apps)
    if presos:
        raise RuntimeError(
            f"A ADR 0053 remove o degrau `{CHAVE}`, mas ele ainda tem vínculo: "
            f"{', '.join(presos)}. Vínculo é história e não se apaga por migração: reaponte essas "
            "linhas para outro degrau (tela Serviços / admin) e rode `migrate` de novo."
        )

    for service in Service.objects.filter(tier=CHAVE):
        divergiu = []
        if service.name != NOME_SEMEADO:
            divergiu.append(f"nome {service.name!r} (semeado: {NOME_SEMEADO!r})")
        if service.list_price != PRECO_SEMEADO:
            divergiu.append(f"preço {service.list_price} (semeado: {PRECO_SEMEADO})")
        if service.summary != RESUMO_SEMEADO:
            divergiu.append("resumo editado")
        if service.archived_at is not None:
            divergiu.append("registro arquivado")
        if divergiu:
            raise RuntimeError(
                f"O serviço #{service.pk} no degrau `{CHAVE}` foi editado por gente e esta "
                f"migração não passa por cima: {', '.join(divergiu)}. Decida o que fazer com ele "
                "(mover para serviço avulso, ou apagar na tela) e rode `migrate` de novo."
            )
        service.delete()


def recriar_o_degrau(apps, schema_editor):
    """Reverse: a chave volta e a linha semeada é recriada como a `0050` a deixou."""
    Service = apps.get_model("core", "Service")
    Service.objects.get_or_create(
        tier=CHAVE,
        archived_at=None,
        defaults={
            "name": NOME_SEMEADO,
            "list_price": PRECO_SEMEADO,
            "summary": RESUMO_SEMEADO,
            "active": True,
        },
    )


def precificar_o_sprint(apps, schema_editor):
    """R$ 3.000 de tabela — só sobre a linha ainda semeada."""
    Service = apps.get_model("core", "Service")
    Service.objects.filter(
        tier=SPRINT,
        archived_at=None,
        name=NOME_SPRINT,
        summary=RESUMO_SPRINT,
        list_price=0,
    ).update(list_price=PRECO_DE_TABELA)


def despreciar_o_sprint(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    Service.objects.filter(
        tier=SPRINT,
        archived_at=None,
        name=NOME_SPRINT,
        summary=RESUMO_SPRINT,
        list_price=PRECO_DE_TABELA,
    ).update(list_price=PRECO_SEMEADO)


class Migration(migrations.Migration):

    dependencies = [("core", "0063_process_process_step")]

    operations = [
        migrations.RunPython(remover_o_degrau, recriar_o_degrau),
        migrations.RunPython(precificar_o_sprint, despreciar_o_sprint),
        migrations.AlterField(
            model_name="service",
            name="tier",
            field=models.CharField(
                blank=True, choices=DEGRAUS_DEPOIS, default="", max_length=32
            ),
        ),
        migrations.AlterField(
            model_name="projectphase",
            name="gate_decision",
            field=models.CharField(
                blank=True, choices=DECISOES_DO_GATE, default="", max_length=16
            ),
        ),
    ]
