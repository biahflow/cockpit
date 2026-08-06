# FDD 024 — Sondas de integração e falhar fechado

## Jornada

O `roadmap.md` tem 33 itens `[x]` e 1 pendente. Só que as quatro entregas anteriores foram todas
defeitos em features **já marcadas como entregues**, e duas auditorias explicaram por quê:

- **As sete flags de integração nascem `false`**, e com os defaults **cerca de metade do roadmap
  entregue está apagada** numa instalação nova.
- **Todo código que fala com um provedor externo está atrás de `# pragma: no cover`** — Drive,
  Calendário, OpenAI, e-sign, Linear/GitHub. Os testes param na fronteira do mock, então nenhuma
  dessas linhas jamais executou, nem em teste nem em produção.

Só uma integração tem homologação registrada (Autentique, ADR 0007) e só um subsistema externo tem
exercício real e recorrente (backup/restauração, FDD 021).

A pergunta que este recorte responde: **a credencial existe ou a credencial funciona?**

## Regras

- **`configured()` cobra o que o código dereferencia.** Antes, cinco das sete flags podiam ser
  ligadas pela tela Configurações faltando a credencial usada na primeira chamada: Drive e
  Calendário pediam o id da pasta/agenda mas não a conta de serviço; e-sign pedia o nome do
  provedor mas não o token nem o segredo do webhook; `tasksync` pedia o segredo de **entrada** e
  nenhuma credencial de fornecedor. A tela dizia "Ligada" e o recurso estourava — enquanto o
  `docs/operacao.md` promete que "o toggle só não liga uma integração cujas credenciais faltem no
  ambiente". A promessa passou a ser verdade.
- **`requires_any` para credencial com duas formas.** A conta de serviço do Google chega como JSON
  inline **ou** como caminho de arquivo; exigir as duas recusaria instalação legítima.
- **A sonda pergunta ao provedor, e não ao ambiente.** `manage.py check_integrations` faz, por
  integração ligada, **uma chamada real, barata e só de leitura**, e sai com código 1 quando
  alguma reprova. É o irmão do `backup_status` (FDD 021) e existe pelo mesmo motivo: a aplicação
  não faz o trabalho, ela **diz se o trabalho é possível**.
- **A sonda nunca levanta e nunca cobra.** Diagnóstico que estoura vira "o diagnóstico quebrou" em
  vez de "a integração quebrou". E nenhuma sonda gera token, cria arquivo, manda e-mail ou abre
  documento — diagnóstico que cobra da conta de quem o roda não é rodado.
- **A sonda reusa o construtor de cliente do próprio adaptador** (`ai._client`, `drive._service`,
  `calendar_sync._service`). É o que a faz valer: credencial malformada estoura no mesmo código que
  estouraria em produção, e não num caminho paralelo que só se parece com ele.
- **`--all` sonda inclusive o desligado**, para conferir a credencial **antes** de ligar.
- **Sem sonda não é falha.** Onde não há como perguntar sem efeito colateral (`tasksync` sem
  credencial nesta instalação, `portal`, Clicksign), o resultado é "não sondável" e não "FALHOU" —
  alerta que grita errado treina quem opera a ignorá-lo.

### Falhar fechado

Quatro defeitos que só apareceriam contra o provedor real, corrigidos antes de qualquer credencial
ser apontada:

- **Evento de dia inteiro terminava no mesmo dia.** `end.date` é **exclusivo** no Google: start
  igual a end é intervalo de comprimento zero e a API recusa — o botão "Adicionar ao calendário"
  falhava em **100%** das tentativas. A regra saiu para `all_day_range()`, testável sem rede.
- **O free/busy falhava aberto.** Sem acesso ao calendário o Google devolve **200** com `errors` no
  lugar de `busy`; ler isso com `.get("busy", [])` produz "tudo livre", e o site passa a oferecer e
  marcar reunião por cima da agenda real. `parse_freebusy` levanta `CalendarUnavailable`, e os dois
  endpoints de agendamento devolvem 503 em vez de mentir sobre a agenda.
- **O digest contava envio que não houve.** `send_mail` devolve quantas mensagens saíram e, com
  `fail_silently=True`, isso é `0` quando o SMTP recusa ou não existe. O laço somava 1 assim mesmo,
  então o agendador logava "Digests enviados: 12" com zero entregues — o defeito do agendador
  inexistente uma camada abaixo, agora com o número dizendo que estava tudo bem.
- **Dois pontos derrubavam o pedido.** O upload no Drive era a única integração num caminho de
  **escrita** sem tratamento: credencial errada dava 500 mudo e o arquivo do usuário sumia (agora
  502, que diz de quem é o problema e que vale repetir). E `qualify_lead` chamava a OpenAI de forma
  síncrona **dentro do POST público** do formulário de leads, sem guarda e sem teto — um 429 virava
  500 para o visitante de um cadastro que na verdade funcionou, e o SDK espera 10 min por padrão,
  o que prenderia o worker. Ganhou `try/except` e `AI_TIMEOUT_SECONDS` (default 30 s).

## Configuração

| Variável | Default | O que faz |
| --- | --- | --- |
| `AI_TIMEOUT_SECONDS` | `30` | teto da chamada à OpenAI; protege o formulário público. É o teto **de verdade** desde a rodada 2: o cliente vai com `max_retries=0`, senão o SDK triplicaria o tempo por baixo |

## Critérios de aceite

- `manage.py check_integrations` com tudo desligado sai **0** e lista as sete como `desligada`.
- Integração ligada sem credencial **reprova antes de gastar rede**, nomeando a variável que falta.
- Sonda que estoura vira reprovação com a **mensagem do provedor** — é ela que diz o que consertar.
- A tela Configurações recusa ligar Drive/Calendário sem conta de serviço, e-sign sem token ou
  segredo de webhook, e `tasksync` sem credencial de fornecedor.
- Agenda inacessível **não** vira agenda livre: `/booking/slots/` e `/booking/book/` devolvem 503.

Testes em `apps/core/tests/test_integrations.py` e `tests/regression/test_integrations_fail_closed.py`.
Sabotagem deliberada, como nas entregas anteriores: repor a data final igual ao início e o
`.get("busy", [])` reprova três testes de regressão.

## Rodada 1 — e-mail, homologada em 06/08/2026

Primeira integração exercitada contra infra real. Procedimento e evidência em
`docs/runbooks/homologacao-de-integracoes.md`. O que a rodada produziu:

- **A sonda SMTP funciona** (`SMTP mailpit:1025 respondeu`) — primeira vez que uma sonda deste
  módulo roda contra algo de verdade.
- **A codificação do assunto está correta no fio**: RFC 2047 base64/utf-8, travessão e cedilha
  intactos. Era o principal risco, porque o backend de teste do Django guarda objetos em memória e
  **nunca codifica nada** — nenhum dos assuntos acentuados jamais tinha passado por MIME.
- **A correção da contagem do digest foi observada**: com o SMTP morto, `Digests enviados: 0` e um
  aviso por destinatário. Único item desta FDD que saiu de "corrigido por análise" para
  "corrigido e visto".
- **Defeito novo, achado e corrigido na rodada**: o convite ficava **órfão** quando o SMTP recusava
  — a linha era gravada e o `fail_silently=False` devolvia 500, deixando um convite válido que
  ninguém recebeu e que cada retentativa duplicava. Agora grava e envia na mesma transação, e
  devolve 502.
- **Comportamento documentado**: convite e kickoff **ignoram a flag `email`** (são transacionais).
  A FDD 010 dizia "desligada → nada muda (só in-app)", o que se lia como "nenhum e-mail sai".

## Rodada 2 — IA (OpenAI), homologada em 06/08/2026

Segunda integração exercitada contra o provedor real, e a primeira que custa dinheiro: **7 115
tokens em 15 chamadas** de `gpt-4o-mini`. Procedimento e evidência no runbook. As 12 superfícies de
IA responderam 200 e os quatro artefatos nasceram em `draft` com conteúdo (FDD 016).

**O que a sonda provou.** `models.retrieve` distingue, de graça, "a chave funciona" de "a chave
funciona mas esta conta não usa este modelo": com `AI_MODEL` inexistente e credencial boa, a sonda
**reprova** com a mensagem do provedor. É a tese desta FDD demonstrada em vez de argumentada.

**O que saiu de "corrigido por análise" para "corrigido e visto".** Os dois itens de blindagem que
faltavam: `qualify_lead` com o fornecedor fora do ar **não derruba** o POST público (lead gravado,
triagem manual), e o digest **entrega a todos** em texto estruturado em vez de morrer no primeiro.

**Antivazamento confere contra o modelo real.** A transcrição semeada omitia o orçamento de
propósito; Discovery, Assessment e o chat não o inventaram, e perguntado direto o chat recusou.
**E `_parse` aguenta**: o AI Score voltou como JSON válido de primeira, sem precisar de
`response_format`.

**Quatro defeitos novos, três corrigidos na rodada:**

- **O assistente do projeto respondia "Não sei." a pergunta que o contexto respondia** — três
  tokens de resposta, enquanto o `summary`, com o mesmo contexto, acertava. Duas causas: o contexto
  **não dizia que dia é hoje** (então "está atrasado?" era indecidível) e o texto de sistema
  proibia raciocinar ("use somente o contexto" virou "só repita o que está escrito"). Corrigidas e
  reconferidas: a resposta certa aparece, e o antivazamento não afrouxou.
- **`AI_TIMEOUT_SECONDS` não era o teto que prometia.** Com o teto em 1 s a chamada levou **5,5 s**
  — o SDK tenta 3 vezes por padrão, então o teto real era `timeout × 3` mais backoff. Com o default
  de 30 s, mais de um minuto e meio segurando um worker por causa de um formulário público. Agora
  `max_retries=0`; a retentativa mudou de dono, porque depois desta rodada todo ponto de chamada ou
  degrada ou devolve 502 dizendo que vale repetir.
- **O digest cobrava a cota de IA de quem nem pediu**, auditando com `user=user` — e sem consultar
  o limite, então era isento dele e cobrava dele ao mesmo tempo.
- **O agente de Entrega não sabe o que está atrasado** — e responde isso honestamente, porque
  `build_delivery_context` manda um resumo de resumos (`risco médio — Itens atrasados`) sem os
  itens. **Não corrigido**: é um dos agregadores recortados à mão pela ADR 0010, e ampliá-lo pede
  revisar o escopo com cuidado próprio.

## Varredura do Google — antes da rodada 3

A rodada 2 ensinou a lição: **a auditoria original desta FDD foi parcial**. Ela blindou 1 dos 4
pontos que chamavam a OpenAI. A varredura equivalente do Google, feita antes de apontar credencial,
achou o mesmo padrão — o **upload** no Drive estava protegido, e seis vizinhos não:

- **A reserva órfã** (`booking.book`), a mais grave e no caminho público: a `Booking` é gravada e a
  transação **fecha** antes de o evento ser criado. Recusa do Google deixava a reserva bloqueando o
  horário, sem evento, sem aviso ao dono, sem confirmação ao lead, e 500 para o visitante. Corrigida
  por **degradação**, que é o que o próprio código já fazia com o retorno vazio (`if event_id or
  link:`) — o defeito era a exceção não ser tolerada como o vazio era.
- **O download do Drive** (na action de documento e no `request-signature`), o `add-to-calendar` e a
  sincronia disparada pela tela: **502**, como o upload.
- **O transporte do free/busy**: o `parse_freebusy` falha fechado desde esta FDD, mas uma falha de
  rede um passo antes escapava crua. Vira **503** pela `CalendarUnavailable` que já existe — ali a
  pergunta é "o que há na agenda?", e a resposta honesta é "não sei".
- **O `kickoff.finalize`**, que engolia a falha do Drive com `pass` mudo: o projeto ficava sem pasta
  e ninguém sabendo.

Tipos estreitos (`DriveProviderError`, `CalendarProviderError`), pelo mesmo motivo da rodada 2. E
nasce `apps/core/exceptions.py`, porque a regra "falha de fornecedor é 502" já estava expressa em
três módulos e ia para quatro — *uma regra, uma expressão* (ADR 0010).

## Fora deste recorte

**As rodadas 3 e 4.** Google e assinatura seguem pendentes, com o roteiro pronto no runbook. Os
três defeitos de calendário e a blindagem do upload no Drive continuam corrigidos **por análise,
não por observação** — o teste prova a regra, só a credencial real prova a integração.

**O contexto do agente de Entrega.** O achado 4 da rodada 2: ele descreve risco em vez de listar
o que está atrasado, então a pergunta mais óbvia da área não tem resposta. Ampliar significa mexer
num agregador que a ADR 0010 recorta à mão, com teste de escopo próprio — recorte separado.

**Teto de tokens por chamada.** `AI_DAILY_LIMIT` conta chamadas, não custo, e nada limita o
tamanho de uma resposta. A rodada 2 mediu a ordem de grandeza real (média de ~225 tokens de saída,
máximo 854 no contrato) e não achou motivo urgente; um teto global truncaria contrato no meio de
uma cláusula, então, se entrar, é por feature.

**Rodar `check_integrations` pelo agendador.** O gancho é natural (o `scheduler` já faz isso com o
`backup_status`), mas fica para depois de as sondas provarem que não dão falso positivo.

**Convite de participante em evento por conta de serviço** (`create_timed_event` com `attendees`):
uma conta de serviço não convida sem delegação em todo o domínio, e o Google responde
`forbiddenForServiceAccounts`. É configuração do Workspace, não código, e vai no runbook da rodada
do Google.

**Clicksign.** O adaptador existe e não tem homologação — o `roadmap.md` creditava a ele a
homologação que o Autentique ganhou (ADR 0007). A linha foi corrigida; homologar o Clicksign é
item próprio.
