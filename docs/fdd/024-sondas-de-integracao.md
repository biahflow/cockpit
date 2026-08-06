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
| `AI_TIMEOUT_SECONDS` | `30` | teto da chamada à OpenAI; protege o formulário público |

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

## Fora deste recorte

**A homologação em si.** Este recorte entrega o instrumento e limpa o que a análise já provou
quebrado; apontar credencial real para IA, Google e assinatura é a rodada seguinte, com runbook
próprio. Os defeitos acima foram corrigidos **por análise, não por observação** — continuam atrás
de `# pragma: no cover`, e só a credencial real prova a integração.

**Rodar `check_integrations` pelo agendador.** O gancho é natural (o `scheduler` já faz isso com o
`backup_status`), mas fica para depois de as sondas provarem que não dão falso positivo.

**Convite de participante em evento por conta de serviço** (`create_timed_event` com `attendees`):
uma conta de serviço não convida sem delegação em todo o domínio, e o Google responde
`forbiddenForServiceAccounts`. É configuração do Workspace, não código, e vai no runbook da rodada
do Google.

**Clicksign.** O adaptador existe e não tem homologação — o `roadmap.md` creditava a ele a
homologação que o Autentique ganhou (ADR 0007). A linha foi corrigida; homologar o Clicksign é
item próprio.
