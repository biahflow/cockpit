# FDD 008 — Kickoff automático na conversão de oportunidade em projeto

## Jornada

Etapa **Kickoff** da jornada de consultoria assistida por IA (RFC 0002). Ao converter uma
oportunidade **ganha** em projeto (`convert-to-project`), o Biahflow prepara o arranque:
cria um **cronograma inicial** (marcos + tarefas de um template), garante a **pasta do
projeto no Drive** (quando ligado) e avisa o responsável por **e-mail** e **notificação
in-app**. Tudo fica pronto para o dono revisar e ajustar.

## Regras

- O cronograma (`kickoff.KICKOFF_TEMPLATE`) é semeado **dentro da transação** da conversão:
  se a conversão falha (ex.: `IntegrityError` de dupla conversão), nada é criado.
- Prazos dos marcos/tarefas são limitados à janela do projeto (`min(início+offset, fim)`);
  o dono dos itens é o dono do projeto.
- Efeitos externos rodam **após o commit** e são **best-effort** (não bloqueiam a
  conversão): pasta no Drive só quando `GOOGLE_DRIVE_ENABLED` (senão no-op), e-mail com
  `fail_silently`, e sempre uma notificação in-app de kickoff ao dono.
- O e-mail só é enviado se o dono tiver endereço; o id da pasta é persistido em
  `Project.drive_folder_id`.
- Nada muda no contrato: `convert-to-project` continua retornando o projeto criado (201).

## Aceite

Converter uma oportunidade ganha cria o projeto **com** marcos e tarefas do template,
envia o e-mail de kickoff ao dono e registra a notificação in-app; a tela do projeto já
exibe o cronograma.

## Regressão crítica

Segunda conversão retorna 409 **sem** criar marcos/tarefas nem projeto; a conversão não
falha quando Drive/e-mail estão indisponíveis; itens ficam dentro da janela do projeto.

## Emenda (03/09/2026) — o kickoff abre o grupo do cliente no WhatsApp

O kickoff ganha um terceiro efeito externo, ao lado da pasta do Drive e do e-mail: **ao nascer o
projeto, a casa abre o grupo do cliente no WhatsApp** (issue #110). O adaptador
(`apps/core/whatsapp.py`) existia inteiro desde a [ADR 0062](../adr/0062-o-fallback-de-whatsapp-nao-assume-quando-nao-sabe.md)
— dois provedores, quatro estados de entrega, fallback ordenado, sonda, flag e testes — e **não
tinha um único chamador**. Nascer sem chamador e ficar sem chamador são a mesma dívida.

O grupo nasce com o nome `{Conta} · {Projeto}` e a referência dele fica em `Project`, em dois
campos: `whatsapp_group_id` (o JID, que endereça o grupo para mandar mensagem depois) e
`whatsapp_group_invite_url` (o link, que é o que se entrega a uma pessoa). São dois fatos
diferentes, e a UAZAPI pode devolver o primeiro sem o segundo. Migração `0079`, aditiva e **sem
backfill**: projeto que já existe não ganha grupo retroativo.

### Quem entra, e as quatro guardas

Entram os `Contact` **não arquivados** da conta que têm `phone` preenchido — a conta canônica é
`engagement.account`. Arquivado não entra: `archive()` é como a casa demite um contato, e um
contato arquivado num grupo de cliente é acesso que ninguém pretendeu conceder.

`kickoff.abrir_grupo_de_whatsapp` sai, em ordem, quando:

1. a flag `whatsapp` está desligada — calado, porque o próprio adaptador já registra a intenção;
2. o degrau está em `DEGRAUS_SEM_GRUPO_DE_WHATSAPP`, hoje só a **Qualification Call**: uma conversa
   de trinta a quarenta e cinco minutos não precisa de canal dedicado. **Projeto sem serviço ou com
   `tier` vazio ganha grupo** — é o default, não esquecimento: serviço avulso é trabalho de entrega
   de verdade;
3. `whatsapp_group_id` já está preenchido. `finalize` é best-effort e pode ser reexecutado; sem esta
   guarda a segunda execução cria o **segundo grupo** com o mesmo cliente, que é exatamente o erro
   caro que a issue #111 nomeia — e este chegaria ao cliente, como duas janelas de conversa com o
   mesmo nome;
4. nenhum contato tem telefone. Sem telefone não há grupo a criar, e um grupo só com a casa dentro
   seria um canal que o cliente nunca vê. O motivo vai para o log — é o mesmo "cala quando não
   sabe" de `receives_billing` (FDD 036), e telefone em log passa por `whatsapp._mask`.

### A ordem, e o que muda nas mensagens

A criação roda **antes** do e-mail, porque é o e-mail que entrega o convite. Ela é best-effort com o
mesmo desenho da pasta do Drive: `try/except` largo com `logger.exception`, nunca `pass` mudo, e o
kickoff **não falha** porque o WhatsApp caiu — o projeto já existe quando `finalize` roda.

O e-mail e a notificação de kickoff levam o link **quando ele existe**, e não mencionam grupo nenhum
quando não existe: "Grupo: —" seria pior que o silêncio, porque anuncia um canal e não entrega
nenhum. A gravação dos campos é responsabilidade do kickoff — `finalize` roda depois do commit, e
não há transação aberta carregando o campo junto.

### Duas consequências registradas

**A referência mora no projeto, e não no mandato.** Um `Engagement` com Discovery → Feasibility →
PROVE abre **três** grupos com o mesmo cliente. É consequência aceita nesta rodada; se for
revisitada, o lugar natural é o mandato — que é, por definição ([ADR 0050](../adr/0050-o-engagement-como-espinha-dorsal.md)),
"o mesmo trabalho".

**A superfície ficou fora desta rodada.** Mostrar o grupo no detalhe do projeto é
`INTERFACE_CHANGE` e exige DAP aprovado **antes** de construir
([`workflows/design-approval.md`](../engineering-os/workflows/design-approval.md)); fica para issue
própria. Mandar mensagem no grupo depois de criado (`whatsapp.send_group_text`) também ficou de
fora, e segue sem chamador.

O teto por operação e a reconciliação que sustentam essa criação estão na
[ADR 0064](../adr/0064-o-teto-e-por-operacao-e-a-resposta-incerta-se-reconcilia.md).

### `UNCERTAIN` pós-reconciliação avisa o dono do projeto (issue #117)

Quando o `create_group` volta com `Delivery.UNCERTAIN` **depois** de a reconciliação da ADR 0064 já
ter tentado e não ter resolvido, `abrir_grupo_de_whatsapp` chama `notifications.notify` para
`project.owner` — a mesma fila do produto que já entrega o e-mail e a notificação de kickoff, e não
uma escalada interna (esse é o padrão da cobrança, outro domínio). O `kind` é `"whatsapp"`, novo e
separado de `"kickoff"`, porque a notificação de kickoff não pode passar a mencionar grupo quando
não há grupo confirmado. A mensagem registra o fato **e** a saída — "ficou incerta" e "confira a
lista de grupos no WhatsApp antes de tentar de novo" — porque avisar sem dizer o que fazer transfere
o problema sem transferir a solução. `REFUSED` e `UNAVAILABLE` continuam só em log: são certeza de
não-entrega, e certeza de não-entrega não cria grupo órfão.
