# Design Approval Package — O grupo do cliente aparece na linha do mandato

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Proposto**
Data: 2026-09-04
Produzido por: Claude Code (harness), a partir da issue `#116`

> Governado por `docs/engineering-os/workflows/design-approval.md`. Este artefato é evidência para
> um gate humano. Não é implementação e não deve ser copiado para dentro do código da aplicação.

---

## O que existe hoje, e por que há um gate

Desde a issue #110 o kickoff abre o grupo do cliente no WhatsApp; desde a #119 (04/09/2026) o
grupo **é do mandato** — nasce no `Engagement`, com nome `{Conta} · {Mandato}`, e o segundo
projeto do mandato entra no grupo que já existe. A referência está guardada, a criação incerta
notifica o dono do projeto (#117)…

**…e não há como ver o grupo em lugar nenhum do produto.** O link de convite sai uma vez, no
e-mail e na notificação de kickoff. Quem apagar o e-mail perde o canal; quem entrar no projeto
depois não descobre que ele existe.

Ficou de fora deliberadamente: mostrar o grupo é `INTERFACE_CHANGE`, e o gate vem **antes** do
planejamento. A #119 precisava vir primeiro — desenhar a superfície antes de decidir o dono do
grupo produziria um pacote para recortar de novo.

---

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede — nenhum `<script>`. |
| `board-desktop.png` / `board-mobile.png` | Capturas do board em 1280px e 390px. |

O board desenha três momentos: a linha do mandato com o grupo, a linha com grupo sem link de
convite, e a ausência (que é silêncio). A fonte Inter não é embutida; sem ela a página cai no
fallback do próprio token `--font-sans`.

---

## As quatro decisões

### Decisão A — onde o grupo aparece

| | |
| --- | --- |
| **A1** ⭐ recomendada | **Na linha do mandato**, seção "Engagements" do detalhe da conta (`AccountDetailPage`, governada pelo DAP `dap-engagement-r1/r3`). Um link discreto na faixa de meta da linha, junto das duas pílulas. |
| A2 | No detalhe do projeto. |
| A3 | Nos dois. |

**Por quê A1.** Desde a #119 o grupo é do mandato — é no `Engagement` que a referência mora, e a
linha dele já é onde o mandato se apresenta (status, modelo comercial, patrocinador, projetos). A2
mostraria no projeto um canal que não é da entrega: dois projetos do mesmo mandato mostrariam **o
mesmo** grupo como se fosse de cada um. A3 é A2 duas vezes.

**O que A1 não muda.** A visibilidade do mandato continua derivando do escopo de projeto
(`Project.objects.visible_to`, CLAUDE.md/ADR 0050) — a linha nova não cria caminho de acesso, só
mostra um campo a mais para quem já vê a linha.

### Decisão B — o grupo legado (de projeto) aparece?

| | |
| --- | --- |
| **B1** ⭐ recomendada | **Sim, por leitura derivada com fallback**: o serializer do `Engagement` emite o par do grupo num lugar só — o do próprio mandato quando existe; senão, o do **projeto vivo mais antigo** do mandato que tenha grupo legado. A tela não sabe a diferença. |
| B2 | Só o grupo do mandato; o legado fica invisível. |

**Por quê B1.** O acervo legado é exatamente o caso real de hoje (o grupo criado em 03/09/2026 é
de projeto). Com B2, o único grupo que existe de verdade continuaria sem tela — o problema que a
issue #116 existe para resolver seguiria de pé para ele. O fallback espelha a ordem de guardas que
`kickoff.abrir_grupo_de_whatsapp` já pratica (mandato primeiro, legado depois), num campo derivado
read-only — o molde de `owning_account` no `DocumentSerializer`: a cadeia mora no servidor, num
lugar só, e o front não a reexpressa.

**Contra-argumento registrado.** B2 é mais simples e o legado é finito. Recusada porque "finito"
hoje é "o único caso real", e uma tela que estreia sem mostrar o único grupo existente nasce
mentindo por omissão.

### Decisão C — o que aparece quando não há grupo

| | |
| --- | --- |
| **C1** ⭐ recomendada | **Nada.** A linha simplesmente não tem o link — a mesma regra do e-mail de kickoff (FDD 008): *"Grupo: — seria pior do que o silêncio: anuncia um canal e não entrega nenhum"*. |
| C2 | Estados diferenciados por causa da ausência (integração desligada, degrau sem grupo, sem contato com telefone, criação incerta). |

**Por quê C1.** As quatro ausências que as guardas do kickoff produzem não são a mesma coisa —
mas nomeá-las na linha do mandato seria vocabulário interno vazando para uma superfície de
relacionamento, e a única ausência perigosa ("pode existir um grupo e o produto não sabe") **já
tem canal próprio**: desde a #117 a criação incerta notifica o dono do projeto com a saída na
mensagem. As outras três são estados normais que não pedem ação de quem olha a conta.

### Decisão D — o que aparece quando há grupo

| | |
| --- | --- |
| **D1** ⭐ recomendada | **O link de convite, quando existe** — "Grupo no WhatsApp", link externo discreto no molde do link "Drive" da linha de documento. Quando o provedor devolveu o JID **sem** link (a UAZAPI pode), texto sem affordance: **"Grupo criado · sem link de convite"**. |
| D2 | Só o link; grupo sem link fica invisível (vira ausência). |

**Por quê D1.** São dois fatos (o JID identifica, o link se entrega — o comentário do modelo), e o
JID sozinho ainda responde a pergunta de quem olha: *o canal existe*. D2 faria "sem link" e "sem
grupo" parecerem o mesmo estado — e o operador tentaria criar de novo um grupo que existe, que é o
erro caro de sempre. O JID em si **não** aparece: não serve para uma pessoa.

---

## Consequências (não são decisões novas)

- `EngagementSerializer` ganha o par derivado read-only (`whatsapp_group_id`/
  `whatsapp_group_invite_url`, com o fallback da decisão B calculado no servidor), e o
  `openapi.yaml` é regenerado.
- O tipo `Engagement` do front ganha os dois campos; a linha do mandato ganha o link (ou o texto
  de D1) na faixa `.row-meta`, antes dos botões de ação.
- Nenhuma primitiva nova, nenhum token novo: o link usa o molde do link "Drive" da
  `DocumentsPage`; o texto sem link é `.type-meta` muted. A varredura de a11y já cobre o detalhe
  da conta nas três larguras.

## O que este pacote NÃO decide (reservado)

- **Criar o grupo pela tela** (para mandato que nasceu antes do kickoff automático ou cuja criação
  falhou). É ação com efeito externo e um segundo caminho para o mesmo ato — hoje só o kickoff
  cria. Se virar necessidade real, volta em r2 com decisão própria.
- **Mandar mensagem ao grupo pela tela.** `send_group_text` segue sem chamador de propósito.
- **Backfill** de grupo/referência para o acervo existente.

---

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| Revisão | r1 |
| Decisões | A · B · C · D |
| Aprovador | — |
| Data | — |
| Evidência pós-build | `BROWSER_REQUIRED` — captura da linha do mandato com o grupo, renderizada na SPA |

Aprovar este pacote autoriza planejar e construir **a revisão que ele descreve**. Mudança de
superfície depois disso exige r2, e não julgamento na hora.
