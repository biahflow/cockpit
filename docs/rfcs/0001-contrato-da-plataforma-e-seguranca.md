# RFC 0001 — Contrato e segurança da plataforma

## Proposta

Versionar rotas sob `/api/v1/`, autenticar usuários por sessão e aplicar permissão de objeto na API. O OpenAPI publicado é o contrato consumido pela interface.

## Compatibilidade

Campos obrigatórios novos, remoção ou mudança de semântica exigem nova versão ou período de compatibilidade documentado.

## Segurança

Credenciais ficam somente em variáveis de ambiente; uploads são privados e os testes devem cobrir tentativa de acesso entre usuários e funções.

O arquivo de um documento sai por uma única porta autenticada (`/api/v1/documents/<id>/download/`) — nenhum ambiente serve `MEDIA_ROOT`. A visibilidade por função é aplicada nas duas camadas do RBAC (queryset e permissão de objeto), não só na leitura. Toda a API tem teto de requisições: `anon`/`user` como padrão e escopo nomeado nas portas de autenticação e nas rotas públicas. Ver FDD 017 e ADR 0009.

