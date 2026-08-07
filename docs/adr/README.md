# ADRs

Cada ADR registra uma decisão difícil de reverter: contexto, decisão, consequências e status. Numere arquivos sequencialmente.

- 0001 — Django, React e PostgreSQL
- 0002 — Autenticação, autorização e documentos privados
- 0003 — Webhook para o portal do cliente
- 0004 — Gestão de tarefas: espelho vs. sistema de registro externo
- 0005 — Alimentação do portal: reuniões, pendências e resultados
- 0006 — Motor de agentes de IA (especializados, RBAC, auditoria e avaliação)
- 0007 — Assinatura eletrônica: provedor homologado e webhook de status
- 0008 — Artefatos da jornada como entidade (um modelo com `kind`, estado próprio)
- 0009 — Visibilidade por função e limites de requisição
- 0010 — Equipe do projeto como fronteira de acesso
- 0011 — Processo de produção e TLS na borda (gunicorn, checks de deploy, cofre de segredos)
- 0012 — Observabilidade: identidade de requisição, sondas e rastreamento de erro
- 0013 — Backup lógico em container próprio, com restauração exercitada no CI
- 0014 — Gate de carga por custo de query no CI, k6 como procedimento operado
- 0015 — Agendador de trabalho periódico na aplicação, com carimbo durável no banco
- 0016 — Autenticação com o Google sem chave de conta de serviço (ADC/Workload Identity ou OAuth)
- 0017 — Retenção de dado pessoal arquivado: mecanismo inerte, prazos a decidir
- 0018 — Integração ligada por padrão quando configurada (e nenhuma liga sem credencial)
- 0019 — Variante de blueprint como tabela, não como JSON (a constraint é o que decide)
- 0020 — Case como fotografia: números persistidos no congelamento, não recalculados
