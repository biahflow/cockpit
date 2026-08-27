# ADR 0041 — Pulse Design System e validação visual

**Status:** aceita
**Data:** 2026-08-24

## Contexto

Pulse é o produto operacional interno da Biahflow. A identidade visual anteriormente discutida sob o nome provisório Nexus não foi implementada e não deve ser carregada como legado para o produto.

Pulse e One possuem responsabilidades e públicos diferentes. Pulse é uma superfície operacional/command center; One é a experiência oficial client-facing. Compartilhar princípios não implica compartilhar a mesma linguagem visual ou densidade de interface.

O EngineeringOS também exige que mudanças de interface tenham decisão visual explícita antes da implementação e evidência do comportamento realmente renderizado depois da implementação.

## Decisão

### Identidade

- O Design System interno nasce diretamente como **Pulse Design System**.
- `Nexus` não é nome de produto, namespace, token, componente ou identidade a ser implementada.
- Pulse deve possuir linguagem visual própria coerente com uma ferramenta operacional/command center.
- One permanece um produto visualmente distinto e orientado ao cliente.

### Foundations

O primeiro incremento do Pulse Design System deve estabelecer, no mínimo:

- color primitives e semantic color tokens;
- typography roles;
- spacing scale;
- radius e elevation/shadow policy;
- focus, hover, active, disabled, success, warning, danger e information states;
- surface/background/border hierarchy;
- accessibility/contrast expectations;
- theme contract e estratégia de consumo dos tokens;
- documentação mínima para evitar valores visuais ad hoc.

Valores concretos de cor, tipografia e estilo não são definidos por esta ADR. Eles devem ser propostos em um Design Approval Package e aprovados por humano antes da implementação.

### EngineeringOS classification

A criação/evolução material do Pulse Design System é:

```text
INTERFACE_CHANGE
BROWSER_REQUIRED
```

Portanto:

1. o Design Approval Package deve existir e ser aprovado antes do Builder implementar a superfície;
2. a implementação deve ser validada no browser/runtime real;
3. evidência renderizada deve fazer parte do Review Evidence Package;
4. ausência dessa evidência impede `REVIEW_PASS`;
5. o harness pode criar commit, push e PR depois das validações/review;
6. merge permanece um Human Gate.

## Separação entre design e implementação

O artefato de aprovação visual é evidência da decisão, não o código de produção. O Builder deve implementar os tokens/components a partir da revisão aprovada e preservar acessibilidade, testes e comportamento do produto.

## FinOps

Browser/E2E validation, screenshot capture e comparação determinística de estados não devem consumir LLM. Modelos podem ser usados para raciocínio/proposta de design quando necessário, mas operações determinísticas permanecem em tooling comum.

## Consequências

- não haverá etapa de rename Nexus → Pulse porque Nexus não foi implementado;
- novas superfícies do Pulse devem consumir o Design System em vez de criar valores locais sem justificativa;
- futuras Issues visuais devem declarar sua classificação e requisitos de browser evidence;
- Pulse e One podem evoluir independentemente sem duplicar ownership visual.
