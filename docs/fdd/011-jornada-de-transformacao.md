# FDD 011 — Jornada de Transformação (fases e entregáveis do projeto)

## Jornada

Etapa de **entrega** da jornada de consultoria (RFC 0002). Depois que a oportunidade vira
`Project`, a execução deixa de ser só marcos/tarefas livres e passa a ter uma **jornada
fásica e nomeável** — o modelo mental "Welcome → … → Optimize". Cada fase concluída
**desbloqueia** seus entregáveis, e equipe/cliente sempre sabem "onde estamos" (fase
ativa) e "o que vem depois" (próxima fase).

O vocabulário é **configurável**: as fases (`JourneyPhase`) e seus entregáveis
(`PhaseDeliverable`) são um template global editável (mesmo espírito do `PipelineStage`).
Cada projeto recebe uma **cópia por instância** (`ProjectPhase` + `ProjectDeliverable`),
para carregar seu próprio estado sem que editar o template reescreva o histórico.

## Regras

- **Materialização automática:** ao criar um `Project` (`post_save`, inclui a conversão de
  oportunidade), `journey.materialize_journey` copia o template para o projeto — 1ª fase
  `active`, demais `locked`, entregáveis `pending`. É **idempotente**; projetos antigos são
  materializados de forma **preguiçosa** na primeira leitura de `/project-phases/`.
- **Avanço manual e não-bloqueante:** `POST /projects/{id}/advance-phase/` conclui a fase
  ativa (`done` + `completed_at`) e ativa a próxima (`active` + `started_at`). Entregáveis
  pendentes **não** impedem o avanço — são progresso informativo (`3/5`). Papel:
  **delivery/admin** (vendas lê, não avança).
- **Entregáveis:** a equipe marca como `delivered` via `PATCH /project-deliverables/{id}/`
  (grava `delivered_at`); pode apontar para o `Document` real. `name`/`position` são
  read-only na instância (herdados do template).
- **Estado da fase:** `status`/`started_at`/`completed_at` são geridos pelo `advance-phase`
  (read-only na API); só `target_date` ("a prevista") é editável pela equipe.
- **Template (config):** `journey-phases` e `phase-deliverables` são **admin-only**
  (resource `journey`), como a configuração de pipeline.
- **Sem quebra de contrato:** nada muda em `convert-to-project`; a jornada é aditiva.

## Aceite

Um projeto novo já nasce com a jornada instanciada (1ª fase ativa). A tela do projeto
mostra o **tracker** de fases (concluída/atual/bloqueada), a barra de progresso, o bloco
"você está aqui → próxima" e o **checklist de entregáveis** da fase ativa. A equipe marca
entregáveis, define a previsão e avança de fase; ao concluir a última, aparece o estado
"jornada concluída". O admin edita fases/entregáveis em **Configurações → Jornada**.

## Regressão crítica

Materialização é idempotente (não duplica fases numa segunda chamada nem em novo save do
projeto); avançar além da última fase é gracioso (sem fase ativa, nada quebra); vendas
recebe **403** ao tentar `advance-phase` ou marcar entregável, mas **200** ao ler a
jornada; template continua acessível só a admin.
