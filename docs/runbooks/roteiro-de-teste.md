# Runbook — roteiro de teste do portal

Percurso manual de ponta a ponta, para quem quer **usar** o portal e confirmar que ele funciona:
cliente → contato → oportunidade → conversão → projeto → equipe → indicadores. Cada passo diz o que
fazer, em que tela, e **o que deve acontecer** — se o "deve acontecer" não acontecer, é defeito.

Este documento é sobre o produto. O que **ligar** (IA, Drive, Calendário, Assinatura, Sincronia) e
em que ordem está em [`../operacao.md`](../operacao.md); como **subir**, no [`README.md`](../../README.md).

## Antes de começar

```bash
docker compose up -d
docker compose ps          # api, db, web, mailpit e minio devem estar Up
curl -s localhost:19000/readyz
```

`readyz` deve devolver `{"status": "ok", "checks": {"db": "ok", "cache": "ok"}}`. Se der 503, o
banco ou o cache não subiram e não adianta seguir.

| Onde | URL |
| --- | --- |
| App | <http://localhost:19173> |
| API / documentação | <http://localhost:19000/api/v1/> · <http://localhost:19000/api/docs/> |
| Caixa de e-mail (Mailpit) | <http://localhost:19025> |

### Crie o primeiro admin — e corrija o papel dele

```bash
docker compose exec api uv run python manage.py createsuperuser
```

**`createsuperuser` não cria um administrador do portal.** `User.role` tem default `delivery`
(`apps/core/models.py`), e o menu do SPA é filtrado só pelo `role`
(`frontend/src/components/Layout.tsx`) — o `is_superuser`, que a API respeita, o menu ignora. Entrar
assim mostra um portal capado, sem **Leads**, **Indicadores**, **Jornada**, **Equipe** e
**Configurações**. E como **Equipe** é justamente a tela que arrumaria o papel, o conserto é por
linha de comando:

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import User; User.objects.filter(username='SEU_USUARIO').update(role='admin')"
```

Se você já estava logado, saia e entre de novo — o papel vem no login.

### O que está desligado de propósito

IA, Google Drive, Calendário, Assinatura eletrônica e Sincronia de tarefas nascem atrás de flag.
**Desligados, os botões não aparecem** e as ações respondem 503. Ausência não é defeito: confira a
tabela de estado em [`../operacao.md`](../operacao.md) antes de abrir um chamado. Notificações
in-app (o sino) e o e-mail do Mailpit funcionam sem configurar nada.

## 1. Entrar

1. Abra <http://localhost:19173>. Sem sessão, cai na tela de login.
2. Entre com o admin criado acima.

**Deve acontecer:** o menu lateral traz as dez entradas (Visão geral, Comercial, Leads, Clientes,
Projetos, Documentos, Indicadores, Jornada, Equipe, Configurações) e o canto superior direito mostra
seu nome com o papel **Administrador**. A sessão é cookie + CSRF: recarregar a página mantém você
dentro; **Sair** derruba.

## 2. Cadastrar um cliente

Em **Clientes** (`/clientes`), no cartão "Novo cliente": preencha *Nome do cliente* (razão social e
CNPJ são opcionais), deixe *Situação* no default **Prospect** e clique em **Cadastrar cliente**.

**Deve acontecer:** o cliente aparece na "Base de clientes" à direita, marcado como **Prospect** e
com "Sem jornada ativa", e a aba **Prospects** deixa de estar vazia. Clicar nele abre
`/clientes/<id>`.

A situação é sua declaração no cadastro — use "Cliente ativo" para quem já fechou (uma base
importada, por exemplo) —, e dá para corrigi-la depois em "Dados do cliente". Daí em diante quem
manda é o sistema: ganhar uma oportunidade (passo 6) promove o cliente a **Ativo**, e a partir daí
voltar para prospect é recusado. A conversão de lead (passo 11) também cria o cliente como prospect.

## 3. Adicionar um contato

No detalhe do cliente, painel **Contatos** → preencha e clique em **Adicionar contato**.

**Deve acontecer:** o contador do painel sobe ("1 contato") e o contato passa a ser selecionável no
detalhe da oportunidade (passo 5).

## 4. Criar uma oportunidade

Em **Comercial** (`/comercial`) → **Nova oportunidade**. Preencha Título, Cliente, **Nível de
produto**, Valor estimado e Previsão de fechamento → **Adicionar ao pipeline**.

O seletor de nível traz os três produtos semeados por migração — Discovery Express, Discovery +
Assessment e Implantação. "Sem nível definido" é permitido, mas **escolha um**: é o nível que decide
o template de kickoff no passo 6. Nome, preço e escopo de cada um se editam em
**Indicadores → Gerir serviços** (`/servicos`).

**Deve acontecer:** um card na primeira coluna do pipeline, com o valor formatado em reais e uma
etiqueta colorida do nível de produto. O total da coluna, no cabeçalho, soma o card.

## 5. Andar no pipeline

1. **Arraste** o card para a coluna seguinte. O quadro é drag-and-drop.
2. Clique no card para abrir o detalhe: dá para editar título, escopo, valor, previsão, contato,
   etapa e nível de produto, e anexar documento.
3. Leve a oportunidade até a coluna **Ganha**.

**Deve acontecer:** o card muda de coluna e os totais das duas colunas se recalculam. Ao soltar na
coluna Ganha, surge no card o botão **"Criar projeto"** (no detalhe, o equivalente é **"Converter em
projeto"**). Em qualquer outra etapa esse botão não existe — conversão só de oportunidade ganha.

## 6. Converter em projeto

Clique em **Criar projeto**, informe *Início* e *Prazo final* e confirme.

**Deve acontecer** — quatro efeitos, e vale conferir os quatro:

1. O projeto nasce em **Projetos** (`/projetos`), com o cliente e o nível de produto herdados da
   oportunidade.
2. **Marcos e tarefas já vêm criados**, a partir do template do nível de produto, com os prazos
   espremidos dentro da janela que você informou (`apps/core/kickoff.py`).
3. Um **e-mail de kickoff** chega no Mailpit (<http://localhost:19025>) — desde que o seu usuário
   tenha e-mail cadastrado, já que ele é o destinatário. Este e-mail não depende de
   `EMAIL_NOTIFICATIONS_ENABLED`.
4. O **sino** de notificações mostra "Projeto … criado a partir da oportunidade ganha".
5. Um **aviso verde** aparece no topo do Comercial, com link "Abrir projeto", e o card da
   oportunidade passa a oferecer **"Ver projeto"** no lugar de "Criar projeto".

**Teste a trava:** o card não oferece mais converter, e é por isso — uma oportunidade ganha converte
exatamente uma vez. Pela API, um segundo `POST` em `convert-to-project` responde 409 ("A
oportunidade já foi convertida"), e nenhum cliente é duplicado no caminho.

## 7. Trabalhar o projeto

Em `/projetos/<id>`, exercite cada painel:

- **Equipe do projeto** — traz **uma** pessoa: quem converteu a oportunidade. É invariante ("quem
  responde pelo projeto participa dele"), não configuração. Guarde este fato para o passo 10.
- **Marcos** → "Adicionar marco"; **Tarefas** → "Nova tarefa", que pode ser pendurada num marco do
  mesmo projeto. Clique no círculo para concluir e **clique de novo para reabrir** — nada aqui é de
  mão única. O estado "Em andamento" existe, mas só chega pela sincronia com Linear/GitHub.
- **Reuniões** — registre uma. São **dois links**, para dois momentos: *Link da reunião* é a sala de
  quem ainda vai acontecer; *Link da gravação* é o registro do que aconteceu. Clique no selo
  **Agendada** para virar **Realizada**, e vice-versa.
- **Pendências** — registre uma, resolva e reabra, como nos marcos.
- **Jornada de Transformação** — a barra mostra "x de N fases concluídas"; **Concluir fase** avança.
- **Documentos** — envie um arquivo pelo painel do projeto.

**Deve acontecer:** tudo é salvo na hora e o cabeçalho passa a mostrar **Saúde do projeto**. Excluir
um item **arquiva** (soft delete): ele some da tela, mas o dado não é destruído.

## 8. Documentos

Há **três lugares** que enviam documento, e cada um já grava o vínculo: o detalhe da oportunidade
(passo 5), o painel de documentos do projeto (passo 7) e a própria tela **Documentos**
(`/documentos`), onde você escolhe o vínculo à mão em *Vincular a*.

Um documento pertence a **exatamente um** de três donos — a regra é do modelo (`Document.clean()`),
não da tela —, e a escolha decide quem enxerga o arquivo e por quanto tempo ele importa:

| Vínculo | Use para | Consequência |
| --- | --- | --- |
| **Cliente** | o que vale para a conta toda: NDA, contrato guarda-chuva, dados cadastrais | acompanha o cliente independentemente de negociação ou projeto |
| **Oportunidade** | material da negociação: proposta, escopo, apresentação comercial | vive no ciclo comercial; se a oportunidade não for ganha, o arquivo fica com ela |
| **Projeto** | material de entrega: ata, relatório, artefato de discovery | é o único que a equipe de **Entrega** enxerga e o único que chega ao portal do cliente |

Envie um de cada e confira que os três aparecem em `/documentos` com o vínculo certo.

**Deve acontecer:** nenhum documento aponta para dois donos nem para nenhum. Baixar um arquivo exige
sessão autorizada — quem não tem acesso ao dono do documento não baixa.

## 9. Indicadores e visão geral

- **Indicadores** (`/indicadores`): o funil por etapa e por nível de produto já reflete a
  oportunidade criada, e o projeto entra no valor fechado.
- **Visão geral** (`/`): "Pipeline estimado" e "Projetos ativos" saem do zero, o "Pipeline
  comercial" mostra a distribuição por etapa e "Próximas entregas" lista as tarefas do passo 7.
- **Detalhe do cliente** (`/clientes/<id>`): agora com saúde da relação, risco de atraso, ROI
  acumulado e a próxima reunião, se você registrou uma.

**Deve acontecer:** nenhum número contradiz o que você criou. Um valor "—" significa base
insuficiente para o cálculo, não erro.

## 10. Papéis e visibilidade — o passo que mais pega

É aqui que mora a regra mais fácil de interpretar como bug (RFC 0003, ADR 0010, FDD 018).

1. Em **Equipe** (`/equipe`) → "Convidar pessoa": e-mail qualquer, função **Entrega** → enviar.
2. Abra o **Mailpit** (<http://localhost:19025>): o convite traz um link pronto para
   `/aceitar-convite?token=…` (o token também pode ser colado à mão na tela). Defina usuário e
   senha. O convite vale 7 dias.
3. Saia e entre com essa pessoa.

**Deve acontecer:**

- O menu encolhe: a Entrega **não vê** Leads, Indicadores, Jornada, Equipe nem Configurações.
- **Projetos está vazio** — inclusive o projeto do passo 6. Não é defeito: o projeto nasce com
  **só quem converteu** (Vendas ou Admin, por invariante), então ninguém da Entrega participa dele
  ainda — e quem é da Entrega só enxerga projeto de que **participa**. Ser dono de um marco ou de
  uma tarefa não basta.
- Volte como admin, adicione essa pessoa em **Equipe do projeto**, e entre de novo como ela: o
  projeto aparece, com marcos, tarefas, reuniões, pendências e documentos.
- Remova-a da equipe: o acesso cai na hora.

Se alguém disser que "o projeto sumiu", é quase sempre isto.

## 11. Leads pelo site (opcional)

Não precisa do site no ar. Ponha um token no `.env` e aplique-o:

```bash
# .env
LEAD_INTAKE_TOKEN=um-token-forte-qualquer
```

```bash
docker compose up -d api    # mudança no .env só vale depois de recriar o container

curl -s -X POST localhost:19000/api/v1/leads/intake/ \
  -H "Content-Type: application/json" \
  -H "X-Intake-Token: um-token-forte-qualquer" \
  -d '{"name":"Fulano de Tal","email":"fulano@exemplo.test","company":"Exemplo S.A.","message":"Quero conhecer o Discovery."}'
```

**Deve acontecer:** resposta 201, o lead aparece em **Leads** (`/leads`) e o botão **Converter em
oportunidade** cria a oportunidade — que entra no pipeline do passo 4. Com o token vazio ou errado o
intake recusa, e é assim que deve ser.

## Quando algo não funcionar

- A tela mostra um **código da ocorrência** — é o `X-Request-ID`, e ele está no log:
  `docker compose logs api | grep <código>`.
- **Mudou o `.env` e nada aconteceu?** O container precisa ser recriado: `docker compose up -d api`.
- **A tela do Vite acusa `Failed to resolve import "<pacote>"`?** O `node_modules` do container é um
  volume anônimo que **mascara** o da imagem; ele não é refeito quando o `package.json` ganha uma
  dependência nova, e o container fica com o conjunto antigo. Renove o volume:
  `docker compose up -d --build --renew-anon-volumes web`. Só dependências são descartadas.
- **A API morreu depois de uma edição?** O `runserver` recarrega a cada arquivo salvo e morre se
  pegar o código num estado intermediário. `docker compose logs api --tail 30` mostra o traceback e
  `docker compose up -d api` levanta de novo.
- **Entrou e o menu está pela metade?** Seu usuário está com papel `delivery`. Veja "Crie o primeiro
  admin", no início deste roteiro.
- Alertas, sondas e diagnóstico mais fundo: [`monitoramento.md`](monitoramento.md).
