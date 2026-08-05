# FDD 003 — Execução e documentos

## Jornada

Entrega organiza marcos e tarefas, atribui responsáveis e prazos, e anexa documentos ao cliente, oportunidade ou projeto.

## Regras

- Um marco ou tarefa aberto com prazo anterior à data atual é exibido como atrasado.
- Arquivos são privados e só podem ser acessados por usuários autorizados ao recurso associado.
  A única porta é `documents/<id>/download/`; nenhum ambiente serve `MEDIA_ROOT` (FDD 017).
- **Entrega vê o documento do projeto em que atua** — ser dono do projeto ou de um marco/tarefa
  dele. Documentos de cliente e de oportunidade ficam fora do alcance da área (FDD 017, ADR 0009).
- O upload aceita só os tipos de `ALLOWED_DOCUMENT_EXTENSIONS` e o nome do arquivo é sanitizado
  antes de gravar, porque ele segue para o Drive, para o fornecedor de assinatura e para o portal.

## Aceite

O painel exibe próximos vencimentos e atrasos; tentativas de download sem permissão retornam acesso negado.

## Regressão crítica

Tarefas concluídas deixam de estar atrasadas; reabertura limpa a conclusão. Documentos sem vínculo, com mais de um vínculo, acima de 10 MB ou de tipo fora da allowlist são rejeitados. Entrega não lista nem baixa documento de oportunidade ou de projeto alheio.
