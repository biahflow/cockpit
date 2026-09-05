# Vertical Engenharia/Topografia — knowledge base

> **Espelho** da ficha canônica no Notion: **Engenharia — Vertical Knowledge Base**
> <https://app.notion.com/p/3ca82225ad27818b9c45f5d5ce24df13>
> Não se edita aqui. Trazido pela **ADR 0069**, que decidiu levar o método das verticais ao corpus
> da FDD 029. **A intel de conta não atravessa**; esta vertical não tem nenhuma conta ativa.
> As perguntas que valem para qualquer vertical estão em [`discovery-questions.md`](../discovery-questions.md).

**A vertical ainda não teve engagement real.** Nenhum número desta página foi medido em campo — o que
existe é o blueprint e um mapa AS-IS que é **hipótese a validar**, inclusive as raias e os quatro
loops de retrabalho.

- **Processo-alvo candidato:** croqui de campo → DXF confiável. É o elo 1→4 da cadeia, não a cadeia
  inteira — e continua **candidato**: pontuar os concorrentes na matriz é trabalho do Discovery, com
  o decisor na mesa. Escolher sem concorrentes declarados é escolher no escuro.
- **Dois perfis de interlocutor, e são conversas diferentes:** responsável técnico de escritório de
  topografia/projeto (decide sozinho) e gestor de secretaria de obras (decisão passa por procuradoria
  e licitação).

> **DESCONHECIDO — o Design Partner com órgão público não está resolvido.** Serviço concedido a
> prefeitura esbarra em regra de contratação, e a Lei 14.133/2021 trata da cessão de direitos sobre o
> desenvolvido. **HIPÓTESE:** o primeiro Design Partner desta vertical deve ser um **escritório
> privado** que atende o poder público, com a prefeitura entrando como cenário e não como parte.
> Fechar com apoio jurídico **antes** de oferecer.

## Onde a Feasibility entra nesta vertical

O Decision Gate T.O.E. acontece em 100% dos casos, sai no readout do Discovery e não é cobrado. A
**Technical Feasibility vendida** só entra quando responder ao gate exigir **medição**.

**Nesta vertical ela quase certamente dispara** — HIPÓTESE forte. A pergunta do gate é *"a geometria
sai do croqui de campo como ele é feito hoje?"*, e isso não se responde em reunião: exige uma amostra
real de croquis classificada um a um. Entre no Discovery já dizendo que a Feasibility é provável, com
preço e prazo na mesa.

## Glossário mínimo

O interlocutor é técnico; errar vocabulário custa autoridade nos primeiros cinco minutos.

| Termo | O que é | Por que importa |
| --- | --- | --- |
| **Croqui** | Desenho de campo à mão, fora de escala, com cotas e amarrações | É o input da cadeia inteira. A qualidade dele define o teto de tudo que vem depois |
| **DXF / DWG** | Formatos de intercâmbio CAD; DXF é aberto, DWG é nativo do AutoCAD | "Entregar DXF" é o elo 4. **DXF útil ≠ DXF que abre** |
| **Poligonal** | Sequência fechada de vértices e distâncias | Polígono que não fecha é o erro de input mais comum e mais barato de detectar em campo |
| **Amarração / ponto de controle** | Referência conhecida a que o levantamento se prende | Sem amarração, geometria bonita continua não sendo georreferenciada |
| **Memorial descritivo** | Texto que descreve objeto, limites, rumos e confrontações | Entregável; candidato a geração assistida depois que a geometria existe |
| **Quantitativo** | Quantidades por serviço extraídas do projeto | Elo 5. Erro aqui vira aditivo na obra, não erro de desenho |
| **Planilha orçamentária** | Quantitativo × composição de custo, com BDI | Elo 6. É onde o orçamento reprovado gera o loop 3 |
| **SINAPI** | Base nacional de custos e composições da construção civil | Em obra pública o preço costuma ser obrigado a referenciar base oficial |
| **As-built** | Desenho do que foi executado, contra o projetado | Fecha o loop 4 e alimenta a medição |
| **Boletim de medição** | Atesta quanto de cada serviço foi executado no período | Base do pagamento. Divergência vira aditivo ou glosa |
| **RRT / ART** | Responsabilidade técnica (CAU / CREA) | Existe **uma pessoa física** que responde pelo desenho. Nenhum sistema assume isso — diga essa frase |
| **Aditivo** | Alteração contratual de quantidade, prazo ou escopo | Em obra pública tem limite e desgaste político. É dor com nome e dono |

## Áreas de pressão — checklist de qualificação

| Área | Pergunta de sondagem | O que você está caçando |
| --- | --- | --- |
| Volume e fila | Quantos levantamentos entram por mês? Quantos estão parados hoje? | Se há fila, o ganho é throughput. Sem fila, economizar minutos não paga nada |
| Segunda visita a campo | Dos levantamentos do trimestre, quantos exigiram voltar? Sabem o número ou é impressão? | A hipótese de valor mais barata de testar |
| Tempo do projetista | Do croqui à prancha, quanto leva um projetista experiente? E um caso complicado? | O comparativo honesto. Se já são 10 minutos, talvez a resposta certa seja não automatizar |
| Espera × execução | Entre o técnico sair de campo e o projetista começar, quantos dias passam? | Lead time é espera, e nenhum agente resolve espera |
| Qualidade do croqui | Quando chega incompleto, o que falta? Quem descobre, e quando? | **Ceiling de Input** — o assunto central desta vertical |
| Padrão de coleta | Cada técnico faz do seu jeito ou existe modelo? Quem definiu? | Sem padrão, padronizar a entrada é o produto, não o conversor |
| Revisão e reemissão | Quantas pranchas voltam? Por norma, divergência com o croqui ou mudança de escopo? | Separa o loop 2 do loop 1 — causas e soluções diferentes |
| Orçamento | Quantos orçamentos são reprovados e voltam ao CAD? O quantitativo bate com a prancha? | Loop 3: consome projetista e orçamentista juntos |
| Obra e medição | Com que frequência o executado difere do projetado? Vira aditivo ou correção? | Loop 4 — o mais caro e o mais visível para o cliente final |
| Capacidade | Se dobrasse a demanda amanhã, o que quebraria primeiro? Contratariam? | Capacidade liberada ≠ redução de custo |
| Retrabalho invisível | Que informação a equipe digita mais de uma vez? | Sinal clássico de Improvement Opportunity |
| Custo de não fazer nada | Se continuar assim por doze meses, o que acontece? | **Se a resposta for "nada", não construa** |

## Hipóteses iniciais

Consolidam o que o blueprint e o mapa AS-IS afirmam — não crie numeração paralela.

| Nº | Hipótese | Como se derruba |
| --- | --- | --- |
| **H1** | **O gargalo é a entrada, não a conversão.** Croqui padronizado e app que impede sair do local com levantamento incompleto valem mais que qualquer conversor | Amostra de croquis classificada: se a maioria chega completa, H1 cai |
| **H2** | **O tempo dominante é espera, não execução.** O lead time croqui → prancha é fila e aguardo | Cronometragem com marcação ativo × espera em 10 a 20 casos |
| **H3** | **O ganho por croqui é pequeno; o valor está no volume e na fila.** Um projetista experiente já resolve rápido | Volume real × tempo mediano medido, contra o custo de desenvolver e operar |
| **H4** | **O retrabalho se concentra no loop 1** (croqui incompleto ou ilegível), e os loops 2–4 são consequência | Classificar cada retorno por loop e origem; se L2–L4 dominarem, H4 cai |
| **H5** | **O Ceiling de Input do croqui atual é baixo demais** para geometria automática confiável | É o que a Technical Feasibility mede: `Ceiling = (amostra − E1) ÷ amostra` |

> **As quatro vias de levantamento não são hipóteses de negócio — são os braços do teste:**
> **H_A** processo atual (croqui manual → DXF) · **H_B** croqui padronizado → DXF · **H_C** app
> guiado → DXF · **H_D** app + drone → DXF. Comparar precisão, tempo de campo, tempo de escritório,
> correções, segunda visita, custo por levantamento e tempo até CAD. Elas rodam **dentro** da
> Feasibility; não as renumere como H6–H9.

## Processos candidatos a mapear

A cadeia é a fonte dos candidatos: 1. Levantamento → 2. Input estruturado → 3. Geometria confiável →
4. DXF útil → 5. Quantitativos → 6. Orçamento, mais a medição que fecha o ciclo.

- **Levantamento de campo** — programação, deslocamento, medição, croqui ou caderneta, fotos,
  amarração
- **Input estruturado** — chegada ao escritório, conferência, contato com o técnico, segunda visita
- **Geometria confiável** — transcrição para o CAD, fechamento de poligonal, validação
- **DXF útil e emissão da prancha** — camadas e padrão CAD, revisão, reemissão, memorial
- **Quantitativos** — extração por serviço, conferência contra o projeto
- **Orçamento** — composição de custo, base de referência, BDI, revisão do reprovado
- **Medição de obra e boletim** — executado × projetado, as-built, boletim que sustenta o pagamento
- **Aditivo** — divergência que vira alteração contratual

## Erros E1–E5 e Ceiling de Input

É o vocabulário da Feasibility, e nesta vertical é o assunto principal: a qualidade do input **é** a
pergunta.

**E1 — o input não permite a resposta certa.** Croqui em que falta cota, o polígono não fecha, não há
amarração ou a anotação é ilegível: **nem um projetista experiente resolveria sem perguntar ou voltar
a campo**. É a classe que o teto exclui — `Ceiling de Input = (amostra − E1) ÷ amostra`.

A taxonomia completa (E2–E5) vive em [`../metodologia-fde.md`](../metodologia-fde.md) e este espelho
**não a reproduz**. Não invente rótulo em campo: classifique como E1 / não-E1 e registre a descrição
em texto livre.

> **O Ceiling decide antes do ROI.** Se 40% dos croquis são E1, nenhuma solução passa de 60% de
> acerto — e discutir payback antes disso é conversa sobre um número impossível. Meça o teto
> primeiro; só depois pergunte se vale a pena.

## Sistemas que costumam aparecer

**HIPÓTESE** — montada do blueprint e do senso comum do setor, ainda não observada em campo.

- **CAD e projeto:** AutoCAD, Civil 3D, BricsCAD, Revit em alguns escritórios
- **Geo:** QGIS, ArcGIS, Google Earth como camada de conferência informal
- **Campo:** estação total, receptor GNSS/RTK, trena a laser, caderneta em papel, celular para foto
- **Orçamento:** planilha própria, SINAPI baixado, eventual sistema dedicado
- **Coordenação real:** WhatsApp com foto de croqui, e-mail, pasta em nuvem sem convenção de nome

> A foto do croqui no WhatsApp é o dado de entrada de verdade. Trate como sistema, não como ruído.

## Dados a pedir (mínimo 6 meses)

- **Amostra de 15 a 30 croquis reais**, com o DXF ou a prancha correspondente — inclusive, e
  principalmente, **os que deram errado**
- Volume mensal por tipo de espaço, e quantos estão em fila hoje
- Datas por etapa: campo, entrada no CAD, primeira emissão, aprovação — é o que separa espera de
  execução
- Segundas visitas e o motivo de cada uma · pranchas reemitidas e o motivo
- Orçamentos reprovados e o que mudou na revisão · aditivos e divergências executado × projetado
- Custo-hora carregado por função: técnico de campo, projetista/CAD, orçamentista, responsável técnico
- Relação de sistemas, formato de exportação e meses de histórico

> Arquivo de projeto costuma ser de **terceiro** — do cliente do escritório ou do órgão contratante.
> Peça amostra com autorização escrita e aceite arquivo com identificação do contratante removida.
> Onde houver obra pública, boa parte já é informação pública, mas **o contrato do escritório pode
> ser mais restritivo que a lei** — pergunte antes de assumir.

## Objeções e respostas

Regra em todas: **concorde com a parte verdadeira antes de responder.** Diante de um responsável
técnico, defender-se soa como venda. **As doze são HIPÓTESE** — nenhuma foi ouvida em campo.

| O que ele diz | O que costuma significar | Resposta |
| --- | --- | --- |
| "Meu projetista faz isso em 10 minutos." | Ele está certo e está testando se você vai insistir | "Então talvez a resposta seja não automatizar essa etapa — e eu escrevo isso no relatório. O que eu quero medir é outra coisa: quanto tempo o croqui espera antes desses 10 minutos, e quantas vezes ele volta para campo." |
| "Isso é drone, né? Não tenho verba para drone." | Ele já decidiu qual é a solução | "Drone é uma fonte entre várias, não a solução obrigatória. Quem decide isso é a medição, não a preferência." |
| "Cada técnico faz o croqui do jeito dele." | A hipótese central da vertical acabou de ser confirmada | "É exatamente isso que eu preciso medir. Sem padrão, nenhum modelo tira geometria confiável — e o primeiro ganho está em padronizar a coleta." |
| "IA não vai entender croqui feito à mão." | Ceticismo técnico legítimo, e possivelmente correto | "Pode ser que não entenda mesmo. Por isso existe a Feasibility com amostra real: eu classifico os seus croquis e te digo o teto. Se for baixo, a recomendação é não construir." |
| "Quem assina o projeto sou eu." | A objeção mais séria, e a mais fácil de responder | "E continua sendo. Nada do que eu construir assina desenho. O sistema entrega base geométrica e alerta do que falta; o RRT/ART é seu." |
| "Os arquivos são dos meus clientes." | Obrigação contratual real | "Certo, e eu não preciso do acervo. Preciso de uma amostra com autorização, sem identificação do contratante." |
| "Isso teria que passar por licitação." | Interlocutor público — a conversa é outra | "Faz sentido, e por isso o diagnóstico não é contratação de software. Se depois virar solução, o caminho é licenciamento de plataforma existente, não desenvolvimento sob encomenda." |
| "Já temos Civil 3D e quase ninguém usa." | Cicatriz de ferramenta | "É o padrão que eu encontro. Quase nunca falta sistema; falta o que acontece entre o campo e o CAD." |
| "Já contratei consultoria e não deu em nada." | A cicatriz mais importante de tratar | "A diferença é que eu entrego número medido, não recomendação genérica. E se apontar que não vale mexer, eu escrevo isso também." |
| "Quanto isso reduz meu prazo?" | Quer a promessa antes da medição | **Não prometa.** "Não sei, e quem prometer número agora está chutando. Posso garantir o baseline." |
| "Se é de graça, qual é a pegadinha?" | Desconfiança legítima | "A pegadinha é que vou pedir acesso, croquis reais e horas da sua equipe, e feedback sincero." |
| "Depois vocês vão me cobrar caro, né?" | Medo do funil | "A conversa de preço acontece no go-live do PROVE, com o que a gente construiu já rodando. O diagnóstico é seu de qualquer forma." |

## Memória de campo

**Erros comuns**, **padrões reutilizáveis**, **números de referência** e **registro de aprendizado**
seguem **vazios** — a vertical não teve engagement real. Os números que circulam no blueprint (80
croquis/mês, 35 min, 8 min de retrabalho, 5% de segunda visita) são **exemplo de raciocínio
econômico, não medição**, e não devem ser copiados como observação.
