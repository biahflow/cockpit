# RFC 0001 — Contrato e segurança da plataforma

## Proposta

Versionar rotas sob `/api/v1/`, autenticar usuários por sessão e aplicar permissão de objeto na API. O OpenAPI publicado é o contrato consumido pela interface.

## Compatibilidade

Campos obrigatórios novos, remoção ou mudança de semântica exigem nova versão ou período de compatibilidade documentado.

## Segurança

Credenciais ficam somente em variáveis de ambiente; uploads são privados e os testes devem cobrir tentativa de acesso entre usuários e funções.

