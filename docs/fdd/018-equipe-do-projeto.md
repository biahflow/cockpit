# FDD 018 — Equipe do projeto

## Jornada

A FDD 017 tirou da Entrega os documentos comerciais, mas deixou o resto do projeto aberto: a
pessoa via todos os projetos, todos os marcos, todas as reuniões, o risco e a saúde de cada
projeto da casa e o ROI de cada cliente. A ADR 0009 registrou isso como assimetria aceita e
pendente de RFC.

Esta entrega fecha o modelo — **Entrega vê apenas os projetos de que participa** — e, para
isso, cria a noção que faltava no domínio: **equipe do projeto**.

## Regras

- **`ProjectMember` é o critério.** Participar do projeto é o que dá acesso; ser dono de um
  marco ou de uma tarefa deixou de bastar. Um critério só, expresso uma vez
  (`Project.objects.visible_to`), do qual derivam viewsets, agregadores e permissão de objeto.
- **O dono é sempre membro**, por invariante. Transferir a titularidade não deixa o novo dono
  de fora do próprio projeto.
- **Só admin monta a equipe.** Vendas e Entrega leem a equipe dos projetos que enxergam.
- **O recorte alcança tudo que pende do projeto:** marcos, tarefas, reuniões, pendências,
  fases, entregáveis, funcionários digitais, artefatos e documentos. E também o que está em
  volta — clientes (só os que a pessoa atende), oportunidades ganhas (só as que viraram
  projeto dela), painel, risco, saúde e o agente de entrega.
- **A escrita acompanha a leitura.** Entrega cria e edita dentro dos seus projetos; não cria
  nem apaga projeto; não move um objeto próprio para projeto alheio. Sem isso a restrição de
  leitura seria contornável em uma requisição — criar uma tarefa em projeto alheio bastava
  para virar dono dela e ganhar acesso.
- **O painel não vira canal lateral.** Para Entrega, o funil comercial vem vazio: ele trazia o
  valor estimado de todas as oportunidades, inclusive as não-ganhas, que a lista de
  oportunidades já escondia dela.
- **Indicadores e recomendações seguem negados** à Entrega, agora com teste que trava o 403.

## Fora deste recorte

O snapshot do portal do cliente (`PortalProjectSnapshotView`) roda por service token, fora do
RBAC interno (ADR 0003), e não muda. O digest diário continua filtrando por `owner=user`, então
um membro que não é dono de nenhum item recebe digest vazio — não é vazamento, é consequência
a resolver quando o digest evoluir para membership.

> **Fechada.** O digest passou a somar as duas coisas: os itens próprios (agora recortados por
> `project_scope_q`) e os atrasados dos projetos de que a pessoa **participa** — ver FDD 010.
>
> **E o alvo das notificações fechou junto**, na sequência: `notify` ganhou `project=`, e quem não
> alcança o projeto é descartado antes de a linha ser gravada — o que derruba o espelho por e-mail
> no mesmo corte. Com isso **acaba o `owner=` como critério de acesso no repositório**: era o
> último resíduo para *alvo*, como o digest era para *filtro*. O predicado virou
> `models.can_access_project`, terceira forma da mesma pergunta ao lado de `visible_to` e
> `project_scope_q`, e `permissions._participates` passou a delegar a ele — o critério segue com
> uma expressão só.
>
> Vale registrar que a consequência acima descrevia só metade do problema. A outra metade era
> vazamento, e ninguém tinha reparado: como nada reatribui os itens quando alguém sai da equipe,
> quem foi removido continua `owner` das suas tarefas, e o digest — filtrando só por `owner` —
> seguia mandando título e vencimento de um projeto que `visible_to` já excluía. Alcançável
> também pelo Django admin, onde o combo de `owner` de `Milestone`/`Task` lista todo mundo sem
> filtrar por equipe. As duas metades fecham juntas.

## Aceite

Um admin abre um projeto e vê o painel **"Equipe do projeto"**, com quem participa e um
formulário para incluir alguém; sem equipe, o painel diz que o projeto está invisível para a
Entrega. Uma pessoa de Entrega recém-criada abre o portal e não vê projeto, cliente,
tarefa nem reunião — a tela de Projetos explica que ela ainda não participa de nenhum e a quem
pedir. O admin a inclui na equipe de um projeto: ela passa a ver aquele projeto e só ele, com
seus marcos, reuniões, documentos e artefatos. O painel dela não mostra pipeline. Perguntar ao
agente de entrega sobre riscos traz só o projeto dela. O admin a remove: o acesso some na hora.
Admin e Vendas não perdem nada.

## Regressão crítica

Quem não é da equipe recebe lista vazia e 404 no detalhe — inclusive nas ações de detalhe
(`risk`, `health`, assistente, resumo, avançar fase), que herdam o recorte pelo `get_object`.
Criar qualquer recurso em projeto alheio responde 403, e mover um objeto próprio para projeto
alheio também. Entrega não cria nem apaga projeto. `/risk/`, `/health/`, `/dashboard/` e
`/clients/overview/` não citam projeto alheio, e o agregado por cliente soma apenas os projetos
da pessoa. Adicionar ou remover membro é 403 para quem não é admin. Quem sai da equipe pode ser
readmitido. O backfill da migração 0025 preserva o acesso de quem era dono de projeto, marco ou
tarefa — inclusive de itens arquivados.
