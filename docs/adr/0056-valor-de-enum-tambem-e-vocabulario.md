# ADR 0056 — Valor de enum também é vocabulário

**Status:** aceita
**Data:** 2026-08-30
**Depende de:** ADR 0049 (a ontologia entra pela linguagem) · ADR 0052 (renomes preservam a
`/api/v1/`) · Language Map v1.4, decisão D10 e invariante §6.15
**Implementada por:** issue #94

## Contexto

O Language Map já exigia inglês para classe, campo, rota e chave de payload, mas não dizia se a
regra alcançava o **valor** persistido por um enum. O silêncio deixou três famílias bilíngues:

- `Activity.CobrancaSinal`, com `esqueceu`, `nao_pode` e `insatisfeito`, e os degraus
  `pre_aviso`, `lembrete`, `firme`, `escalada` e `renegociacao`;
- `Satisfacao`, com fontes e níveis em português;
- `DigitalEmployeeBlueprint.Area`, com cinco áreas em português.

Valor de enum não é detalhe invisível de armazenamento. Ele atravessa JSON, query string,
TypeScript, filtros e integrações. Trocar `promotor` por `promoter`, por exemplo, altera tanto o
registro persistido quanto `?nivel=promotor` e o corpo aceito pela API.

## Decisão

Valores de enum são termos de domínio e seguem a mesma regra dos identificadores: **inglês
canônico** em modelo, banco e API; a UI traduz apenas o rótulo exibido.

Os destinos decididos são:

| Família | Legado | Canônico |
| --- | --- | --- |
| sinal de cobrança | `esqueceu` · `nao_pode` · `insatisfeito` | `forgot` · `unable_to_pay` · `dissatisfied` |
| degrau de cobrança | `pre_aviso` · `lembrete` · `firme` · `escalada` · `renegociacao` | `pre_notice` · `reminder` · `firm` · `escalation` · `renegotiation` |
| fonte de satisfação | `declarada` · `percebida` | `declared` · `perceived` |
| nível de satisfação | `promotor` · `satisfeito` · `neutro` · `insatisfeito` | `promoter` · `satisfied` · `neutral` · `dissatisfied` |
| área de blueprint | `comercial` · `financeiro` · `rh` · `juridico` · `atendimento` | `commercial` · `finance` · `hr` · `legal` · `support` |

### A decisão não autoriza uma migração isolada

Cobrança e satisfação migram junto do renome de suas famílias. Cada fatia terá migração de dados
com reversa e normalização de entrada. A área do blueprint migra em fatia própria, agora que o
conceito e os valores canônicos entraram no Language Map.

A `/api/v1/` continua aceitando os valores portugueses como aliases de entrada e preserva o
contrato de resposta até a mudança de versão. Os aliases morrem na `/api/v2/`; removê-los antes é
quebra incompatível. Até a respectiva fatia chegar, os valores legados continuam persistidos e
expostos — a decisão impede **dívida nova**, não reescreve dados fora de um plano de migração.

## Consequências

- Modelo, banco e APIs convergem para um idioma único sem fingir que a v1 nunca existiu.
- Toda migração futura precisa tratar persistência, filtros, escrita, resposta, tipos do frontend
  e integrações como uma unidade.
- A compatibilidade tem prazo explícito: `/api/v2/`, não uma data de calendário.
- O inventário legado fica congelado por teste; acrescentar ocorrência exige falha visível.
- Rótulos de UI continuam em português. Traduzir apresentação não cria um segundo valor de
  domínio.

## Alternativas consideradas

- **Valores fora da regra de idioma.** Evitaria migrações, mas tornaria bilinguismo uma exceção
  permanente exatamente na superfície que sai do repositório como dado.
- **Traduzir tudo nesta issue.** Produziria uma quebra da `/api/v1/` e misturaria três famílias sem
  compartilhar lifecycle nem plano de rollout.
- **Aceitar só o inglês já na v1.** É mais limpo no código e incompatível para clientes que enviam
  filtros e payloads legados.
