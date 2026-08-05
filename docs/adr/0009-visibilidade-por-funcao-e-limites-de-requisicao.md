# ADR 0009 — Visibilidade por função e limites de requisição

**Status:** aceito

## Contexto

A revisão de segurança do item de prontidão para produção (FDD 017) encontrou duas lacunas que
não são defeitos pontuais, e sim decisões que nunca tinham sido tomadas.

**A primeira é de autorização.** O RBAC é de duas camadas: `RolePermission` decide por
`resource` e alguns viewsets estreitam `get_queryset` por função. A ADR 0008 aplicou esse
estreitamento ao `Artifact` — Entrega não vê proposta nem contrato, porque carregam valor e
condição comercial. Só que o mesmo texto, quando alguém clica "Salvar como documento", vira um
`Document` ligado à oportunidade, e o `DocumentViewSet` nunca estreitou nada: Entrega listava e
baixava exatamente o que a ADR 0008 tinha acabado de esconder. A regra existia num recurso e não
no outro porque ninguém tinha decidido, para `Document`, qual era a regra.

**A segunda é de limite.** O DRF estava sem `DEFAULT_THROTTLE_CLASSES`. Havia escopo nomeado nas
quatro rotas públicas (intake, booking, tasksync, webhook de assinatura) — porque cada uma foi
construída com o seu — e nada no resto. O login era `AllowAny` sem teto: adivinhar senha era
questão de tempo de CPU. O snapshot do portal, autenticado por Bearer, era um oráculo para
descobrir `PORTAL_READ_TOKEN` por tentativa.

## Decisão

### Entrega vê o documento do projeto em que atua

Não existe modelo de equipe no domínio. A única expressão de "faz parte deste projeto" que o
schema oferece é a propriedade: `Project.owner`, `Milestone.owner`, `Task.owner`. Adotamos
essa — quem é dono do projeto ou de qualquer item de trabalho dele atua nele.

Consideramos duas alternativas mais frouxas:

- **"Tudo menos oportunidade"** — espelho literal do `ArtifactViewSet`, já que `Artifact` só tem
  duas pontas e "só projeto" ali significa "sem oportunidade". Mais simples e menos intrusivo, mas
  deixa Entrega vendo o documento de qualquer projeto e de qualquer cliente, inclusive de
  contas em que não trabalha.
- **Criar um modelo de equipe** (`ProjectMember`) e filtrar por ele. É o desenho certo a prazo,
  mas é uma mudança de modelagem, com migração e telas, dentro de uma entrega de segurança.

Escolhemos a regra restritiva sobre a modelagem que já existe. Quando `ProjectMember` aparecer,
`_acts_on_project` é o único ponto a mudar.

A escrita acompanha a leitura: Entrega não cria documento fora de um projeto em que atua, e não
cria artefato ligado a oportunidade. Sem isso, a pessoa gravaria um registro que desaparece da
própria lista no instante seguinte — e a segregação valeria só na leitura, que era exatamente o
furo do `Artifact`.

### Teto de requisições em toda a API

`AnonRateThrottle` + `UserRateThrottle` como padrão (a rede de baixo), mais escopos nomeados nas
portas que merecem limite próprio: `login`, `invitation_accept`, `portal_read`, além dos quatro
que já existiam. Todas as taxas vêm de variável de ambiente, para afrouxar em produção sem tocar
em código.

O limite é **por IP** para quem não está autenticado e **por usuário** para quem está. Limitar
login por username seria mais preciso contra força bruta dirigida, mas transforma o endpoint numa
arma de negação de serviço contra uma conta específica: basta errar a senha de alguém até travar.
Por IP, o custo do ataque cresce com a necessidade de rede.

## Consequências

Uma pessoa de Entrega deixa de ver documentos que via ontem — os de cliente, os de oportunidade e
os de projetos em que não atua. É uma quebra de expectativa deliberada, e é o ponto da mudança.

Fica uma **assimetria conhecida e aceita**: Entrega continua enxergando todos os projetos, mas só
os documentos dos seus. Estender "projetos em que atua" a `Project`/`Milestone`/`Task` muda o
modelo de acesso da área inteira e mexe em várias telas — é trabalho de RFC próprio, não desta
entrega. Enquanto isso, a tela de projeto mostra o projeto sem os arquivos, o que é estranho e
preferível ao vazamento.

Atrás de proxy, `AnonRateThrottle` chaveia pelo IP que chega ao Django. Sem `NUM_PROXIES`
configurado, todo o tráfego que passa por um mesmo proxy compartilha um balde e o limite por IP
vira um limite global — no compose de desenvolvimento é exatamente o que acontece, porque o SPA
fala com a API pelo container do Vite. A variável existe para corrigir isso em produção; os
defaults foram escolhidos folgados o bastante para não estorvar uso legítimo mesmo agrupado.

O contador de throttle vive no cache. Com `LocMemCache` ele é por processo: com vários workers, o
limite efetivo é o configurado multiplicado pelo número de processos. Um cache compartilhado
(Redis) resolve, e entra junto do item de infraestrutura do roadmap.
