# ADRs

Cada ADR registra uma decisão difícil de reverter: contexto, decisão, consequências e status. Numere arquivos sequencialmente.

O campo Status usa um conjunto **fechado** de três valores, em pt-BR: `aceita`, `superada pela ADR NNNN` ou `superada em parte pela ADR NNNN`. Ele é sempre inline — `**Status:** <valor>` — e é a primeira linha não vazia depois do `# ADR NNNN — Título`; não há bullet nem `## Status` próprio. Sucessão se escreve no próprio status, com a referência à ADR que sucede; o motivo da sucessão, quando não cabe na frase, mora no corpo. `backend/tests/test_status_das_adrs.py` reprova o que sair disso.

O índice abaixo é **derivado**: cada entrada repete, palavra por palavra, o `#` do arquivo, sem o prefixo `ADR NNNN — `. Não anote, não encurte, não reescreva — o que o título precisa dizer, diga no `#` do arquivo, que é o único lugar onde ele vale. Relação com outra ADR tem campo próprio no cabeçalho (`**Revisa:**`, `**Completa:**`), e é lá que ela é registrada. `backend/tests/test_indice_de_adrs.py` reprova a divergência.

- 0001 — Django, React e PostgreSQL
- 0002 — Acesso privado
- 0003 — Webhook para o portal do cliente
- 0004 — Gestão de tarefas: espelho vs. sistema de registro externo
- 0005 — Alimentação do portal: reuniões, pendências e resultados
- 0006 — Motor de agentes de IA (especializados, RBAC, auditoria e avaliação)
- 0007 — Assinatura eletrônica: provedor homologado e webhook de status
- 0008 — Artefatos da jornada como entidade
- 0009 — Visibilidade por função e limites de requisição
- 0010 — Equipe do projeto como fronteira de acesso
- 0011 — Processo de produção e TLS na borda
- 0012 — Observabilidade: identidade de requisição, sondas e rastreamento de erro
- 0013 — Backup lógico em container próprio, com restauração exercitada no CI
- 0014 — Gate de carga por custo de query no CI, k6 como procedimento operado
- 0015 — Agendador de trabalho periódico na aplicação, com carimbo durável no banco
- 0016 — Autenticação com o Google sem chave de conta de serviço
- 0017 — Retenção de dado pessoal arquivado
- 0018 — Integração ligada por padrão quando configurada
- 0019 — Variante de blueprint como tabela, não como JSON
- 0020 — Case como fotografia: números persistidos, não recalculados
- 0021 — Registro financeiro não arquiva: a exceção declarada ao soft delete da casa
- 0022 — Recuperação do corpus interno neste repositório, com pgvector
- 0023 — Resposta ancorada: citar ou declarar a lacuna, e quem declara o regime é o modelo
- 0024 — Branco, preto e laranja, e a camada que faltava
- 0025 — A sidebar clara, e o matiz como única identificação
- 0026 — As telas passam a chamar o design system (e a guarda que impede a volta)
- 0027 — A regra do snapshot que só existia em prosa
- 0028 — O documento que não sobrevivia à revisão
- 0029 — A identidade que o Django não sabia apresentar
- 0030 — A operação sai do texto: o cockpit vira o sistema primário
- 0031 — O degrau sai sozinho, o texto da IA não
- 0032 — Só a declarada move número
- 0033 — A camada 5 não suspende sozinha
- 0034 — Só o fato sustenta número
- 0035 — Fontes da verdade e fronteiras operacionais
- 0036 — ClickUp como SoR de Delivery e aceitação separada do merge
- 0037 — Backbone event-driven, Outbox e idempotência
- 0038 — OpenTelemetry como padrão canônico e Grafana Cloud como backend inicial
- 0039 — LangGraph como runtime agentic e LangSmith para observabilidade/evals de IA
- 0040 — Pulse + GitHub + One sem ClickUp ou Make
- 0041 — Pulse Design System e validação visual
- 0042 — Trunk-based: `main` promove HML e tag da `main` promove produção
- 0043 — A marca Pulse no shell, e as fundações r2 finalmente consumidas
- 0044 — A infraestrutura do Pulse mora no repositório do outro produto
- 0045 — A camada global vem vendorizada e pinada, e o Project Context sai de baixo dela
- 0046 — A projeção de entrega GitHub lê, e não vira fonte da verdade
- 0047 — A linha do tempo da entrega: canônica sobre a configurável e histórico append-only
- 0048 — A escada FDE inteira vira degrau comercial, e duas chaves são renomeadas
- 0049 — A ontologia entra pela linguagem, antes do schema
- 0050 — O Engagement como espinha dorsal, e a origem comercial deixando de ser 1-1
