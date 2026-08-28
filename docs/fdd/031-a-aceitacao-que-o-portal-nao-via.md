# FDD 031 — A aceitação que o portal não via

## Jornada

O portal do cliente instrumentou um funil de onboarding (RFC 001 de lá) para responder uma
pergunta que nenhum health score responde: **o cliente engaja?** Um projeto verde cujo cliente
parou de logar é churn silencioso, e só aparece quando ele reclama ou some.

Aquela RFC lista sete degraus de valor. Cinco nascem no portal, um chega pelo snapshot deste
repositório (o primeiro entregável saindo de `pending`) — e o sétimo, **artefato aceito
(`sent → accepted`)**, nasceu **declarado ausente** do enum de lá, com a razão escrita no
código e apontando para cá:

> *"A RFC o lista, mas o snapshot do Biahflow não carrega nada de artefato […] Declará-lo
> agora criaria um degrau que nada carimba […] **Ele entra quando o outro lado o afirmar.**"*

Deste lado o dado existe inteiro desde a FDD 016. `Artifact.status` tem `SENT` e `ACCEPTED`,
`save()` carimba `decided_at` na transição, o e-sign fecha o contrato sozinho quando o
signatário assina, e o `views.py` já calcula taxa de aceitação com aquele campo. O docstring
do próprio modelo diz para que ele existe: *"permite medir onde a jornada trava entre uma etapa
e a seguinte"*.

O que faltava era **atravessar**. `build_snapshot` não levava artefato nenhum, e `signals.py`
não tinha receiver de `Artifact` — a lacuna é da mesma família que a FDD 023 encontrou no
roster de funcionários digitais, um degrau antes: lá o fato entrava no snapshot sem emissor;
aqui o fato **não entrava no snapshot**, então não havia sequer o que emitir.

E o que isso custa é maior do que um degrau a menos numa lista. A régua que a RFC de lá nomeia
é o **time-to-first-value** — *"quanto o cliente demora do ganho até a primeira aprovação e até
o primeiro ROI visto"*. Sem esta data o portal não tem o **ganho**: ele conta os dias a partir
do convite, ou da criação da organização, que é a data em que ele por acaso conheceu o cliente.

## Regras

- **Atravessa um instante, e nada mais.** `artifact_accepted_at` é a data da **primeira**
  aceitação daquele cliente. Não vai `kind` (diria em que etapa do funil comercial ele está),
  não vai `title`, não vai `content` (o texto que a IA daqui redige é dado interno da casa),
  não vai valor e não vai contagem. A frase da ADR 0003 — *"nenhum dado comercial (Opportunity,
  PipelineStage, valores) é enviado ao portal"* — continua verdadeira, e a emenda de 07/08/2026
  diz por quê em vez de deixar por conta da leitura: nenhuma das três coisas nomeadas cruza. O
  que cruza é a data em que **o próprio cliente aprovou** alguma coisa.
- **O cálculo é por cliente, não por projeto.** O funil de lá é escopado por organização e um
  cliente pode ter vários projetos; os dois vínculos possíveis do artefato (`project` e
  `commercial_opportunity`) chegam à mesma `Account`. É pelo lado da oportunidade que o contrato
  quase
  sempre vive, porque aceitá-lo é o que *cria* o projeto depois.
- **Arquivado para de contar**, como todo filho no snapshot.
- **Só `ACCEPTED` emite.** Rascunho, revisão e envio mudam a linha várias vezes sem mover
  degrau nenhum. `REJECTED` também não move, e por uma razão de produto e não de economia: o
  funil mede o que o cliente **recebeu**, nunca o que nós fizemos — é a trava "degraus de valor,
  não vaidade" da RFC de lá, aplicada aqui.
- **O emissor resolve o projeto, e às vezes não há.** `portal.emit` não faz nada sem
  `project_id`. Então: o projeto do artefato quando há; senão o projeto vivo mais antigo do
  mesmo cliente; senão **nada**, e isso é limite declarado e não esquecimento — sem projeto o
  portal ainda não conhece aquela organização, e como `build_snapshot` calcula o campo sobre o
  cliente, o fato chega inteiro no primeiro snapshot depois que o projeto nascer.
- **Um projeto só, nunca fan-out.** O argumento é o mesmo que o `post_delete` de `Project` já
  escreve: cada aviso extra provoca uma busca de snapshot inteira do outro lado.

## Configuração

Nenhuma. O campo nasce no snapshot que já existe, atrás da flag `portal` que já existe, e o
receiver acompanha os outros nove em `signals.py`.

## Critérios de aceite

- O snapshot de um projeto leva `artifact_accepted_at` com a data da **primeira** aceitação do
  cliente, vindo tanto de artefato ligado ao projeto quanto de artefato ligado a uma oportunidade
  dele.
- Artefato em `sent` ou `rejected` **não** produz data; artefato aceito e depois arquivado deixa
  de produzi-la.
- Nenhum campo além da data atravessa — o `content` do artefato não aparece no snapshot.
- Aceitar um artefato emite webhook; mudar para `sent` não emite.
- Aceitar um artefato preso a uma oportunidade nomeia o projeto vivo **mais antigo** daquele
  cliente, e um só.
- Aceitar quando o cliente ainda não tem projeto nenhum **não estoura** e não emite projeto.

Testes em `backend/apps/core/tests/test_portal.py` (6). Medidos por sabotagem, como a FDD 021
estabeleceu: com `portal.py` e `signals.py` revertidos, os seis reprovam e os vinte anteriores
seguem verdes.

Do outro lado, o degrau entra no enum e é carimbado com `reached_at` igual a esta data — a
fatia gêmea é a ADR 0041 do `portal_cliente`.
