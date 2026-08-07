# FDD 027 — Repositório de cases com métrica

> **Status: proposta.** Nada aqui está implementado. **Depende da FDD 026**: o "setor" do
> case é a `Vertical` proposta lá, e o KPI canônico vem do blueprint.

## Jornada

Projeto entregue hoje não vira nada. `Project.status` chega a `completed` e o conhecimento
comercial daquela entrega — o que melhorou, quanto, em que setor — fica espalhado entre o
ROI do projeto, os KPIs digitados em cada Funcionário Digital e a memória de quem entregou.
Quando o comercial precisa de prova, ele reconta de cabeça.

Um repositório de cases estruturados resolve isso: cada projeto concluído produz um registro
com **antes/depois, número e setor**, que alimenta a proposta gerada por IA e uma tela
interna de consulta. A matéria-prima já existe — é o argumento que torna a ideia atraente.

Mas ela vem com uma armadilha que precisa ser dita antes das regras, porque muda o custo:
**"o dado já existe, é só uma projeção" não se sustenta**. Não existe "antes":
`hours_saved_month` já é o *delta declarado*, não um par, e sem baseline capturado o "antes"
seria digitado retroativamente — que é exatamente o que destrói a credibilidade de prova
social. `kpi_value` é `CharField`, cabe `"80%"` ou `"de 3h para 20min"`, e não ordena nem
agrega. E o health nunca é persistido: `assess_project_health` é função pura sobre o estado
**atual**, de modo que um projeto concluído, recalculado meses depois, devolve outro número
— tarefas fecharam, pendências sumiram. Um case cujo número muda sozinho depois de publicado
é pior que nenhum case.

Por isso esta FDD não é "uma tela": é tipar o KPI, capturar baseline no começo e **congelar**
o resultado no fim.

## Regras

- **Tipar o KPI.** `DigitalEmployee` ganha `kpi_unit` (percentual, horas, minutos, moeda,
  contagem), `kpi_direction` (maior é melhor / menor é melhor), `kpi_baseline` e
  `kpi_current` (`Decimal`). `kpi_value` **permanece** — campo aditivo, sem quebra do
  contrato `/api/v1/` — e fica declarado como obsoleto em prosa, não removido. O blueprint da
  FDD 026 carrega `kpi_label`, `kpi_unit` e `kpi_direction` **canônicos**: é o que torna
  centenas de cases comparáveis entre si em vez de uma coleção de frases.
- **Baseline no início, não na hora do case.** O baseline é pedido quando o Funcionário
  Digital é instanciado a partir do blueprint — o mesmo momento em que a FDD 026 já abre um
  formulário. Baseline preenchido depois é memória, não medição.
- **Congelar na conclusão.** Quando `Project.status` passa a `completed`, nasce um `Case` em
  rascunho com os números **congelados**: o health calculado naquele instante e
  **persistido** no próprio case, o ROI do projeto, e o antes/depois de cada Funcionário
  Digital. O case não recalcula nada depois — é fotografia, não consulta.
- **Modelo `Case`.** FK `project`, `title`, `summary`, FK `vertical`, `metrics` (JSON, uma
  entrada por métrica com rótulo, unidade, antes, depois e direção), `health_snapshot`,
  `roi_snapshot`, `status`, `published_at`, o trio de consentimento (`client_consent`,
  `consent_recorded_at`, `consent_recorded_by`) e `anonymized`.
- **Estado no padrão que já existe.** `rascunho → em revisão → publicado`, com mapa de
  transições no molde de `ARTIFACT_TRANSITIONS`, e carimbo automático no `save()` como o
  `Artifact` já faz. A governança espelha o AI Score, que só cruza ao portal depois de
  `ai_score_reviewed`: **gerado como rascunho, publicado por decisão humana**.
- **Consentimento é condição de publicação, não observação.** Sem `client_consent`, o case
  não publica — nem anonimizado. `anonymized` permite publicar como "uma imobiliária de médio
  porte" quando há autorização de uso do resultado mas não da marca; são duas permissões
  diferentes e o modelo não pode confundi-las.
- **Superfície interna.** Tela `/cases` com filtro por vertical, área e blueprint; e
  `ai.build_opportunity_context` passa a injetar cases da mesma vertical, ao lado do nível de
  produto e dos blueprints. A proposta gerada deixa de prometer e passa a provar.
- **Superfície no portal do cliente.** Fica declarada aqui, com as restrições que a tornam
  possível — e **exige RFC antes de construir**, porque atravessa a fronteira de um serviço
  externo. O snapshot da ADR 0003 é **por projeto** e `portal.py` afirma que nenhum dado
  comercial é exposto: case de terceiro não cabe nele, pede rota própria. Só sai case
  **publicado com consentimento**; **nunca** o `roi_snapshot` financeiro, que é interno — ao
  cliente vai a métrica operacional do Funcionário Digital. E o isolamento por organização é
  invariante: do lado do portal ele é imposto pela RLS no banco (ADR 0010 de lá), e o
  documento deve apoiar-se nisso em vez de reinventar a guarda.
- **Acesso.** Recurso próprio no `RolePermission`, que nega por padrão: leitura para papéis
  internos, escrita e publicação só admin. Registrar consentimento é ato de admin, porque é
  ele que carrega a responsabilidade.

## Aceite

Ao concluir um projeto, o admin encontra em **Cases** um rascunho já preenchido: título,
vertical do cliente, o health e o ROI congelados na data da conclusão, e uma linha por
Funcionário Digital com o antes e o depois do KPI na unidade certa. Ele revisa o texto,
registra o consentimento do cliente e publica. Em **Comercial**, ao gerar uma proposta para
um cliente da mesma vertical, o texto cita o case publicado com o número real. Meses depois,
com tarefas e pendências daquele projeto já alteradas, o case continua exibindo exatamente
os mesmos números.

## Regressão crítica

Case sem `client_consent` não publica, por nenhum caminho — nem anonimizado. Os números
congelados não mudam quando o projeto muda depois: alterar tarefas, pendências ou valores do
projeto concluído não altera `health_snapshot`, `roi_snapshot` nem `metrics`. Case
anonimizado não expõe nome, razão social nem CNPJ em nenhuma serialização. O
`roi_snapshot` financeiro nunca aparece em resposta destinada ao cliente. E um projeto
concluído sem baseline registrado gera o case declarando a lacuna, em vez de inventar um
"antes" — ausência de base é informação, não zero.

## Fora deste recorte

**Vitrine pública no site.** É outra audiência, outro contrato de consentimento e outro
risco; provavelmente o destino natural da prova social, mas não se resolve junto.

**Versionamento e expiração de case.** Um número de dois anos atrás continua verdadeiro e
pode já não ser representativo — a diferença entre as duas coisas merece decisão própria.

**Consentimento com prazo de validade.** Conversa diretamente com a ADR 0017, que trata
retenção de dado pessoal arquivado; unir os dois assuntos agora atrasaria os dois.
