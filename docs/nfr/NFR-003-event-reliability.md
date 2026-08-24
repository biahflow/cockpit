# NFR-003 — Event Reliability

**Status:** Active  
**Data:** 2026-08-24

## Objetivo

Eventos e automações do BiahflowOS devem sobreviver a retries, reinícios e falhas de provedores sem duplicar efeitos de negócio.

## Requisitos

- Publicação de evento de domínio usa Transactional Outbox.
- Entrega é tratada como `at least once`; consumidores são idempotentes.
- `event_id`, `correlation_id` e `schema_version` são obrigatórios nos eventos canônicos.
- `causation_id` é obrigatório quando um evento nasce como consequência direta de outro.
- Retries precisam de política e limite explícitos.
- Falhas permanentes devem ser inspecionáveis em DLQ/quarentena; descarte silencioso é proibido.
- Efeitos externos persistem idempotency key/provider reference quando suportado.
- Handlers não devem depender da ordem global de eventos; ordenação necessária deve ser definida por aggregate/partition ou protegida por versão de estado.
- Mudança incompatível de payload exige versionamento de contrato.
- Auditoria deve permitir reconstruir quem/qual evento causou um efeito relevante.

## Critério de aceite transversal

Reprocessar o mesmo evento não pode criar segundo projeto, segundo contrato, segunda cobrança, segunda mensagem crítica ou segunda aprovação.
