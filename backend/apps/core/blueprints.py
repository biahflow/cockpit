"""Resolução e instanciação do catálogo de Funcionários Digitais (FDD 026).

Terceira aplicação do molde que a FDD 011 já provou duas vezes (`JourneyPhase → ProjectPhase`,
`PhaseDeliverable → ProjectDeliverable`): template global editável mais **cópia** por instância.
A cópia é o ponto — editar o catálogo amanhã não pode reescrever o que foi entregue ontem.

Duas diferenças deliberadas em relação à jornada:

- **Sem signal.** A jornada é materializada no `post_save` de `Project` porque é igual para todo
  projeto; o roster de Funcionários Digitais não é. A instanciação é ação explícita da equipe.
- **Uma camada a mais.** Entre o template e a instância existe a `BlueprintVariant`, que
  parametriza o mesmo bloco por vertical. `resolve()` é essa camada, e só ela sabe que branco
  herda.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .models import (
        BlueprintVariant,
        DigitalEmployee,
        DigitalEmployeeBlueprint,
        Project,
        Vertical,
    )


class Resolved(TypedDict):
    """Os valores de um blueprint depois de aplicada a variante da vertical."""

    name: str
    area: str
    area_display: str
    description: str
    kpi_label: str
    # Unidade e direção saem sempre do blueprint: a variante não participa delas (FDD 027). Estão
    # aqui, e não fora do `Resolved`, para que quem instancia tenha o bloco inteiro num lugar só.
    kpi_unit: str
    kpi_direction: str
    hours_saved_month: Decimal
    roi_month: Decimal


def variant_for(
    blueprint: DigitalEmployeeBlueprint, vertical: Vertical | None
) -> BlueprintVariant | None:
    """A variante deste blueprint para esta vertical, se existir. Sem vertical, não existe."""
    if vertical is None:
        return None
    # `.all()` e não `.filter()`: quem lista o catálogo faz `prefetch_related("variants")`, e um
    # `.filter()` aqui furaria o prefetch com uma consulta por blueprint.
    for variant in blueprint.variants.all():
        if variant.vertical_id == vertical.pk:
            return variant
    return None


def resolve(blueprint: DigitalEmployeeBlueprint, vertical: Vertical | None = None) -> Resolved:
    """Aplica a variante da vertical sobre os valores do blueprint.

    Campo em branco (ou decimal nulo) na variante **herda** o do blueprint: a variante diz o que
    muda para aquele setor, não repete o que não muda. Sem vertical — cliente que ainda não tem
    uma —, ou sem variante para ela, o que sai é o próprio blueprint. É o que sustenta a regra de
    que cliente sem vertical continua funcionando.

    A exceção é o par (`kpi_unit`, `kpi_direction`): ele não passa pela variante nem quando ela
    existe. O `kpi_label` é o **texto** do KPI e muda com o setor; a unidade e a direção são o que
    torna o número comparável entre setores, e uma variante que as trocasse quebraria a comparação
    sem dizer nada (FDD 027).
    """
    variant = variant_for(blueprint, vertical)
    return Resolved(
        name=blueprint.name,
        area=blueprint.area,
        area_display=blueprint.get_area_display(),
        description=(variant.description if variant and variant.description else blueprint.description),
        kpi_label=(variant.kpi_label if variant and variant.kpi_label else blueprint.kpi_label),
        kpi_unit=blueprint.kpi_unit,
        kpi_direction=blueprint.kpi_direction,
        hours_saved_month=(
            variant.default_hours_saved_month
            if variant and variant.default_hours_saved_month is not None
            else blueprint.default_hours_saved_month
        ),
        roi_month=(
            variant.default_roi_month
            if variant and variant.default_roi_month is not None
            else blueprint.default_roi_month
        ),
    )


def instantiate(
    project: Project,
    blueprint: DigitalEmployeeBlueprint,
    vertical: Vertical | None = None,
) -> DigitalEmployee:
    """Cria o `DigitalEmployee` do projeto **copiando** os valores resolvidos do catálogo.

    `area` recebe o **rótulo** (`get_area_display`), não o slug: em `DigitalEmployee` o campo é
    texto livre, é o que a tela do projeto mostra e é o que o snapshot leva ao painel do cliente —
    gravar `"rh"` ali faria o cliente ler "rh".

    O `blueprint` fica gravado como procedência. Ele não é lido depois: o que vale é a cópia.

    **`kpi_baseline` saiu daqui** (ADR 0055, decisão C1 do DAP `dap-prove-e-valor-r1`). A FDD 027
    tinha razão sobre o *momento* — o "antes" perguntado na conclusão é memória, não medição —, e o
    que mudou é **onde** ele mora: o baseline é uma `Measurement(kind=baseline)` de um `KPI`, e
    aceitá-lo aqui manteria um segundo lugar escrevendo a mesma medição, que é exatamente o que a
    decisão C1 remove. O ativo instanciado nasce sem KPI e passa a **referenciar** um.
    """
    from .models import DigitalEmployee

    valores = resolve(blueprint, vertical)
    return DigitalEmployee.objects.create(
        project=project,
        blueprint=blueprint,
        name=valores["name"],
        area=valores["area_display"],
        description=valores["description"],
        kpi_label=valores["kpi_label"],
        kpi_unit=valores["kpi_unit"],
        kpi_direction=valores["kpi_direction"],
        hours_saved_month=valores["hours_saved_month"],
        roi_month=valores["roi_month"],
        status=DigitalEmployee.Status.BUILDING,
    )
