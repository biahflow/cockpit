# Design Approval Package — a finalidade do documento no formulário de upload

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-09-02
Produzido por: harness (Claude Code), sob `docs/engineering-os/workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Presença, condição de exibição e rótulos do campo `Finalidade` no formulário de envio de `/documentos` |
| Aprovado por | Daniel Campos, nesta sessão |
| Data | 2026-09-02 |
| Revisão aprovada | r1 |
| Decisões | **A1** (só no vínculo com conta) · **B1** ("Finalidade" / "Documento comum") |
| Explicitamente não aprovado | Editar a finalidade depois do envio; exibir a finalidade na listagem; qualquer valor de `Document.kind` além de `design_partner_agreement` |

> **Nota de processo, registrada por honestidade.** As duas decisões foram tomadas pelo humano em
> conversa **antes** da construção — o gate foi honrado no que importa. Este pacote foi escrito
> **depois** do código, e não antes, como o fluxo pede. Fica registrado como desvio, não como
> precedente.

## Por que existe um gate

`Document.kind` entrou no backend com um valor, `design_partner_agreement`, e é ele que decide se
uma assinatura concluída abre um `Engagement` de parceria sozinha. Sem campo na tela, a marca só
se põe pela API — e o ciclo do Design Partner não anda pela superfície do produto.

Acrescentar um campo a um formulário existente é alterar superfície perceptível por humano. O
formulário de envio de `/documentos` não é coberto por nenhum pacote vigente: o
`dap-lifecycle-status-r1` mediu a listagem de contas, o `dap-perfil-e-contato-r1` o painel de
Contatos, e os de Engagement a seção de mandatos.

## Decisão A — quando o campo aparece

- **A1 — só quando `Vincular a` = Conta.** ✅ aprovada
- **A2 — sempre visível.**

**Motivo da A1.** Um Design Partner Agreement só se ancora numa `Account`: `Document.clean()` e
`DocumentSerializer.validate()` recusam com 400 o mesmo `kind` pendurado em oportunidade ou
projeto. Oferecer a opção nos outros dois vínculos seria mostrar o que a API nega — o oposto exato
da regra que o produto segue em outros pontos (*"o desenho não inventa permissão: ele deixa de
mostrar o que a API recusaria"*, `AccountDetailPage.tsx`). O 400 chegaria sem que nada na tela
explicasse por quê.

**Consequência registrada:** trocar o tipo de vínculo **limpa** a finalidade escolhida. Sem isso,
escolher "Design Partner Agreement", mudar para Projeto e enviar mandaria uma chave que a tela já
não mostra — o mesmo defeito de estado órfão que `changeEngagementCommercialModel` evita no
formulário de mandato.

## Decisão B — o rótulo e o valor vazio

- **B1 — "Finalidade", com "Documento comum" e "Design Partner Agreement".** ✅ aprovada
- **B2 — "Tipo", com "Sem tipo definido".**

**Motivo da B1.** O campo não classifica o arquivo: ele **liga um comportamento** (a assinatura
passa a abrir um mandato). "Finalidade" diz isso; "Tipo" é mais vago. E "Documento comum" nomeia o
padrão em vez de deixar o select descrevendo uma ausência — a maioria dos documentos é isso, e a
opção vazia é a que quase todo mundo vai usar.

"Design Partner Agreement" fica **em inglês**, sem tradução, pelo precedente do `Engagement` (DAP
de Engagement r1, decisão A1): é nome de instrumento, e o campo do modelo que o guarda já se chama
`originating_design_partner_agreement`.

## Estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Formulário | vínculo = Conta, finalidade não escolhida (padrão) | sim |
| Formulário | vínculo = Conta, acordo de parceria escolhido | sim |
| Formulário | vínculo = Oportunidade ou Projeto (campo ausente) | sim |
| Listagem | exibir a finalidade de um documento já enviado | **não** — reservado |
| Formulário | editar a finalidade depois do envio | **não** — reservado |

## Proveniência visual

Nenhum valor visual novo, nenhuma primitiva nova. É um `<select className="field">` dentro de um
`<label className="form-label">`, idêntico aos dois que já estão no mesmo formulário (`Vincular a`
e o alvo do vínculo), na mesma coluna e com o mesmo espaçamento.

## Evidência renderizada

`BROWSER_REQUIRED` é satisfeito pela cobertura que a rota `/documentos` já tem em
`frontend/e2e/a11y.spec.ts` (três larguras, contraste AA) — o campo entra na mesma coluna dos
existentes e não introduz par de cor novo.

A condição da decisão A1 tem testemunha em `frontend/src/pages/DocumentsPage.test.tsx`:
`a finalidade não existe fora do vínculo com conta` afirma que o campo some nos outros dois
vínculos, e `documento comum não manda kind nenhum` afirma que o padrão não escreve a chave.

## Fora da aprovação

- Acrescentar valores a `Document.kind` — cada um novo precisa ter comportamento e decisão própria.
- Exibir ou filtrar por finalidade na listagem de documentos.
- Tornar a finalidade editável depois do envio.
- Qualquer mudança no restante do formulário ou na listagem.
