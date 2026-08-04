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
