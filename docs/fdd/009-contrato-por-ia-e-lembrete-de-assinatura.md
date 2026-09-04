# FDD 009 — Contrato por IA e assinatura eletrônica

**A solicitação é o pedido ao fornecedor.** Com fornecedor configurado, se ele não devolver
referência, `request-signature` responde **502** e **nada é gravado** (FDD 024, rodada 4). Antes,
uma falha do Autentique virava 201 com uma `SignatureRequest` sem `provider_ref`: pendente para
sempre, impossível de fechar pelo webhook, e ainda cobrada por lembrete a uma pessoa de verdade.
Sem fornecedor configurado nada muda — o `NullProvider` registra a intenção e o `mark-signed`
manual segue valendo.


## Jornada

Etapa **Contrato** da jornada de consultoria assistida por IA (RFC 0002). No detalhe da
oportunidade, o time comercial gera um **rascunho de contrato por IA** a partir de um
modelo padrão de cláusulas, revisa e salva como documento. Sobre um documento, é possível
solicitar assinatura ao **fornecedor homologado**, lembrar quem ainda não assinou e
acompanhar o status — que o próprio fornecedor devolve por **webhook** (ADR 0007).

## Regras

- **Geração de contrato** (`opportunity.contract`, feature `contract`): reusa o motor de IA
  (`_ai_run`) — depende de `AI_ENABLED` (503), respeita o limite diário (429) e é auditada
  em `AiInteraction`. O modelo preenche o contrato só com o material fornecido e marca
  `[lacunas]`; a saída é **rascunho para revisão humana**.
- **Solicitar/lembrar assinatura** dependem da flag `esign` (503 quando desligada). Desde a
  ADR 0018 `ESIGN_ENABLED` nasce `true`, e "desligada" passou a incluir um caso novo: **fornecedor
  nomeado sem `ESIGN_API_TOKEN` ou sem `ESIGN_WEBHOOK_SECRET`**. Sem `ESIGN_PROVIDER` a flag fica
  ligada e vale o registro local descrito abaixo — esse modo não precisa de credencial.
  `request-signature` chama o adaptador do fornecedor (`ESIGN_PROVIDER`) enviando o arquivo
  de verdade — do Drive ou do storage local, mesma regra do download — e guarda o que voltou
  (`provider_ref` do signatário, `document_ref` do documento e `sign_url` quando houver).
  Sem fornecedor reconhecido, sem `ESIGN_API_TOKEN` ou com documento sem conteúdo, a
  solicitação fica só local. `remind-signature` envia e-mail **apenas** aos signatários com
  status `pending` (best-effort, `fail_silently`), carimba `reminded_at` e retorna quantos
  foram lembrados; o link de assinatura entra no corpo quando existe.
- **Quem avisa o signatário** é `ESIGN_DELIVERY`. Em `email` (padrão) o fornecedor manda o
  convite oficial e o portal não duplica o aviso — o `sign_url` fica vazio e a tela esconde
  o botão "Assinar". Em `link`, o fornecedor devolve o link, o portal grava, convida o
  signatário na hora (`invite_signer`) e repete o link no lembrete. `ESIGN_SANDBOX=true`
  cria documentos de teste (sem crédito, apagados pelo fornecedor em poucos dias).
- **Webhook de status** (`POST /api/v1/esign/webhook/`, público, sem sessão):
  - **503** com a flag `esign` desligada — o que agora inclui a falta de `ESIGN_WEBHOOK_SECRET`
    com fornecedor nomeado, que antes caía no 401 (ADR 0018); **401** quando o HMAC-SHA256 do
    **corpo cru** não confere; **400** com corpo que não é um objeto JSON.
    O header e o formato são de cada fornecedor: Autentique `x-autentique-signature` com o
    hex puro; Clicksign `Content-Hmac: sha256=<hex>`. A entrega de um fornecedor não passa
    quando o `ESIGN_PROVIDER` é outro.
  - De-para explícito de eventos. Autentique: `signature.accepted` → `signed`,
    `signature.rejected` → `declined`. Clicksign: `sign`/`auto_close`/`document_closed` →
    `signed`, `refusal`/`cancel` → `declined`. Qualquer outro **não move** a assinatura.
  - Casa a `SignatureRequest` por `provider_ref`; na falta dele, por `document_ref` +
    e-mail do signatário (case-insensitive).
  - **Idempotente**: reentrega do mesmo evento responde 200 sem recarimbar `signed_at` nem
    gerar segunda notificação. Evento desconhecido ou sem solicitação correspondente
    responde **200 "Evento ignorado."** — erro faria o fornecedor reentregar para sempre.
  - Ao aplicar, notifica quem enviou o documento (`uploaded_by`) via `notifications.notify`.
  - Protegido por `ScopedRateThrottle` (`esign_webhook`, default `120/hour`).
- **Registrar assinatura** (`mark-signed`): fallback manual — move a `SignatureRequest`
  para `signed` com `signed_at` quando não há provedor configurado (ou a assinatura correu
  fora do fluxo). Assinaturas concluídas deixam de receber lembrete. Assinatura inexistente
  → 404.
- O acesso segue o RBAC do recurso `document`/`commercial_opportunity`; documentos seguem privados
  (ADR 0002) e nada comercial vaza para o portal do cliente (ADR 0003).

## Aceite

Numa oportunidade, "Gerar contrato" retorna um rascunho para revisão e salva como
documento. "Enviar para assinatura" cria o documento no fornecedor com o arquivo real; com
`ESIGN_DELIVERY=link` o link do signatário aparece como "Assinar" na lista. "Lembrar"
dispara e-mail aos pendentes (com o link, quando houver); quando o signatário assina no
fornecedor, o webhook marca "Assinado" sem intervenção e notifica quem enviou o documento.
"Marcar assinado" segue disponível como fallback manual; o status aparece por signatário.

## Regressão crítica

`contract` retorna 503 com IA desligada; `remind-signature` retorna 503 com esign
desligado e só e-mail os pendentes; após `mark-signed`, um novo lembrete lembra 0;
`mark-signed` de assinatura inexistente retorna 404. No webhook: HMAC errado → 401,
evento fora do de-para → 200 sem mudar nada, e **reentrega do mesmo evento não altera
`signed_at` nem duplica notificação** (`backend/tests/regression/test_esign_webhook_idempotent.py`).
## Emenda (03/09/2026) — a assinatura tem lugar na página, e a rodada tem mais de uma pessoa

A primeira assinatura real do produto foi concluída neste dia, e tudo o que esta FDD prometia
funcionou: o arquivo subiu, o signatário assinou, a auditoria registrou, o webhook voltou e a
solicitação virou `signed` sozinha. **E a assinatura não apareceu no campo de assinatura** — foi
para uma página anexa, no fim do arquivo. O painel do fornecedor diz o motivo com todas as letras:
*"esse signatário não possui campos de assinatura visíveis, a assinatura dele aparecerá somente na
última página ao baixar o arquivo"*.

Não é defeito do arquivo. A Autentique **não tem** detecção de âncora por texto (nada equivalente
às *anchor tags* do DocuSign), então a linha `Assinatura: ______` do template não é lida por
ninguém. Onde a assinatura aparece é propriedade da **solicitação**, e se declara em `positions`
dentro de cada signatário do `createDocument` — campo que `request-signature` nunca mandou. Ao
investigar o envio apareceu o segundo problema, maior: o template de contrato da casa tem **quatro**
linhas de assinatura (a Biahflow, a parte contratante e duas testemunhas), que foi exatamente o caso
do primeiro contrato real, e o portal só sabia pedir **um** signatário por solicitação. A decisão
está na [ADR 0065](../adr/0065-a-assinatura-tem-lugar-na-pagina-e-a-rodada-e-que-fecha.md).

### O que muda nas regras acima

- **`request-signature` aceita uma lista.** O corpo canônico é
  `{"signers": [{"email": …, "role": …}]}`, com `role` ∈ `house` · `counterparty` · `witness`
  (`SignatureRequest.signer_role`, migração `0080`, default `counterparty` — toda linha já gravada
  está certa sob esse default, e por isso não há backfill). O corpo antigo (`{"signer_email": …}`)
  **continua aceito** e vira um único `counterparty`; a forma canônica vence quando as duas vêm no
  mesmo corpo, e o alias morre na `/api/v2/` (`docs/ontology/aliases.md`). A resposta passa a
  devolver a lista de solicitações criadas. Recusas de **400**: lista vazia, papel desconhecido e
  e-mail repetido — este porque o fornecedor casa signatário por e-mail, e dois iguais tornam
  ambíguo qual assinatura o webhook veio fechar.
- **Uma chamada ao fornecedor, N signatários.** Os três assinam **o mesmo** documento: chamar o
  fornecedor uma vez por pessoa criaria três documentos separados lá dentro, cada um com uma
  assinatura, e nenhum deles seria o contrato que as três pessoas pensam ter assinado. Por isso o
  adaptador Clicksign **recusa** mais de um signatário em vez de fazer laço — ele continua servindo
  para o caso de um.
- **A assinatura vai posicionada** quando dá: `z` é o **número da página** (a última, contada com
  `pypdf` sobre os bytes que já buscávamos), e `x`/`y` são percentuais da página com origem no topo.
  Só os `kind` com bloco de assinatura desenhado — `design_partner_agreement`, `nda` e
  `commercial_contract` — são posicionados; a Proposta não tem bloco e o `kind` vazio não diz nada.
  **Sem posição manda assim mesmo e registra o motivo no log**: o fluxo real de hoje usa `.docx`, e
  recusar quebraria o que funciona. A testemunha sai com `action: "SIGN_AS_A_WITNESS"`, ocupa a
  primeira linha livre de testemunha, e da terceira em diante vai sem posição — empilhar duas
  assinaturas no mesmo ponto é pior que a página anexa. **As coordenadas x/y são estimativa
  declarada, não medida**: o primeiro envio real é a medição, e ajustá-las é uma linha por papel.
- **A casa entra sozinha** quando `ESIGN_HOUSE_SIGNER_EMAIL` está preenchido (vazio por padrão, e é
  o que mantém a mudança reversível): quem envia não digita o próprio e-mail toda vez.
- **"Assinado" passa a ser por rodada.** Todos os signatários criados numa chamada compartilham o
  mesmo `document_ref`, e é essa a rodada; reenviar depois de uma recusa cria outra. `Document.is_signed`
  era um `.exists()` — com um signatário, "alguém assinou" e "está assinado" eram a mesma frase, e
  a propriedade estava certa por acidente. Agora exige uma rodada em que **todas** as solicitações
  estão `signed` **com** `signed_at`.
- **Aceitar exige todos; recusar exige um.** O artefato de contrato só vira `ACCEPTED` quando a
  rodada fecha; uma recusa marca `REJECTED` na hora. Sem isso, a assinatura da **casa** aceitaria o
  contrato, abriria o mandato de Design Partner (ADR 0061) e mandaria ao cliente o convite de marcar
  o Discovery — anunciando um acordo que ele ainda não tinha assinado, sem nada ficar vermelho. E o
  convite do Discovery passa a sair para o signatário `counterparty` da rodada, nunca para quem
  assinou por último, que pode ser a casa ou a testemunha.

### O que **não** muda

A tela. Escolher contatos e papéis na SPA é `INTERFACE_CHANGE` e exige DAP aprovado antes de
construir; até lá o alias `signer_email` é o que mantém o produto com caminho para pedir assinatura,
e a rodada de três é montada por quem chama a API. Ficam de fora também: posicionar `NAME`/`CPF`/
`DATE`, ordem de assinatura, verificações de segurança, entrega por WhatsApp/SMS, converter `.docx`
para PDF do nosso lado, e reposicionar documento já enviado.

> **A tela chegou na emenda seguinte (03/09/2026, issue #120).** O que este bloco reservava era o
> DAP, e ele foi aprovado — ver abaixo.

### Regressão desta emenda

`backend/tests/regression/test_o_alias_signer_email_sobrevive_na_v1.py` (o corpo antigo continua
criando a solicitação de `counterparty`, e a forma nova vence quando as duas vêm juntas) e
`backend/tests/regression/test_uma_rodada_de_tres_nao_abre_o_mandato_antes_da_hora.py` (a assinatura
da casa não abre o mandato, não aceita o contrato e não dispara o convite). Os demais critérios —
contagem de páginas, posições por papel, as duas linhas de testemunha, o `createDocument` único e as
três recusas de 400 — estão em `backend/apps/core/tests/test_esign.py`.

## Emenda (03/09/2026) — a tela que pede a rodada

O DAP [`dap-assinatura-com-papeis-r1`](../design/dap-assinatura-com-papeis-r1/README.md) foi
aprovado em r1 (decisões **A1 · B1 · C1 · D1 · E1 · F1**) e a superfície foi construída: o
`window.prompt` que pedia um e-mail solto virou um modal na `DocumentsPage` que monta a rodada
inteira — N signatários com papel — e envia numa chamada. Mudar essa superfície exige r2, e não
julgamento na hora.

O que a `/api/v1/` ganhou para a tela poder existir, tudo derivado e read-only:

- **`DocumentSerializer.owning_account`** — a conta-dona, pela mesma regra de `drive.account_of`
  (B1). É o que faz o modal buscar os contatos da conta em **uma** requisição. Não se confunde com
  a chave `client`, que é o alias de leitura do vínculo direto: um contrato pendurado numa
  oportunidade sai com `client: null` e conta-dona preenchida — fatos diferentes, nomes diferentes.
- **`DocumentSerializer.signature_positioning_gap`** (`not_pdf` · `kind_without_block` · `null`),
  de `esign.lacuna_de_posicionamento` (E1). É o aviso de que a assinatura **não** vai cair sobre as
  linhas, dito antes do clique em vez de descoberto depois do 201. `null` é "nenhuma lacuna
  conhecida" e **não** é promessa de posição: quem decide de verdade continua sendo
  `posicoes_da_rodada`, lendo os bytes reais na hora do envio.
- **`Document.content_is_pdf`** (migração `0082`) — carimbado **no upload**, único momento em que
  os bytes estão em mãos: com o Drive ligado o arquivo só existe lá, e farejar na leitura custaria
  um download por linha da listagem. `null` é "não medido", nunca `False`, e o legado do Drive fica
  sem carimbo em vez de ganhar um valor inventado. Listar documentos **nunca** toca o Drive.
- **`SignatureRequest.signer_role` no `GET`** — o campo existia e só o `POST` o devolvia; a lista de
  assinaturas passa a dizer quem é a casa, quem é a parte e quem testemunha (F1). Os três selos de
  status não mudam, e não há selo de "documento assinado": ele seria a segunda definição de
  `Document.is_signed`.
- **`/config/.esign_house_signer_email`** — sai **fora** de `integrations` de propósito: uma flag
  responde "configurado?" sem revelar valor, e aqui o valor é a resposta (D1). Não é segredo — é o
  e-mail com que a casa assina, e ele vai no próprio documento. É o que faz a linha fixa
  "Você (Biahflow)" existir, e sumir inteira quando a variável está vazia.

**A casa não vai no corpo do `POST`.** Quem a acrescenta é o servidor, a partir de
`ESIGN_HOUSE_SIGNER_EMAIL` — dois caminhos para o mesmo fato é o que a decisão C recusa, e o segundo
deles poderia nomear a casa com um e-mail que não é o dela. Pela mesma razão "Biahflow" não é opção
do seletor de papel. O botão de enviar nasce desabilitado: a casa sozinha não é rodada, e um botão
vivo para um `POST` que o servidor recusa é o defeito nomeado no `CLAUDE.md`.

**O alias `signer_email` continua vivo, e agora ele só tem um chamador: a regressão.** A SPA passou
a escrever `signers`, então nada dentro do repositório escreve mais a chave antiga — e é exatamente
aí que uma varredura futura a removeria "pagando dívida", quebrando a `/api/v1/` de quem integrou
sem nada ficar vermelho. Ver a nota atualizada em
[`docs/ontology/aliases.md`](../ontology/aliases.md) §2c.

Fica reservado no pacote, para um r2 com caso real: ordem de assinatura, agrupar a lista por rodada
e editar coordenadas.

### Regressão desta emenda

`frontend/src/pages/DocumentsPage.test.tsx` (a rodada montada, a linha fixa da casa e o sumiço dela,
a numeração das testemunhas com o aviso da terceira, o corpo do `POST` na ordem da lista e sem a
casa, as duas frases do aviso E1 e os três papéis na lista) e, no backend,
`apps/core/tests/test_esign.py` (a lacuna nos cinco caminhos, incluindo o do Drive que **não** pode
tocar a rede) mais `apps/core/tests/test_api.py` (o carimbo no upload, a prova do `seek(0)` de que
o Drive recebe o arquivo inteiro, a conta-dona nos três vínculos e o e-mail da casa no `/config/`).
A varredura de acessibilidade abre o modal em `/documentos` nas três larguras — sem isso o
`.alert--warn`, cor nova, nunca passaria pela medição de contraste.
