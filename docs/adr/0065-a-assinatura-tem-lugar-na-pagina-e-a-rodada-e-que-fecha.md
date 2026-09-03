# ADR 0065 — A assinatura tem lugar na página, e é a rodada que fecha

**Status:** aceita
**Data:** 2026-09-03
**Depende de:** ADR 0007 (assinatura eletrônica: fornecedor e webhook) · ADR 0061 (a assinatura
abre o mandato, e o que ela abre se declara antes) · ADR 0059 (a suíte não atravessa a rede para
provar um adapter) · FDD 009 (emenda de 03/09/2026)
**Implementada por:** `backend/apps/core/esign.py` (`paginas_do_pdf`, `posicoes_da_rodada`,
`_POSICAO_POR_PAPEL`, `Signer`, `_parse_created`, `email_da_contraparte`) ·
`SignatureRequest.SignerRole`, `Document.rodada_assinada` e `Document.is_signed` em
`backend/apps/core/models.py` · `_signers_do_pedido`, `DocumentViewSet.request_signature` e
`_discovery_attendee` em `backend/apps/core/views.py` · `ESIGN_HOUSE_SIGNER_EMAIL` em
`backend/config/settings.py` · migrações `0080` e `0081`

## Contexto

A primeira assinatura real do produto foi concluída em **03/09/2026**. Tudo o que a ADR 0007
prometeu funcionou: o documento subiu, o signatário assinou, a auditoria registrou, o webhook
voltou assinado e a solicitação virou `signed` sozinha.

E **a assinatura não apareceu no campo de assinatura**. Foi parar numa página anexa, no fim do
arquivo. O painel do fornecedor explica, com todas as letras:

> *"Esse signatário não possui campos de assinatura visíveis, a assinatura dele aparecerá somente
> na última página ao baixar o arquivo."*

O defeito não é do arquivo. A Autentique **não tem** detecção de âncora por texto — nada
equivalente às *anchor tags* do DocuSign —, então a linha `Assinatura: ______` que o template
desenha não é lida por ninguém. Onde a assinatura aparece é propriedade da **solicitação**, e se
declara em `positions` dentro de cada signatário do `createDocument`. Nós nunca mandamos esse
campo.

Ao investigar o envio, apareceu o segundo problema, maior e mais silencioso: o template de contrato
da casa tem **quatro** linhas de assinatura — a Biahflow, a parte contratante e duas testemunhas —
e foi exatamente esse o caso do primeiro contrato real. O portal só sabia pedir **um** signatário
por solicitação.

## Decisão

### 1. A página sai da contagem do PDF, e por isso entra uma dependência

Cada `position` é `{x, y, z, element}`: `x`/`y` em percentual 0–100 da página com origem no topo, e
`z` é o **número da página**. Não existe "última página", `z: -1`, página negativa nem repetição em
todas — o campo é um número de página e ponto.

Como o bloco de assinatura mora na última página do instrumento, e a API não aceita pedir "a
última", o número **precisa ser contado**. Ele não é dedutível de nenhum outro dado que o portal já
tenha: não está no `Document`, não vem do Drive, e o nome do arquivo não diz. Por isso entra
**`pypdf`** (BSD-3-Clause, sem dependência de runtime no Python 3.12) — a única dependência nova, e
o único jeito de responder a pergunta.

`esign.paginas_do_pdf` **nunca levanta**: ela é auxílio de posicionamento, não a operação. PDF
corrompido, ilegível ou arquivo que não é PDF devolvem `None`, e a solicitação sai **sem** posição,
com o motivo no log. Recusar seria pior que o defeito: o fluxo real de hoje envia `.docx`, e
converter `.docx` para PDF do nosso lado está fora de escopo. O reconhecimento é pelo conteúdo
(`%PDF`) e não pela extensão, porque `original_name` é digitado por gente.

Só três `Document.Kind` têm bloco de assinatura desenhado — `design_partner_agreement`, `nda` e
`commercial_contract`. A Proposta não tem, e o `kind` vazio não diz nada: nos dois casos a
assinatura vai sem posição, porque carimbá-la no meio de um texto corrido é pior que mandá-la para
a página anexa.

**As coordenadas x/y são estimativa declarada, não medida.** Não há conversor de `.docx` para PDF
nesta máquina, e o que vale é a geometria do PDF que a *Autentique* produz, não a do Word. O
primeiro envio real é a medição: abrir o documento no painel do fornecedor, ver onde cada campo
caiu, e ajustar os números — é uma linha por papel, num lugar só (`_POSICAO_POR_PAPEL`).

### 2. A solicitação tem N signatários numa chamada — nunca N chamadas

`Provider.send` passa a receber uma **lista** de `Signer` (e-mail + papel) e a devolver uma
referência por signatário. A razão é dura e não é de estilo: os três signatários assinam **o mesmo**
documento. Chamar o fornecedor uma vez por pessoa criaria três documentos separados lá dentro, cada
um com uma assinatura — e nenhum deles seria o contrato que as três pessoas pensam ter assinado.

Por isso o `ClicksignProvider` **recusa** mais de um signatário (`EsignProviderError`) em vez de
fazer laço. Um adaptador incompleto que falha alto é honesto; um que faz laço mente.

`_parse_created` deixa de escolher *um* signatário com fallback `signatures[0]`: com um signatário
só ele acertava por sorte, mas numa lista de três pegaria calado a referência de outra pessoa, e o
webhook passaria a fechar a assinatura errada. Agora é uma referência por e-mail pedido, e nenhuma
inventada para quem não voltou.

### 3. A rodada é o `document_ref`, e é ela que fecha

Todos os signatários criados numa chamada compartilham o mesmo `document_ref` — é o `id` que o
`createDocument` devolve. Então *"esta rodada de assinatura"* já era expressável no schema, sem
tabela nova: são as `SignatureRequest` do documento com o mesmo `document_ref`. Reenviar depois de
uma recusa cria uma rodada nova, com referência nova, e é por isso que a rodada — e não "todas as
solicitações do documento" — é o recorte certo.

`SignatureRequest.signer_role` (`house` · `counterparty` · `witness`) nasce com default
`counterparty`, e o default **é** a decisão: até aqui o único signatário que existia era a outra
parte, então toda linha já gravada está certa e não há backfill (migração `0080`).

**A rodada é um fato nosso, e não do fornecedor — e é por isso que ela é cunhada quando ele não a
dá.** A primeira versão desta decisão deixava `document_ref` vazio sem fornecedor homologado, e
tratava isso como "todas caem numa rodada só, aceitável no registro local". Não era aceitável: um
documento recusado, reenviado e **assinado à mão** ficaria com uma concluída e uma recusada no
mesmo grupo, e nunca mais contaria como assinado. Até esta ADR ele contava, porque a pergunta era
um `.exists()` — ou seja, a decisão introduziria uma regressão no modo que o `mark-signed` existe
para servir, e o `NullProvider` é modo **previsto**, não degradado.

Então `esign.send_for_signature` cunha uma referência `local:<uuid>` quando nenhum signatário
voltou com `document_ref`. A rodada nasce no instante em que a casa pede as assinaturas, e só
*coincide* com o `id` do `createDocument` quando existe fornecedor para emiti-lo. O prefixo torna a
referência auto-explicativa no banco e impede colisão com um id de fornecedor; ele nunca casa com
um webhook, e não precisa — sem fornecedor não há webhook.

As linhas anteriores a esta entrega ganham cada uma a sua referência na migração `0081`.
Historicamente **uma solicitação era uma rodada** (o endpoint criava uma por chamada, com um
signatário), então carimbá-las uma a uma não inventa história: reproduz exatamente o que o
`.exists()` respondia, agora sob o recorte novo.

### 4. Aceitar exige todos; recusar exige um

`Document.is_signed` era `.exists()` sobre as assinaturas concluídas. Com um signatário, "alguém
assinou" e "está assinado" eram a mesma frase e a propriedade estava certa por acidente. Com três,
o acidente acaba — e a primeira assinatura a chegar costuma ser a da **casa**, porque é ela quem
envia. Passa a ser: existe uma rodada em que **todas** as solicitações estão `signed` **com**
`signed_at` (a exigência dos dois campos juntos continua valendo, pela razão de sempre).

A partir daí a assimetria, que é deliberada:

- `signed` fecha o artefato de contrato como `ACCEPTED` **só quando a rodada fechou**;
- `declined` marca `REJECTED` **na hora** — não há o que esperar depois de alguém dizer não.

Sem essa correção, a assinatura da casa aceitaria o contrato, abriria o `Engagement` de Design
Partner (ADR 0061) e mandaria ao cliente o convite de marcar o Discovery, anunciando um acordo que
ele ainda não tinha assinado. Nada disso levantaria erro em lugar nenhum.

O convite do Discovery passa a sair para o signatário **`counterparty`** da rodada, e não para quem
assinou por último — que pode ser a casa ou a testemunha.

E eram **dois** os sítios que dependiam daquele atalho, não um: o convite por e-mail
(`esign.apply_decision`) e o convidado do evento no Google (`views._discovery_attendee`, que
ordenava por `-signed_at` e pegava o primeiro). Consertar só o primeiro deixaria o cliente recebendo
o link por e-mail enquanto o convite de calendário ia para dentro de casa. Quem responde é
`esign.email_da_contraparte`, público e num lugar só — duas buscas parecidas para a mesma pergunta
divergiriam no primeiro conserto, e esta já tinha divergido.

### 5. A casa entra sozinha, e continua desligada por padrão

`ESIGN_HOUSE_SIGNER_EMAIL` (**vazio por padrão**) acrescenta um signatário `house` a toda rodada
quando preenchido: quem envia não digita o próprio e-mail toda vez. Vazio, nada muda em relação a
antes desta ADR — é o que torna a entrega reversível por configuração.

O corpo do `request-signature` passa a aceitar `signers` (lista de `{email, role}`), e **continua
aceitando** `signer_email`, que vira um único `counterparty`. A forma canônica vence quando as duas
vêm juntas, pela regra de `docs/ontology/aliases.md` §2c; o alias morre na `/api/v2/`.

## Consequências

- **Uma dependência nova.** `pypdf` é a primeira biblioteca de manipulação de arquivo do backend, e
  ela só é usada para contar páginas. Se algum dia contarmos com outra coisa, o ponto de troca é
  uma função.
- **As coordenadas vão ser ajustadas.** Elas estão declaradas como estimativa no código, e o
  primeiro envio real é a medição. Isso é dívida conhecida com um lugar só para pagar, não
  incerteza espalhada.
- **O Clicksign fica mais incompleto do que estava**, e agora diz isso em voz alta. O adaptador
  homologado é o Autentique; o segundo continua servindo para o caso de um signatário.
- **A tela ainda não escolhe papéis.** Escolher contatos e papéis na SPA é `INTERFACE_CHANGE` e
  exige DAP aprovado antes de construir. Até lá o alias `signer_email` é o que mantém o produto
  funcionando, e a rodada de três é montada por quem chama a API.
- **Ficam fora**: posicionar `NAME`/`CPF`/`DATE`, ordem de assinatura, verificações de segurança,
  entrega por WhatsApp/SMS, converter `.docx` do nosso lado, e reposicionar documento já enviado.

## Alternativas consideradas

- **Âncora por texto no documento.** É o que o DocuSign faz e resolveria sem contar páginas. A
  Autentique não tem o recurso; escrever isso como se tivesse seria inventar API.
- **`z` fixo em 1, ou "todas as páginas".** O bloco de assinatura fica na última, e a API não aceita
  repetição nem página relativa. Cravar `1` acertaria só o contrato de uma página.
- **Chamar o fornecedor uma vez por signatário.** Produz N documentos separados, cada um com uma
  assinatura, e nenhum deles é o contrato. É exatamente o defeito silencioso que esta ADR existe
  para não ter.
- **Uma entidade `SignatureRound`.** O `document_ref` já expressa a rodada e é o que o webhook usa
  para casar. Uma tabela nova seria uma segunda definição do mesmo fato — e a metade que faltava
  (a rodada sem fornecedor) coube num cunho `local:` no mesmo campo, não numa tabela.
- **Converter `.docx` para PDF no backend.** Resolveria o posicionamento para o fluxo real de hoje,
  ao preço de uma dependência pesada e de um documento que a casa não revisou. Fica para quando o
  template virar PDF na origem.
