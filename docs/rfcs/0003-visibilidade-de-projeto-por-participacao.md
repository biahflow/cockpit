# RFC 0003 — Visibilidade de projeto por participação

## Motivação

A ADR 0009 fechou o vazamento de documentos comerciais para a Entrega e registrou, como
consequência aceita, uma assimetria: a pessoa passou a ver apenas os **documentos** dos
projetos em que atua, mas continuava vendo **todos os projetos** e tudo o que pende deles —
marcos, tarefas, reuniões, pendências, fases, entregáveis, funcionários digitais e artefatos.
Mais: `/risk/`, `/health/`, `/dashboard/`, `/clients/overview/` e o agente de entrega
varriam a base inteira, então nome, diagnóstico, saúde e ROI de projeto alheio saíam por
caminhos que nem passam por queryset de viewset.

Esconder o arquivo e deixar o resto aberto não é um recorte, é meio recorte. Esta RFC fecha o
modelo: **quem é da Entrega vê apenas os projetos de que participa.**

É mudança transversal — toca dez viewsets, quatro agregadores, a política de RBAC e o
frontend — e muda a semântica de rotas existentes. Por isso RFC, e não só FDD.

## Alternativas consideradas

**A. Manter a assimetria.** Custo zero hoje, mas o vazamento continua aberto e cresce: cada
recurso novo pendurado em projeto nasce visível para todo mundo.

**B. Reusar `Project.owner` como critério.** Sem modelo novo. Mas `owner` é obrigatório e
`PROTECT`: não dá para tirar, só transferir. Como na conversão o dono é sempre quem converteu
— Vendas ou admin (`views.py`, `convert-to-project`) —, o critério ou não alcança ninguém da
Entrega, ou, se combinado com "dono de marco/tarefa", torna **impossível revogar** o acesso
de quem já é dono de alguma coisa. Também mantém duas expressões da mesma regra: a de Python
e a de SQL, que já haviam divergido.

**C. Modelo de equipe (`ProjectMember`) — escolhida.** Um critério explícito, revogável e
auditável, com um único ponto de verdade.

## Impacto

**No contrato `/api/v1/`.** Aditivo em forma: novas rotas `project-members`, novos schemas.
Mas **incompatível em semântica** para consumidores autenticados como Entrega: a mesma rota
passa a devolver menos linhas, e um `GET` de detalhe de projeto alheio passa de 200 para 404.
O RFC 0001 exige, nesse caso, "nova versão ou período de compatibilidade documentado".

Não abrimos `/api/v2/`: o único consumidor é o SPA deste repositório, versionado junto. O
`portal_cliente` consome o snapshot por service token (ADR 0003), que **não** passa pelo RBAC
interno e fica intocado. O período de compatibilidade é, na prática, o próprio deploy, e a
quebra está registrada no CHANGELOG sob "Alterado (incompatível)".

**Na operação.** Quando **Vendas** converte uma oportunidade, o projeto nasce sem equipe e é
invisível para a Entrega até um admin montá-la. É o custo direto de concentrar a gestão de
equipe no admin, e está no runbook.

**Em quem escreve.** Entrega perde `POST` e `DELETE` de projeto — projeto nasce da conversão
comercial ou pela mão do admin — e passa a criar marcos, tarefas, reuniões, pendências,
funcionários digitais e artefatos apenas dentro dos seus projetos.

## Segurança

A leitura só vale se a escrita fechar junto. Antes, `POST /milestones/` apontando para
qualquer projeto tornava a pessoa dona do item e, pelo critério antigo, "atuante" nele: a
restrição de leitura seria contornável em uma requisição. Fecham juntos:

- guarda de criação e de **mudança de vínculo** (mover um objeto próprio para projeto alheio);
- `has_object_permission` deixa de ter `return True` cego e passa a **negar por padrão**, para
  que um recurso novo nasça fechado;
- `risk`/`health` saem do atalho que liberava `GET` a qualquer autenticado antes de checar o
  papel;
- `/analytics/` e `/recommendations/` continuam negados à Entrega, agora com teste que trava
  esse 403 — os dois varrem a base inteira e não foram parametrizados.

## Plano de migração

`ProjectMember` entra em duas migrações: `0024` cria a tabela, `0025` faz o **backfill**,
traduzindo o critério antigo (dono do projeto, de um marco ou de uma tarefa) em participações.
Quem via um projeto na véspera do deploy continua vendo depois — a mudança de regra não vira
perda de acesso silenciosa.

O backfill é fiel, não mais rígido: inclui donos de itens **arquivados**, porque o critério
antigo também incluía. Apertar isso é decisão separada. Não inclui `Pendencia.owner`, que
nunca concedeu acesso.

Uma invariante mantém o estado consistente daqui pra frente: **o dono do projeto é sempre
membro ativo**, garantida por signal em vez de por uma linha na view, para valer também no
admin do Django e nas factories dos testes.

Depois do deploy, revisar as alocações: o backfill preserva o acesso, mas o acesso que existia
era largo demais — é justamente o que esta RFC corrige.
