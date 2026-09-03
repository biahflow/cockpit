# Design Approval Package — Assinatura com papéis

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Aprovado**
Data: 2026-09-03
Produzido por: Claude Code (harness), a partir da issue `#115`

> Governado por `docs/engineering-os/workflows/design-approval.md`. Este artefato é evidência para
> um gate humano. Não é implementação e não deve ser copiado para dentro do código da aplicação.

---

## Por que existe um gate

A `#115` entregou o backend inteiro (ADR 0065): a assinatura tem posição na página, a solicitação
tem N signatários numa rodada só, cada um com papel (`house` · `counterparty` · `witness`), e a
rodada é o que responde se o instrumento está assinado. O endpoint aceita

```json
{"signers": [{"email": "...", "role": "counterparty"}, {"email": "...", "role": "witness"}]}
```

**E ninguém consegue mandar isso pela tela.** A superfície de hoje é, literalmente, um
`window.prompt` (`frontend/src/pages/DocumentsPage.tsx:95-100`):

```js
async function requestSignature(id: number) {
  const email = window.prompt("E-mail do signatário:");
  if (!email) return;
  await api(`/documents/${id}/request-signature/`, { method: "POST",
    body: JSON.stringify({ signer_email: email }) });
}
```

Um campo de texto do navegador, sem validação, sem contexto e sem como expressar papel. É o alias
`signer_email` que mantém isso funcionando — e ele existe exatamente para não deixar o produto sem
caminho enquanto este pacote não é aprovado.

O gate não é formalidade. O primeiro contrato real da casa teve **três** signatários (a Biahflow, a
parte contratante e uma testemunha do lado do cliente), e a tela sabe pedir **um**. A distância
entre o que o backend aceita e o que a tela oferece é o produto inteiro desta fatia.

E há a razão de sempre para o gate vir **antes** do planejamento: um plano que decompõe superfície
não decidida produz tarefas que precisam ser recortadas de novo.

---

## Uma correção de fato, antes das decisões

**A tela não consegue, hoje, saber de que conta um documento é.** O `DocumentEntry`
(`frontend/src/types.ts:223`) carrega `account`, `commercial_opportunity` e `project`, e o
`account` só vem preenchido quando o documento está vinculado **diretamente** a uma conta. Um
contrato pendurado numa oportunidade ou num projeto chega com `account: null`.

Isso não é detalhe de implementação: é o que decide se "puxar os contatos da conta" é uma
requisição ou três encadeadas. O backend já tem a regra de conta-dona num lugar só —
`drive.account_of(document)` segue o vínculo (conta → oportunidade.account → projeto.engagement.
account) e é usada em todo upload. A tela não tem equivalente e **não deve ganhar um**: seria a
segunda definição de "de quem é este documento".

A decisão **B** trata disso.

---

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede — nenhum `<script>`. |

O board desenha os quatro momentos da tela: o modal vazio, o modal com três signatários montados, o
aviso de documento sem posicionamento, e a lista de assinaturas depois do envio.

A fonte Inter não é embutida; sem ela a página cai no fallback declarado no próprio token
`--font-sans`, e o que muda é o desenho da letra, não a decisão em aprovação.

---

## Onde a superfície mora

| Superfície | Onde | Situação |
| --- | --- | --- |
| Modal "Enviar para assinatura" | `frontend/src/pages/DocumentsPage.tsx`, no lugar do `window.prompt` da linha 95 | **novo** |
| Botão que o abre | `DocumentsPage.tsx:144`, o `PenLine` que já existe | **não muda** |
| Lista de assinaturas | `DocumentsPage.tsx:145`, a `<ul>` sob cada documento | **ganha o papel** |

A tela **não é rota nova**, e isso é decisão (A). O ato é sobre um documento, e o documento já tem
uma linha com um botão de assinatura.

---

## O que está sendo pedido

Seis decisões. **A · B · C · D** são escolha entre opções; **E · F** nascem como *recomendação do
harness* e ficam identificadas como tal, porque `design-approval.md` exige que um agente diga quais
partes do pacote são proposta sua em vez de linguagem estabelecida do projeto — sem isso o
aprovador não sabe o que está de fato decidindo.

### Decisão A — onde mora o ato de pedir assinatura

| | |
| --- | --- |
| **A1** ⭐ recomendada | **Modal na `DocumentsPage`**, aberto pelo botão que já existe. Monta a rodada inteira (N signatários com papel) e envia numa chamada. |
| A2 | Rota nova, `/documentos/:id/assinatura`. |
| A3 | No detalhe da conta, junto dos contatos. |

**Por quê A1.** O ato é sobre **um documento**, e a linha do documento já é onde ele mora — com o
botão, o link do Drive, o "Lembrar" e a lista de assinaturas. Uma rota nova separaria o pedido do
objeto do pedido, e obrigaria a carregar de novo o que a listagem já tem em mãos. A rodada é curta
(dois a quatro signatários, e-mail e papel) e cabe num modal sem virar formulário longo.

**Contra-argumento registrado.** A2 daria espaço para pré-visualizar o documento ao lado da lista de
signatários — que é o que se faria se algum dia a tela precisasse mostrar *onde* cada assinatura vai
cair na página. Foi recusada porque essa necessidade não existe hoje: desde a emenda de 03/09/2026
na ADR 0065 a posição é **lida do próprio documento** (as linhas de assinatura são encontradas no
PDF), e não há coordenada para alguém revisar na tela. Se um dia houver, este pacote volta em r2.

### Decisão B — como a tela sabe a conta-dona, para oferecer os contatos

| | |
| --- | --- |
| **B1** ⭐ recomendada | O `DocumentSerializer` passa a emitir a **conta-dona derivada**, sempre — a mesma regra de `drive.account_of`, num lugar só. O modal busca `/contacts/?account=<id>` uma vez. |
| B2 | O front encadeia: lê `commercial_opportunity`/`project`, busca cada um, chega na conta. |
| B3 | Sem contatos: só digitar e-mail, como hoje. |

**Por quê B1.** B2 reescreve no front a cadeia `conta → oportunidade → projeto → engagement.account`
que `drive.account_of` já expressa — e as duas divergem no primeiro conserto sem nada ficar
vermelho. É o mesmo argumento que a decisão B do DAP de publicação usou para recusar inferência no
cliente. Além disso B2 custa até três requisições antes de o modal desenhar a primeira linha.

**Consequência.** Um campo derivado read-only a mais no `DocumentSerializer` (que hoje tem
`originated_engagement`, mesmo formato), e o `openapi.yaml` regenerado. **A chave `client` continua
saindo** como está: ela é alias da `/api/v1/` e não é a conta-dona derivada — são fatos diferentes
e não podem compartilhar nome.

**Contra-argumento registrado.** B3 é o mais barato e não mente sobre nada. Foi recusada porque o
caso real — dois do cliente e a casa — é justamente aquele em que digitar três e-mails à mão erra:
o e-mail do contato **já está cadastrado** na conta, e redigitá-lo é a operação que produz o
`fulano@clietne.com` que ninguém percebe até o convite não chegar.

### Decisão C — como o papel de cada signatário é escolhido

| | |
| --- | --- |
| **C1** ⭐ recomendada | **Seletor por linha.** Cada signatário adicionado tem um `<select>` com "Parte contratante" e "Testemunha". O default é Parte contratante. |
| C2 | Duas seções fixas — "Partes" e "Testemunhas" —, e se adiciona dentro de cada uma. |

**Por quê C1.** As duas linhas de testemunha do template são **de quem for** (decisão do usuário,
03/09/2026): não há uma reservada por lado. C2 desenharia uma estrutura que o instrumento não tem, e
obrigaria a mover uma pessoa de seção quando o papel dela muda — que é uma operação de arrastar para
resolver o que um seletor resolve com um clique.

**O que o seletor NÃO oferece.** "Biahflow" não é opção. O papel `house` existe no vocabulário
(`SignatureRequest.SignerRole`), mas quem o atribui é o servidor a partir de
`ESIGN_HOUSE_SIGNER_EMAIL` — deixá-lo escolhível na tela criaria dois caminhos para o mesmo fato, e
o segundo deles poderia nomear a casa com um e-mail que não é o dela. Ver **D**.

**Ordem importa, e a tela precisa dizer isso.** A primeira testemunha da lista ocupa a linha 1 do
documento e a segunda ocupa a linha 2; da terceira em diante não há linha e a assinatura vai **sem
posição** (ADR 0065). O board mostra a numeração ao lado do seletor quando o papel é Testemunha, e
um aviso na terceira.

### Decisão D — a casa aparece na lista de signatários?

| | |
| --- | --- |
| **D1** ⭐ recomendada | **Aparece como linha fixa, não removível e não editável**, no topo, quando `ESIGN_HOUSE_SIGNER_EMAIL` está configurado. Some inteira quando não está. |
| D2 | Não aparece. O servidor acrescenta e a tela não menciona. |

**Por quê D1.** Quem envia precisa saber quantas assinaturas o documento vai esperar, porque é isso
que decide quando ele fecha — e desde a ADR 0065 **aceitar exige todos**. Com D2, quem monta uma
rodada de dois recebe um documento que só fecha com três, e a diferença aparece como "o contrato não
foi aceito ainda" sem nada explicando por quê.

**Consequência.** A tela precisa saber se a casa entra, ou seja, se a variável está preenchida. Isso
**não** é expor o e-mail dela como segredo — é o e-mail com que a casa assina, que vai no próprio
documento. O caminho já existe: a `SettingsPage` lê o estado das integrações, e `flags` já responde
"configurado?" sem revelar valor. Se o valor em si não puder sair, a linha diz "Você (Biahflow)" sem
o endereço, e isso continua cumprindo o que D1 existe para cumprir.

**Contra-argumento registrado.** D2 é mais simples e evita expor configuração na tela. Foi recusada
porque esconde a informação que muda a leitura do resultado.

### Decisão E — o aviso de documento sem posicionamento

> **Proposta do harness.** É o que este gate decide.

| | |
| --- | --- |
| **E1** ⭐ recomendada | **Campo derivado read-only** no `DocumentSerializer`, calculado pelo mesmo `esign` que decide de verdade. O modal mostra o aviso quando ele diz que não haverá posição. |
| E2 | O front infere pela extensão de `original_name`. |
| E3 | Não avisar. |

**O problema que E resolve.** Desde a ADR 0065, a assinatura só ganha lugar na página quando o
arquivo é PDF legível **e** o `kind` tem bloco de assinatura desenhado. Os dois templates reais da
casa são `.docx` hoje — ou seja, **o caso mais comum é o que não posiciona**, e ele é silencioso: a
solicitação sai 201, o cliente assina, e a assinatura aparece na página anexa. Foi exatamente o
defeito que abriu a `#115`, e sem aviso ele volta como surpresa a cada envio.

**Por que E2 não serve.** O backend reconhece PDF pelo **conteúdo** (`%PDF`), não pela extensão,
porque `original_name` é digitado por gente. Um `contrato.pdf` que na verdade é `.docx` faria a tela
prometer posicionamento que não haverá — o aviso mentiria, que é pior do que não avisar.

**A copy do aviso diz o fato, não a causa técnica.** Proposta:

> *"Este documento não é PDF. As assinaturas vão para a última página do relatório, e não sobre as
> linhas de assinatura."*

e, para `kind` sem bloco:

> *"Documentos desta finalidade não têm bloco de assinatura. As assinaturas vão para a última página
> do relatório."*

**Contra-argumento registrado.** E3 mantém o `DocumentSerializer` como está. Foi recusada porque
transforma uma limitação conhecida em surpresa recorrente — e o produto já pagou uma vez por isso.

### Decisão F — o que a lista de assinaturas mostra depois do envio

> **Proposta do harness.** É o que este gate decide.

| | |
| --- | --- |
| **F1** ⭐ recomendada | A linha de cada assinatura ganha o **papel**, em texto discreto ao lado do e-mail. Os três selos de status (`Assinado`/`Pendente`/`Recusado`) **não mudam**. |
| F2 | Agrupar por rodada, com cabeçalho por rodada. |

**Por quê F1.** Com três signatários, "quem é quem" é a pergunta que a lista passa a não responder —
hoje ela mostra só o e-mail, e `daniel@biahflow.ai` ao lado de `fulano@cliente.com` não diz qual
deles é a casa. O papel é uma palavra e cabe na linha que já existe.

**Por que não agrupar por rodada agora.** A rodada existe no schema (`document_ref`) e é o que fecha
o documento, mas ela só se torna visível quando há **reenvio depois de recusa** — que é raro e que
ninguém relatou ainda. Agrupar por algo que quase sempre tem um grupo só é estrutura sem carga.
Quando houver um caso real, isto volta em r2.

**O que F1 deliberadamente não faz.** Não mostra "a rodada fechou". O estado do documento já se
expressa pelos selos das linhas, e um selo de documento inteiro seria uma segunda definição de
`is_signed` — a mesma armadilha que o `CLAUDE.md` nomeia para os mapas de estado. Se o operador
precisar da resposta agregada, ela é derivável de relance: todas as linhas verdes.

---

## O que este pacote NÃO decide

- **As coordenadas x/y.** Saem da leitura do próprio PDF (ADR 0065, emenda de 03/09/2026). A tela
  não as expõe nem as edita; o único número ainda por medir é o deslocamento acima da linha, e ele
  mora no backend.
- **Ordem de assinatura** (quem assina primeiro), verificações de segurança, entrega por
  WhatsApp/SMS. O `SignerInput` do fornecedor aceita; nós não usamos, e usar é decisão de produto.
- **Reposicionar documento já enviado.** Sem backfill, por decisão da `#115`.
- **A `SettingsPage`.** Se a decisão D exigir expor "a casa assina como…", isso entra como leitura
  no modal e não como campo editável em Configurações.

---

## Riscos e o que pode voltar em r2

1. ~~**O aviso de E pode virar ruído** se todo documento for `.docx`.~~ **Resolvido em 03/09/2026**,
   e pela saída que o próprio risco apontava: os instrumentos da casa passam a ir em **PDF**. O aviso
   volta a ser exceção em vez de regra — e, mais que isso, a medição dos PDFs reais trocou a
   coordenada cravada pela âncora lida do documento (emenda na ADR 0065), o que torna o
   posicionamento exato em vez de aproximado.
2. **D depende de a tela poder saber que a casa entra.** Se `flags` não puder responder isso sem
   expor o valor, a linha fica sem endereço — e vale conferir se "Você (Biahflow)" sem e-mail ainda
   responde a pergunta que D existe para responder.
3. **C1 assume no máximo duas testemunhas úteis.** A terceira em diante assina sem posição, e o
   board avisa. Se três testemunhas virarem caso comum, o template é que precisa mudar, não a tela.

---

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| Revisão | r1 |
| Decisões | A · B · C · D · E · F |
| Aprovador | Daniel Campos |
| Data | 2026-09-03 |
| Evidência pós-build | `BROWSER_REQUIRED` — captura das quatro telas do board renderizadas na SPA |

Aprovar este pacote autoriza planejar e construir **a revisão que ele descreve**. Mudança de
superfície depois disso exige r2, e não julgamento na hora.
