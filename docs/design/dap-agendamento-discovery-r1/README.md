# Design Approval Package — a página pública de agendamento do Discovery

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-09-02
Produzido por: harness (Claude Code), sob `docs/engineering-os/workflows/design-approval.md`

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Matiz, exposição, pós-escolha, estados de exceção e texto do e-mail da rota pública `/agendar/:token` |
| Aprovado por | Daniel Campos, nesta sessão |
| Data | 2026-09-02 |
| Revisão aprovada | r1 |
| Decisões | **A1** (clay) · **B1** (conta + contexto) · **C1** (sem remarcação) · **E2** (texto longo) |
| Decisão D | **D1** é a recomendação vigente e não foi submetida a escolha em separado — D2 não tem defensor. Contestável a qualquer momento antes da construção. |
| Explicitamente não aprovado | Remarcação e cancelamento pelo cliente; reenvio automático do link expirado; mudança na grade de horários ou no horizonte de 14 dias; tornar pública qualquer outra tela |

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação. Nenhuma linha de `frontend/src/` muda enquanto ele não for
> aprovado.

## Por que existe um gate

O ciclo do Design Partner termina hoje num beco: o acordo é assinado, o mandato é criado, e o
cliente não recebe nada. A proposta é que a assinatura dispare um e-mail de boas-vindas com um
link onde o próprio cliente escolhe o horário do Discovery — a primeira vez em que ele sente a
automação que a casa vende.

Isso acrescenta uma **rota sem autenticação**, e o pacote é maior que a tela que ele desenha por
causa disso: uma página que qualquer pessoa com o link abre é mudança de superfície de segurança,
não só de superfície visual.

> **Correção de fato, 2026-09-02.** A primeira redação desta seção afirmava que esta seria a
> primeira rota pública do produto além do login. É **falso**: `/aceitar-convite`
> (`AcceptInvitePage`) já é pública e já é movida a token — `App.tsx` a resolve antes do portão de
> sessão. O que esta rota tem de inédito é outra coisa, e é a que importa para o desenho: o
> `/aceitar-convite` fala com alguém que **está virando usuário do Pulse**, enquanto `/agendar`
> fala com um cliente que **nunca vai ter login**. Mesma mecânica, audiência oposta — e é dessa
> diferença que sai a Decisão A.

O precedente também é a referência de forma: cartão centrado em `bg-canvas`, `.panel` de largura
máxima, `.eyebrow`, `.alert--error`. A divergência é o token no caminho (`/agendar/<token>`) em vez
da query (`?token=`), porque este link o cliente recebe pronto e não digita.

Nenhuma aprovação vigente cobre isto. O DAP GH-26 r1 aprovou marca e fundações no shell e listou
"as outras 20 telas de produto" como não aprovadas; os DAPs de Engagement (r1, r2) cobrem a seção
de mandatos do detalhe da conta e nada além dela.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| `board-desktop.png` | Captura congelada a 1280px. |
| `board-mobile.png` | Captura congelada a 390px. |

As capturas são a evidência fixa: um board depende de fonte, navegador e plataforma, e é ao PNG
que a aprovação se refere. Elas retratam o **board**, não o produto — a evidência renderizada da
tela implementada é `BROWSER_REQUIRED` e vem depois, contra o código.

## O que está sendo pedido

Cinco decisões. Nenhuma primitiva nova; a página é montada com `panel`, `field`, `btn`,
`empty-state`, `alert--error` e `state`, que já existem.

### Decisão A — o matiz da página

A regra vigente (ADR 0024, revista pela 0025) é: *a forma é a mesma nos dois portais; o que
identifica é só o matiz — roxo `#6e56cf` é o portal do cliente, clay `#bd4a30` é este. Nunca use
um no outro.* Esta página é servida **pelo Pulse** e vista **por um cliente**, então ela é o
primeiro caso em que os dois critérios discordam.

- **A1 — clay.** O matiz identifica o produto que serve a página.
- **A2 — roxo.** O matiz identifica a audiência; o cliente verá roxo no One e duas caras confundem.

**Recomendação: A1.** A regra, como está escrita, é sobre identidade de produto; esticá-la para
"audiência" inventa um terceiro significado para o matiz e a torna ambígua no próximo caso. Há
ainda um argumento de fato: neste ponto da jornada **não existe projeto**, e sem projeto o One não
mostra nada (`portal.emit` sai cedo sem `project_id`) — ou seja, o cliente ainda não viu roxo
nenhum, e não há consistência a preservar. A A2 também colocaria roxo dentro do código clay, que é
literalmente o que a regra proíbe.

Consequência registrada: a marca é `pulse-mark.svg` sobre superfície clara — não a inversa, que só
existe para fundo escuro.

### Decisão B — o que a página mostra antes da escolha

O token **é** a credencial: quem tem o link vê o que estiver aqui.

- **B1** — nome da conta, uma linha dizendo o que é o Discovery, e os horários por dia.
- **B2** — só os horários, sem nomear a conta.
- **B3** — B1 mais o nome de quem conduz pela Biahflow.

**Recomendação: B1.** A B2 deixa quem recebeu sem saber se o link é o certo, e link que não se
identifica parece phishing — o oposto exato do efeito que a página existe para causar. A B3
acrescenta um dado pessoal que não ajuda a escolher horário.

O preço da B1 está declarado: quem tiver o link confirma que aquela conta tem relação com a
Biahflow. É divulgação real, ainda que pequena, e a mitigação é o alcance do link — ele vai por
e-mail a quem acabou de assinar o acordo.

### Decisão C — o que acontece depois de escolher, e se dá para remarcar

- **C1** — confirma na página, cria o evento no Google Calendar com o cliente convidado; reabrir o
  link mostra o horário marcado e **não** deixa remarcar sozinho.
- **C2** — o link continua remarcando até o Discovery acontecer.

**Recomendação: C1 nesta revisão.** Remarcar sozinho é melhor produto, mas exige desmarcar o evento
anterior, tratar a corrida de dois cliques e decidir o que fazer com convite já aceito — trabalho
que não é desta entrega e que ficaria mal-feito se entrasse junto. Fica **reservado**, não negado.

### Decisão D — os quatro estados que não são o caminho feliz

A classificação `INTERFACE_CHANGE` inclui vazio e erro, e aqui eles não são detalhe: três dos
quatro são mais prováveis que o caminho feliz no primeiro mês.

| Estado | Quando | O que a página diz |
| --- | --- | --- |
| Link expirado | passou a validade | expirou, e o caminho é responder ao e-mail |
| Link inválido | assinatura não confere | não reconhecido, sem dizer por quê |
| Sem horários | agenda cheia na janela | não há horário na janela, responda ao e-mail |
| Agenda indisponível | `CalendarUnavailable` | não foi possível carregar, tente mais tarde |

- **D1** — cada estado com sua mensagem, como na tabela.
- **D2** — uma mensagem genérica para os quatro.

**Recomendação: D1.** "Seu link expirou" e "não há horário livre" pedem coisas diferentes de quem
está lendo. O quarto estado existe porque `booking.freebusy` **falha fechado** de propósito
(`CalendarUnavailable` em vez de "tudo livre"): desenhar só o vazio faria a página afirmar que não
há horário quando o que houve foi a agenda não responder — mentira que custa uma reunião.

O estado "link inválido" não diz por quê deliberadamente: distinguir "assinatura errada" de
"mandato inexistente" para quem não está autenticado é dar retorno a quem está sondando.

### Decisão E — o texto do e-mail

É o que de fato chega ao cliente. Vai como constante revisada em código, no molde do `Degrau` de
`cobranca.py` — é a revisão humana da constante que autoriza o envio automático. Texto puro: não
há template HTML de e-mail neste produto, e a decisão é explícita.

**E1 — curto:**

> **Assunto:** Sua parceria com a Biahflow começou
>
> Olá, {nome}.
> O acordo está assinado — bem-vindo. O próximo passo é o Discovery, e você escolhe o horário:
> {link}
> Qualquer coisa, é só responder este e-mail.

**E2 — com o que esperar:**

> **Assunto:** Sua parceria com a Biahflow começou — vamos marcar o Discovery
>
> Olá, {nome}.
> O acordo de parceria está assinado. A partir daqui, a Biahflow entra no seu processo para
> entender onde está o trabalho que dói — é o Discovery, e ele dura de 5 a 7 dias.
> Comece escolhendo o melhor horário para a primeira conversa: {link}
> Na sessão vamos percorrer o processo junto com quem o executa. Não precisa preparar nada.
> Qualquer coisa, é só responder este e-mail.

**Recomendação: E2.** O e-mail é o primeiro contato depois da assinatura, e "não precisa preparar
nada" remove a hesitação que trava agendamento. A E1 é defensável se a preferência for sobriedade.

## Estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Página | horários disponíveis (caminho feliz) | sim |
| Página | confirmado, com o horário marcado | sim |
| Página | link expirado · inválido · sem horários · agenda fora | sim, os quatro |
| Página | carregando | sim |
| E-mail | as duas redações | sim |
| Página | remarcação pelo cliente | **não** — reservado (C1) |

## Proveniência visual

Nenhum valor visual novo. Os tokens do board são cópia de `frontend/src/index.css`
(`--color-brand-500: #bd4a30`, `--color-brand-900: #5c2317`, `ink`, `canvas`, `line`, `muted`, os
papéis tipográficos `--text-*` e o raio de cartão 12px / de controle 8px). Onde o board divergir do
produto, o produto vence.

## Entregue versus reservado

| Elemento | Esta revisão | Reservado para | Condição |
| --- | --- | --- | --- |
| Escolha de horário e confirmação | entrega | — | — |
| Os quatro estados de exceção | entrega | — | — |
| Remarcação pelo cliente | não desenha | trabalho futuro | tratar desmarcação e corrida |
| Cancelamento pelo cliente | não desenha | trabalho futuro | política de cancelamento definida |
| Escolha de duração ou de participantes | não desenha | — | fora do problema |

## Fora da aprovação

- Mudar a grade de horários (`BOOKING_HOURS`, seg–sex 9–12 e 14–17) ou o horizonte de 14 dias.
- Expor qualquer dado do mandato além do nome da conta.
- Reaproveitar esta rota para agendar outra coisa que não o Discovery.
- Tornar pública qualquer outra tela do produto.
- Decidir a política de reenvio do link quando ele expira.

## Notas para implementação

- O token é assinado (`django.core.signing`), escopado a **um** mandato e expirável; a rota é
  `AllowAny` com throttle próprio, como as de booking que já existem.
- A página não deve pedir login nem oferecer caminho para o resto do produto — sem menu, sem
  breadcrumb, sem link para `/`.
- O backend repete todas as invariantes: a interface não é fronteira de confiança.
- O estado "agenda indisponível" é diferente de "sem horários" e não pode cair no mesmo ramo.
- Entra em `e2e/a11y.spec.ts` como tela nova (3 larguras, contraste AA).
- Ordem de foco: marca, nome da conta, dias, horários, ação de confirmar.
