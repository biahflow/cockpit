# Design Approval Package — Meu perfil e edição de contato

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Pendente de aprovação**
Data: 2026-08-27
Produzido por: harness (Claude Code), sob `workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação.

## Por que existe um gate

Dois pedidos criam superfície perceptível que hoje não existe:

1. uma rota nova, `/perfil`, com edição de nome, envio de foto e troca de senha;
2. um campo novo no formulário de contato (`Sobrenome`) e uma ação que o painel não tem (`Editar`).

`workflows/design-approval.md` classifica como `INTERFACE_CHANGE` o que "cria ou altera
materialmente uma superfície perceptível por humano", e diz explicitamente que isso cobre os
estados de erro, vazio, carregamento e não autorizado — que são os descobertos tarde. Nenhuma
aprovação vigente cobre estas duas superfícies: o DAP GH-26 r1 aprovou marca e fundações no shell
e listou "as outras 20 telas de produto" como **não** aprovadas
(`docs/design/dap-gh26-r1/README.md`).

O gate fica **antes do planejamento**, não antes da construção. Por isso ele é pedido agora, com o
mapeamento de código já feito e nenhuma linha de implementação escrita.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| `board-desktop.png` | Captura congelada do board a 1280px, `deviceScaleFactor: 2`. |
| `board-mobile.png` | Captura congelada do board a 390px. |

As capturas são a evidência fixa do que foi renderizado: um board depende de fonte, navegador e
plataforma, e é ao PNG que a aprovação se refere. Elas retratam o **board**, não o produto — a
evidência renderizada da tela implementada é `BROWSER_REQUIRED` e vem depois, contra o código. O board cita, valor a valor, a origem de cada
cor, corpo, raio e sombra em `frontend/src/index.css`.

## O que está sendo pedido

Duas decisões separadas, porque aprovar visual não aprova copy:

1. **Visual** — a composição da revisão 1: dois cartões em `/perfil`, miniatura circular de 72px,
   barra de progresso de 4px, e o par lápis/lixeira na linha do contato.
2. **Copy** — as strings exatas listadas na seção 11 do board.

## Novo versus consumido

Só **dois** valores visuais são novos nesta revisão, e é isso que está em julgamento:

| Novo | Onde |
| --- | --- |
| Miniatura de foto circular de 72px, `object-fit: cover` | cartão "Foto e nome" |
| Barra de progresso de 4px, trilho `line`, preenchimento `brand-500` | envio da foto |

Todo o resto consome primitiva existente — `.panel`, `.field`, `.form-label`, `.form-grid`, `.btn`,
`.btn--secondary`, `.btn--secondary-danger`, `.alert--error`, `.alert--ok`, `.avatar`,
`.popover-item`, `.page-head`, `.eyebrow`. Nenhuma cor nova, nenhum corpo fora dos papéis
`display/title/body/label/meta`, nenhum raio fora do par 8px/12px das fundações r2.

Isso não é acaso: `CLAUDE.md` registra que toda classe do design system tem consumidor e que isso é
invariante, e `src/test/primitivas.test.ts` reprova o literal que já tem primitiva.

## Decisões registradas

| # | Decisão | Alternativa rejeitada |
| --- | --- | --- |
| 1 | Perfil em rota própria `/perfil` | Aba em Configurações — a rota é `admin`-only e excluiria vendas e entrega do próprio perfil |
| 2 | Dois cartões, dois botões de gravação | "Salvar" único — faria a troca de nome falhar por um campo de senha não pedido |
| 3 | E-mail somente leitura | E-mail editável — é a credencial de login; trocá-lo sem confirmação é sequestro de conta silencioso |
| 4 | Edição de contato reaproveita o formulário do painel | Modal dedicado — superfície nova para o mesmo trabalho |
| 5 | Sobrenome opcional | Obrigatório — travaria cadastro rápido e invalidaria contatos já existentes |
| 6 | Sem editor de recorte de imagem | Recorte/zoom — dependência desproporcional a um avatar de 32px |

As decisões 1, 5 e a estratégia de migração do nome foram escolhidas pelo solicitante nesta sessão,
antes do board ser desenhado.

## Explicitamente fora desta aprovação

Tema escuro; item de "Meu perfil" na sidebar; admin editar outro usuário pela tela Equipe; recorte
ou zoom de imagem; foto de outros usuários; "Esqueci minha senha" por e-mail; 2FA; expirar sessões
ativas após a troca de senha; foto em e-mail, documento gerado ou exportação; contato principal do
cliente; mesclar contatos duplicados; reverter a divisão do nome para campo único.

## Consequências que o board não decide, e que a implementação vai enfrentar

Registradas aqui porque afetam o custo, não o desenho:

- **A foto contraria o padrão de mídia privada vigente, e o solicitante já decidiu como resolver.**
  `backend/config/urls.py:5-8` documenta que `/media/` nunca é servido pelo Django em nenhum
  ambiente, porque documento é recurso privado (ADR 0002) e a única porta é a rota autenticada de
  download. Um avatar exibido em `<img>` no topbar de toda tela ou repete esse padrão ou abre uma
  exceção. **Decisão do solicitante nesta sessão: repetir o padrão** — a foto sai por
  `GET /api/v1/users/<id>/avatar/`, atrás de sessão e RBAC, como o download de documento. Isso
  mantém o padrão vigente intacto e **dispensa ADR nova**; em troca, a implementação precisa de
  `ETag`/`Last-Modified` na rota, senão o topbar refaz uma requisição autenticada por tela.
- **O RBAC hoje fecha `user` para vendas e entrega.** `permissions.py` não contempla o recurso
  `user` em nenhuma allowlist, então `UserViewSet` está fechado para os dois papéis, e não existe
  mecanismo de "editar o próprio registro" em lugar nenhum. Escrita de perfil próprio é caminho
  novo, e por tocar autorização merece revisão linha a linha.
- **`UserViewSet` é `ReadOnlyModelViewSet` e `/auth/me/` é GET-only.** Não há endpoint de troca de
  senha em lugar nenhum do backend.
- **Dividir `Contact.name` é mudança de contrato `/api/v1/`.** O campo é `required` no schema
  (`openapi.yaml:9608`). A migração de dados quebra no primeiro espaço, por decisão do solicitante.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se pede aprovar | **visual** e **copy** da revisão 1 das duas superfícies |
| Aprovado por | — |
| Data | — |
| Revisão aprovada | — |

Aprovação da revisão 1 não é aprovação de uma revisão posterior: um pacote materialmente alterado é
revisão nova e precisa do próprio registro.
