# NFR-004 — Security & Privacy

## Objetivo

Definir requisitos mínimos de segurança e privacidade para Pulse, One, BiahflowOS, integrações e agentes.

## Requisitos

- toda operação multitenant deve resolver e validar `tenant_id` antes de acessar dados;
- secrets nunca podem aparecer em prompts, logs, traces, eventos ou payloads de auditoria;
- dados pessoais e conteúdo do cliente devem ser minimizados em eventos e telemetria;
- logs/traces não devem carregar texto bruto de documentos, transcrições ou mensagens salvo decisão explícita e documentada;
- ferramentas de agente devem operar com menor privilégio e escopo explícito;
- ações com efeito externo de alto impacto exigem Human Gate quando definido pelo Agent Spec;
- webhooks devem ser autenticados e resistentes a replay quando o provedor permitir;
- integrações devem falhar fechadas quando autenticação/autorização não puder ser verificada;
- todo dado enviado a LLM externo deve respeitar classificação de dados e política do tenant;
- prompt injection e tool abuse devem fazer parte dos testes adversariais de agentes.

## Auditoria

Ações humanas, automações e agentes com efeito material devem registrar ator, causa, timestamp, correlação e resultado sem depender do backend de observabilidade.
