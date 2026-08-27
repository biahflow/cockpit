# ADR 0018 — Integração ligada por padrão quando configurada

**Status:** aceita
**Data:** 06/08/2026
**Contexto:** FDD 024 (sondas de integração), ADR 0003 (webhook do portal), ADR 0007 (assinatura
eletrônica), FDD 010 (notificações e digest)

## Contexto

As sete flags de integração nasciam `false`. O efeito, escrito com todas as letras no
`roadmap.md`, era que "cerca de metade do roadmap entregue fica apagada numa instalação nova":
quem subia o portal com credenciais válidas no `.env` ainda precisava descobrir a tela
Configurações e ligar cada recurso à mão para ver o que já estava pronto.

Ao mesmo tempo, `flags.is_enabled()` tinha um buraco. A tela recusava ligar uma integração sem
credencial (`ConfigView.patch` devolve 400), mas o **default do ambiente não passava por essa
porta**: com `ESIGN_ENABLED=true` e nenhum token, `is_enabled()` respondia `True`, o guard de 503
liberava a ação, e a falha só aparecia lá dentro do adaptador — como se fosse erro do fornecedor.
O comentário no topo de `flags.py` já dizia que "a promessa agora é verdade"; era verdade apenas
para o toggle.

Inverter os defaults sem fechar esse buraco transformaria o problema latente em problema garantido.

## Decisão

**Sem credencial não existe "ligada".** `is_enabled(name)` passa a ser
`configured(name) and desired(name)`, onde `desired()` é a intenção declarada (override do admin
ou default do ambiente). Vale para as sete flags, para o default e para o override.

**`email` e `esign` nascem ligadas.** `EMAIL_NOTIFICATIONS_ENABLED` e `ESIGN_ENABLED` têm default
`true`. As demais seguem `false` — IA e Drive/Calendário têm custo por chamada ou dependem de conta
Google, e ligá-las por conta própria seria gastar dinheiro alheio.

**O portal do cliente vira alternável.** Deixa de ser `toggleable=False`. `portal.emit()` passa a
consultar `flags.is_enabled("portal")` em vez de reler as settings — sem isso o toggle seria
decorativo, e desligar o portal durante um incidente continuaria exigindo deploy.

**A exigência de credencial da assinatura é dinâmica.** Sem `ESIGN_PROVIDER`, o e-sign roda no
`NullProvider`: registra a intenção e espera o `mark-signed` manual, sem chamar ninguém e sem
receber webhook. Esse modo não precisa de credencial alguma, e uma lista fixa em `requires` o teria
matado. Nomeado o fornecedor, `ESIGN_API_TOKEN` e `ESIGN_WEBHOOK_SECRET` viram obrigatórios. É o
mesmo mecanismo (`extra_missing`) que a ADR 0016 usa para a autenticação do Google.

**A sonda pergunta pela intenção, não pelo efeito.** `integrations.probe` passou a ler `desired()`.
Lendo `enabled`, ela calaria exatamente no caso que existe para denunciar — quem escreveu
`ESIGN_ENABLED=true` e esqueceu o token veria "desligada" em vez de uma reprovação nomeada.

**A tela diz o que falta.** `flags.status()` devolve `missing`, e Configurações troca "Faltam
credenciais no ambiente para ligar" por "Falta no ambiente: `ESIGN_API_TOKEN`".

## Consequências

- **É mudança incompatível de configuração.** Uma instalação existente que nunca declarou
  `ESIGN_ENABLED` e tem as três credenciais preenchidas passa a ter a assinatura ligada depois de
  atualizar. Quem não quiser precisa escrever `ESIGN_ENABLED=false`. Está no CHANGELOG.
- **Cuidado com placeholder.** `flags.missing()` só testa truthiness. Um
  `ESIGN_WEBHOOK_SECRET=<segredo do painel>` literal conta como configurado e agora **liga** a
  integração sozinho, com o webhook do fornecedor devolvendo 401 em silêncio. Quem valida isso é a
  sonda do `check_integrations`, não a flag — a distinção da FDD 024 segue valendo.
- **Produção passa a exigir SMTP real.** Com notificações ligadas por padrão, o default
  `localhost:1025` (o Mailpit do compose) deixa de ser inofensivo fora do dev. Ver
  `docs/runbooks/producao.md`.
- **`emit()` do portal ganhou uma consulta ao banco por evento.** É o preço de respeitar o toggle;
  a leitura é uma linha de `AppSetting` e acontece dentro de uma transação que já existe.
- **Trinta e três testes precisaram de credenciais fictícias.** Eles ligavam a flag sem token e
  passavam por causa do buraco que esta ADR fecha — o que é, em si, a evidência de que o buraco
  existia.
