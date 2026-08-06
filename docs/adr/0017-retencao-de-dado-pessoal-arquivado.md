# ADR 0017 — Retenção de dado pessoal arquivado

- **Status:** aceita
- **Data:** 06/08/2026
- **Contexto:** FDD 021 (backup e retenção), ADR 0002 (documentos privados), LGPD

## Contexto

O portal sempre soube **arquivar** e nunca soube **esquecer**. `archived_at` tira a linha das telas
e ela fica indefinidamente — no banco, nos backups e em qualquer agregador que não filtre. Dezesseis
modelos usam esse campo.

A FDD 021 tratou retenção de **cópias de segurança** e registrou explicitamente que retenção de
**dado de negócio** era "outro assunto". Esse outro assunto nunca foi tratado, e o relógio dele
começa a correr no dia em que entrar dado de cliente real — que é agora, na preparação para
produção.

Duas coisas se misturavam nessa pendência, e a decisão é separá-las: **o mecanismo** (código) e
**os prazos** (negócio, com peso jurídico).

## Decisão

Entra o **mecanismo**, com os prazos deliberadamente vazios.

- **`manage.py purge_archived`, ensaio por padrão.** Sem `--apply` ele apenas relata o que faria.
  É a única operação do portal que destrói dado de propósito, num repositório cuja regra é soft
  delete em todo lugar — e um expurgo que apaga por engano é pior que um expurgo que não existe.
- **Retenção `0` = nunca expurgar, e é o default de todas as famílias.** O portal nasce inerte:
  ninguém perde dado por ter atualizado. O expurgo começa quando alguém decidir o prazo.
- **Duas famílias, não dezesseis.** `Lead` e `Document` são as que guardam dado pessoal e são
  autocontidas. Prazo por família via `RETENTION_LEAD_DAYS` e `RETENTION_DOCUMENT_DAYS`.
- **O arquivo sai antes da linha.** Apagar o registro e deixar o PDF no Drive ou no disco é meio
  expurgo, e o pior tipo: some o índice e o conteúdo permanece sem ninguém saber que existe. Se o
  arquivo não sair, a linha **fica**, para o próximo expurgo tentar de novo.
- **A contagem parte de `archived_at`**, não de `created_at`: o relógio começa quando alguém
  decidiu que aquilo saiu de uso. Linha viva nunca entra — este comando não decide o que sai de
  uso, ele esquece o que já saiu.

## Restaurar zera o relógio (FDD 025)

O prazo conta a partir de `archived_at`. Com a restauração pela interface, `archived_at` volta a
`NULL` e o registro deixa de ser candidato ao expurgo — o relógio não "continua de onde parou",
recomeça se ele for arquivado de novo.

É intencional: um lead ou documento que voltou ao uso não deve ser apagado por um prazo que corria
enquanto ele estava fora. Quem restaura assume o dado de volta.

## Consequências

- **O mecanismo existe e não faz nada até ser configurado.** É a postura certa para uma operação
  destrutiva, mas tem um custo honesto: enquanto ninguém definir prazo, a pendência de LGPD segue
  aberta — o que mudou é que ela deixou de ser também um problema de engenharia.
- **`Client`, `Project` e `Opportunity` ficam de fora, de propósito.** Apagá-los cascatearia sobre
  histórico comercial inteiro (oportunidades, projetos, ROI, indicadores), e isso é decisão de
  negócio maior que "quanto tempo guardar". Fica registrado como **não automatizado**, e não como
  esquecido.
- **O expurgo não é reversível pelo backup**, e essa é a intenção: se a cópia guardasse o que o
  expurgo apagou, o expurgo não teria acontecido. Quem definir os prazos precisa considerar a
  janela de retenção das cópias junto (FDD 021).
- **Não entra no `scheduler`** por enquanto. Rodar sozinho uma operação destrutiva antes de alguém
  ter visto o ensaio uma vez seria inverter a ordem do cuidado. O gancho é natural quando os prazos
  existirem.

## O que falta decidir — e não é técnico

Registrado aqui para não se perder:

- Quanto tempo guardar **lead não convertido** (dado de quem preencheu um formulário e nunca virou
  cliente — o caso mais claramente sujeito à LGPD).
- Quanto tempo guardar **documento** de cliente encerrado, considerando que contrato tem prazo
  prescricional próprio, que não é o mesmo de um material de discovery.
- Se há base legal para reter além do prazo (obrigação fiscal, defesa em processo) e como marcar
  esses casos.
- Se o titular pode pedir expurgo antecipado, e por qual caminho.

## Alternativas consideradas

- **Prazos default não-nulos.** Rejeitada: qualquer número que eu escolhesse seria um palpite com
  consequência jurídica, e a atualização do portal apagaria dado de quem não pediu nada.
- **Anonimizar em vez de apagar.** Boa opção para preservar indicadores históricos, e não descartada
  para o futuro — mas exige decidir campo a campo o que é identificador, e isso pertence à mesma
  conversa de negócio que ainda não aconteceu.
- **Expurgo pela interface.** Rejeitada por ora: operação destrutiva atrás de um clique, sem
  ensaio, é como se apaga o que não se queria.
