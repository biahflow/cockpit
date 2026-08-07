# ADR 0020 — Case como fotografia: números persistidos, não recalculados

- **Status:** aceita
- **Data:** 07/08/2026
- **Contexto:** FDD 027 (repositório de cases com métrica), FDD 026 (biblioteca de Funcionários
  Digitais), FDD 014 (AI Score, revisão humana antes de publicar), FDD 022 (custo de query como
  gate), ADR 0008 (artefato da jornada como entidade)

## Contexto

A FDD 027 quer que projeto concluído vire prova: antes/depois, número e setor, alimentando a
proposta gerada por IA e uma tela interna de consulta. O argumento que torna a ideia atraente é que
**a matéria-prima já existe** — health, ROI e KPIs de Funcionário Digital estão todos no banco.

Daí a pergunta de desenho: o case precisa ser um registro, ou basta uma **projeção** — uma view que
agrega, na hora da leitura, o que já está lá? A segunda opção é claramente mais barata: nenhum
modelo, nenhuma migração, nenhum estado para manter em sincronia, e nenhuma chance de o case
divergir do projeto que ele descreve.

Só que a premissa é falsa em três pontos, e todos foram verificados no código antes de decidir:

- **`assess_project_health` é função pura sobre o estado de agora** (`apps/core/health.py`). Ela
  conta entregas atrasadas, reuniões não realizadas e pendências abertas **hoje**. Um projeto
  encerrado com nota 68 é recalculado meses depois como 100, porque as tarefas foram fechadas e as
  pendências resolvidas na arrumação de fim de contrato. O número não está errado — ele responde a
  outra pergunta.
- **`Project.actual_value` e `Project.cost` continuam editáveis** depois da conclusão, e são a base
  do ROI. Um ajuste contábil de dezembro reescreveria o ROI de um case de julho.
- **Não existe "antes".** `DigitalEmployee.hours_saved_month` é o *delta declarado*, não um par. Sem
  baseline capturado, uma projeção teria de inventar o "antes" ou omiti-lo.

## Decisão

**O `Case` persiste os números.** `health_snapshot`, `roi_snapshot` e `metrics` são gravados uma vez,
no instante em que `Project.status` passa a `completed`, e nunca recalculados.

Três consequências deliberadas seguem daí:

- **O congelamento é estrutural, não convencional.** Os três campos são `read_only` no
  `CaseSerializer`: não há caminho de escrita pela API, em vez de haver um caminho que se combina não
  usar. Um `PATCH` que os traga no corpo é aceito com 200 e os ignora — e a regressão
  `test_case_congelado_nao_muda.py` prova o par: o texto revisado pelo humano muda, a fotografia não.
- **O gatilho é um signal, não um botão.** Um "Gerar case" clicado semanas depois congelaria um
  health que já mudou, o que reintroduziria o defeito inteiro por outra porta. A idempotência é por
  existência (`cases.freeze_if_completed`): projeto reaberto e reconcluído não produz um segundo
  case, e salvar qualquer campo de um projeto já concluído não produz nada.
- **Ausência de base é informação.** `kpi_baseline` é nulável e o case grava `has_baseline: false`
  em vez de `0`. Um "antes" igual a zero que ninguém mediu é pior que a lacuna admitida — é a lacuna
  disfarçada de medição.

**A governança espelha a do AI Score** (FDD 014): a máquina apura, o humano decide. O case nasce em
`draft`, percorre `draft → review → published` e só publica com `client_consent` registrado — por
uma ação com autor e carimbo, não por um campo que um `PATCH` liga.

## Consequências

- **Um recurso novo no contrato `/api/v1/`** (`cases`), aditivo, sem `create`: o único caminho de
  criação é a conclusão do projeto. Os quatro campos novos de `DigitalEmployee` e os dois de
  `DigitalEmployeeBlueprint` também são aditivos, e `kpi_value` fica **obsoleto em prosa, não
  removido** — ele ainda alimenta o painel do cliente pelo snapshot da ADR 0003.
- **Duplicação deliberada da fórmula do ROI.** `cases._roi_snapshot` repete a aritmética de
  `views._roi` em vez de importá-la. A de Indicadores é agregação viva e pode mudar de fórmula
  amanhã; a do case é fotografia e não pode mudar de significado depois de tirada. Importar também
  inverteria a direção do import (view → domínio) que o resto do pacote respeita.
- **Um custo de leitura que some.** A tela `/cases` não paga o preço que a FDD 022 mediu nos
  agregadores (`/clients/overview/` ia de 43 a 169 queries com o tamanho da base): o case já está
  gravado, e listar cem custa uma consulta. É o efeito colateral agradável de gravar em vez de
  agregar.
- **Um estado a mais para envelhecer.** Um número de dois anos atrás continua verdadeiro e pode já
  não ser representativo. É consequência aceita e nomeada: versionamento e expiração de case estão
  em "Fora deste recorte" da FDD 027, e a diferença entre "falso" e "velho" merece decisão própria.
- **A vertical do case é uma cópia da referência, não do nome.** `Case.vertical` é FK `SET_NULL`:
  renomear "Igrejas" para "Organizações religiosas" muda o rótulo em cases antigos. É o
  comportamento desejado — a taxonomia é vocabulário editável (FDD 026) —, e é diferente dos
  **números**, que são cópia de valor e não mudam.
