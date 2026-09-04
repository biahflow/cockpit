# ADR 0065 — A assinatura tem lugar na página, e é a rodada que fecha

**Status:** aceita
**Data:** 2026-09-03
**Depende de:** ADR 0007 (assinatura eletrônica: fornecedor e webhook) · ADR 0061 (a assinatura
abre o mandato, e o que ela abre se declara antes) · ADR 0059 (a suíte não atravessa a rede para
provar um adapter) · FDD 009 (emenda de 03/09/2026)
**Implementada por:** `backend/apps/core/esign.py` (`ancoras_de_assinatura`,
`_itens_da_ultima_pagina`, `posicoes_da_rodada`, `Signer`, `_parse_created`, `email_da_contraparte`) ·
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

### 1. A posição sai do próprio documento, e por isso entra uma dependência

Cada `position` é `{x, y, z, element}`: `x`/`y` em percentual 0–100 da página com origem no topo, e
`z` é o **número da página**. Não existe "última página", `z: -1`, página negativa nem repetição em
todas — o campo é um número de página e ponto.

Nem a página nem as coordenadas são dedutíveis de algum outro dado que o portal já tenha: não estão
no `Document`, não vêm do Drive, e o nome do arquivo não diz. **O documento precisa ser lido.** Por
isso entra **`pypdf`** (BSD-3-Clause, sem dependência de runtime no Python 3.12) — a única
dependência nova, e o único jeito de responder as duas perguntas.

A leitura **nunca levanta**: ela é auxílio de posicionamento, não a operação. PDF corrompido,
ilegível ou arquivo que não é PDF devolvem `None`, e a solicitação sai **sem** posição, com o motivo
no log — que é o comportamento de antes desta ADR, ruim mas funcional. Recusar seria pior que o
defeito. O reconhecimento é pelo conteúdo (`%PDF`) e não pela extensão, porque `original_name` é
digitado por gente: um `contrato.pdf` que na verdade é `.docx` cai aqui, e cai certo.

Converter `.docx` do nosso lado continua fora de escopo, e agora sem custo: os instrumentos da casa
passam a ir em PDF, que é o que torna o posicionamento **exato** em vez de aproximado.

Só três `Document.Kind` têm bloco de assinatura desenhado — `design_partner_agreement`, `nda` e
`commercial_contract`. A Proposta não tem, e o `kind` vazio não diz nada: nos dois casos a
assinatura vai sem posição, porque carimbá-la no meio de um texto corrido é pior que mandá-la para
a página anexa.

**A posição é lida do próprio documento, e não cravada por papel.** A primeira versão desta ADR
tinha um mapa fixo `papel → (x, y)`, declarado como estimativa porque não havia como medir. Os PDFs
dos dois instrumentos reais chegaram no mesmo dia, e a medição derrubou o mapa antes de ele chegar a
produção:

| linha | Contrato | NDA |
| --- | --- | --- |
| casa | 37,24% | 26,74% |
| parte contratante | 48,58% | 38,08% |
| testemunha 1 | 66,89% | 56,39% |
| testemunha 2 | 77,06% | 66,55% |

**Dez pontos percentuais** entre um documento e outro, porque a última página do contrato carrega
mais texto que a do NDA. E o problema não é ter dois templates: a razão social, o endereço e o
objeto do cliente entram no texto e empurram o bloco dentro do **mesmo** template. Um número cravado
acerta o documento em que foi medido e erra o próximo, sem nada ficar vermelho — que é a forma de
defeito que esta ADR inteira existe para não produzir.

A Autentique não tem detecção de âncora por texto, mas **nós temos o PDF em mãos** e o `pypdf` já é
dependência. Então a âncora é lida aqui: as corridas de sublinhado da última página são as linhas de
assinatura, e o rótulo `Testemunhas:` separa as de parte das de testemunha. O limiar de 20
sublinhados também é medido, não escolhido — as linhas de assinatura têm 43 a 47 caracteres e a
linha de data logo acima tem no máximo 19 por corrida; sem o limiar, a primeira "linha de
assinatura" encontrada seria a data.

Achar menos de duas linhas de parte devolve `None`, e a solicitação sai sem posição: significa que o
documento não tem o bloco que a casa desenha, e posicionar a partir de palpite é pior do que mandar
para a página anexa.

**Sobrou um número não medido, e só um:** o deslocamento que põe a assinatura *acima* da linha
(`_ACIMA_DA_LINHA`, 2,2% ≈ 18pt). A documentação do fornecedor não diz se `x`/`y` são o canto
superior esquerdo ou o centro do elemento, e o primeiro envio real resolve. Eram oito números no
escuro; é um.

A separação segue o molde do módulo: `_itens_da_ultima_pagina` é I/O e fica fora da cobertura;
`ancoras_de_assinatura` é pura e é testada com a geometria real dos dois instrumentos, que entra
como fixture — os PDFs não entram no repositório, porque são documentos de cliente.

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
- **O instrumento precisa ir como PDF para ser posicionado.** `.docx` não tem geometria até
  alguém convertê-lo, e quem converte é o fornecedor — depois de nós. Os templates da casa
  passam a ir em PDF, e é o que torna o posicionamento exato em vez de aproximado.
- **Um deslocamento continua por medir**, e só ele: se a assinatura sair sobre o rótulo, aumenta;
  se sair solta acima da linha, diminui. Um lugar só para pagar.
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
- **Mapa fixo de coordenadas por papel.** Foi a primeira versão desta decisão, e a medição dos dois
  instrumentos reais a derrubou no mesmo dia: dez pontos percentuais de diferença entre eles, e o
  texto do cliente empurrando o bloco dentro de cada um.
- **Chamar o fornecedor uma vez por signatário.** Produz N documentos separados, cada um com uma
  assinatura, e nenhum deles é o contrato. É exatamente o defeito silencioso que esta ADR existe
  para não ter.
- **Uma entidade `SignatureRound`.** O `document_ref` já expressa a rodada e é o que o webhook usa
  para casar. Uma tabela nova seria uma segunda definição do mesmo fato — e a metade que faltava
  (a rodada sem fornecedor) coube num cunho `local:` no mesmo campo, não numa tabela.
- **Converter `.docx` para PDF no backend.** Resolveria o posicionamento para o fluxo real de hoje,
  ao preço de uma dependência pesada e de um documento que a casa não revisou. Fica para quando o
  template virar PDF na origem.
