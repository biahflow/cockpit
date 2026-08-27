# FDD 043 — Perfil do próprio usuário

> GitHub Issue [#56](https://github.com/biahflow/pulse/issues/56). Superfície:
> `INTERFACE_CHANGE`, aprovada em `docs/design/dap-perfil-e-contato-r1/` (revisão 1).
> Browser: `BROWSER_REQUIRED` — a tela é nova e entra na matriz de a11y da FDD 022.
> Merge do PR ≠ Done operacional.

## Jornada

Quem usa o Pulse não tinha como mudar nada sobre si. O popover do usuário mostrava nome e e-mail
como texto morto e oferecia só "Sair": trocar a própria senha exigia um administrador no Django
admin, e nome errado no cadastro ficava errado para sempre — aparecendo em todo lugar que lê
`first_name`.

Agora existe `/perfil`, alcançada pelo popover, onde o usuário da sessão edita o próprio nome,
troca a própria senha e envia ou remove a própria foto.

## O que esta fatia entrega

- **Nome e sobrenome** do próprio usuário, por `PATCH /auth/me/`.
- **Troca de senha** com a senha atual, por `POST /auth/me/password/`.
- **Foto**: envio e remoção por `PUT`/`DELETE /auth/me/avatar/`, leitura por
  `GET /users/<id>/avatar/`.
- O `.avatar` do topbar passa a mostrar a foto quando houver, e segue nas iniciais quando não.

## Regras

### A foto é recurso privado, como o documento

`config/urls.py` documenta que `/media/` **não é servido pelo Django em nenhum ambiente**, porque
documento é recurso privado (ADR 0002) e a única porta é a rota autenticada de download. A foto
repete esse padrão em vez de abrir exceção: sai por `GET /users/<id>/avatar/`, atrás de sessão.
Nenhuma URL pública, nenhuma URL assinada — decisão do solicitante, registrada no DAP.

A rota responde `ETag` e `Last-Modified` e devolve `304` na revalidação. Sem isso o topbar
dispararia uma requisição autenticada por tela, já que a foto aparece em todas.

Foto de outra pessoa responde **404, não 403**: quem não a alcança também não precisa saber que
aquele usuário existe. Admin alcança a de quem já lista.

### Escrita de perfil não é escrita de usuário

`UserSerializer` tem `role` gravável — e sempre teve, sem consequência, porque nenhum endpoint de
escrita o usava. Abrir o perfil muda isso: reusá-lo aqui transformaria o `PATCH` num caminho de
auto-promoção a admin.

Por isso a escrita de perfil usa um serializer **separado**, `ProfileSerializer`, com allowlist de
dois campos — `first_name` e `last_name`. `role`, `is_admin`, `is_superuser`, `is_staff`,
`is_active`, `username`, `email` e `id` não sobem por ele.

As rotas de escrita operam **sempre sobre `request.user`** e não aceitam id de alvo. Não existe
caminho para alterar outra pessoa.

`RolePermission` **não foi afrouxada**: o recurso `user` segue fora de toda allowlist, e `/users/`
continua fechado para Vendas e Entrega. O perfil é rota própria com `IsAuthenticated`, no mesmo
estilo de `MeView`.

### A troca de senha derruba as outras sessões, de propósito

O Django rotaciona o hash de sessão ao trocar a senha, o que invalidaria **todas** as sessões,
inclusive a corrente. `update_session_auth_hash` preserva a corrente; as outras caem, e isso é o
comportamento seguro — trocar a senha é o que se faz quando se suspeita de acesso alheio.

A senha atual é obrigatória, e a regra de força é a **mesma** do convite (`validate_password` com
os validadores do projeto), não uma segunda definição. `POST /auth/me/password/` tem escopo de
throttle próprio: quem tem a sessão mas não a senha — cookie vazado, estação destravada — não pode
adivinhar sob o teto genérico.

### O arquivo enviado é conferido pelos bytes, não pela extensão

A foto volta a ser servida **sob a origem do portal**, então um `.png` que na verdade é HTML seria
XSS armazenada. O upload é recusado antes de gravar quando os bytes de assinatura não batem com a
extensão. A resposta declara o `Content-Type` do nosso mapa — nunca o que o cliente informou — e
leva `X-Content-Type-Options: nosniff`.

O nome do arquivo enviado é descartado: o storage grava sob um nome gerado, então entrada do
usuário não entra em caminho de arquivo.

Limite de 2 MB e três tipos (JPG, PNG, WebP), validados **no servidor**; o `accept` do input é
afordância de tela, não controle. Trocar a foto apaga a anterior, em ordem gravar-depois-apagar,
para nunca deixar linha apontando para arquivo inexistente.

## Aceite

Os três papéis alcançam `/perfil` e editam a si mesmos. Nenhum altera outro usuário por rota
nenhuma. `delivery` mandando `role: "admin"` no PATCH continua `delivery`, no banco e na resposta.
Senha atual errada recusa e não altera nada; senha nova fraca é recusada com a regra do convite;
senha trocada com sucesso mantém a sessão corrente válida. Foto acima de 2 MB, de tipo não aceito
ou com bytes que não batem com a extensão é recusada. A rota da foto nega sem sessão, esconde a
foto alheia com 404 e devolve 304 quando o `ETag` bate. `/users/` segue fechado para Vendas e
Entrega.

## Regressão crítica

Reusar `UserSerializer` na escrita do perfil reabre a auto-promoção a admin — é o que
`test_entrega_mandando_role_admin_nao_vira_admin` guarda, afirmando banco **e** payload. Remover o
`update_session_auth_hash` desloga quem acabou de trocar a senha. Servir a foto sem o corte por
alvo expõe a foto de qualquer usuário a qualquer sessão. Afrouxar `RolePermission` para o recurso
`user` abre `/users/` para papéis que nunca o tiveram.

## Contrato

Rotas aditivas em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `PATCH /auth/me/` | o próprio usuário da sessão |
| `POST /auth/me/password/` | o próprio usuário da sessão |
| `PUT`/`DELETE /auth/me/avatar/` | o próprio usuário da sessão |
| `GET /users/<id>/avatar/` | o próprio; admin alcança a de quem lista |

`GET /auth/me/` ganha `has_avatar` e `avatar_updated_at`, ambos somente-leitura. Nenhum campo
existente muda de forma ou de significado.

## Fora desta fatia

Item de "Meu perfil" na sidebar; admin editar outro usuário pela tela Equipe; recorte ou zoom da
imagem; "Esqueci minha senha" por e-mail; 2FA; edição de e-mail ou de `username`; foto em e-mail,
documento gerado ou exportação; comando de limpeza de avatares órfãos deixados por falha de
storage.
