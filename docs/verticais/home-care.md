# Vertical Home Care — knowledge base

> **Espelho** da ficha canônica no Notion: **Home Care — Vertical Knowledge Base**
> <https://app.notion.com/p/3c982225ad27819e889dc18f8ce0c73b>
> Não se edita aqui. Trazido pela **ADR 0069**, que decidiu levar o método das verticais ao corpus
> da FDD 029.
> **A intel de conta não atravessa, e nesta vertical isso importa:** a ficha do Notion traz nome,
> site, números estimados, sistema em uso e situação financeira da conta em qualificação. Nada disso
> está aqui, por decisão de 05/09/2026 — `docs/` é commitado **e** alimenta os agentes, e o
> repositório já mantém documento real de cliente fora da imagem (FDD 029). Quem precisa da intel
> abre a ficha.
> As perguntas que valem para qualquer vertical estão em [`discovery-questions.md`](../discovery-questions.md).

Memória da vertical de atenção domiciliar: método, vocabulário e o que perguntar. É a vertical mais
adiantada da casa — **e ainda com zero Discoveries concluídos**.

## Glossário mínimo

Errar vocabulário custa autoridade nos primeiros cinco minutos.

| Termo | O que é |
| --- | --- |
| **Glosa** | Valor faturado que a operadora se recusa a pagar, normalmente por documentação ou autorização |
| **Recurso de glosa** | Processo de contestar a glosa junto à operadora |
| **Plantão / escala 12x36** | Regime típico de cuidador e técnico de enfermagem |
| **Evolução** | Registro do que foi feito no atendimento — a base da comprovação para faturamento |
| **Admissão** | Entrada do paciente: avaliação, orçamento, autorização, abertura do caso |
| **PAD** | Plano de atenção domiciliar; sua prorrogação é ato sensível e sujeito a questionamento da operadora |
| **TISS** | Padrão de troca de informação com operadoras de saúde |
| **Atenção domiciliar × internação domiciliar** | Complexidade e remuneração diferentes; não trate como a mesma coisa |

## Áreas de pressão — checklist de qualificação

Leia em voz alta e peça para o dono **ordenar**. A ordenação revela mais do que a descrição.

| Área | Pergunta de sondagem | O que você está caçando |
| --- | --- | --- |
| Escala e cobertura | Quantos plantões vocês cobrem por mês? Quando um cuidador falta, o que acontece nas duas horas seguintes? | Tempo de gente cara resolvendo falta no WhatsApp |
| Hora extra | Quanto pagaram de hora extra no último mês? É constante ou explode em algum período? | Custo recorrente disfarçado de exceção |
| Glosa e faturamento | Quanto do faturado volta glosado? Quanto disso recuperam no recurso? | Receita já produzida e não recebida |
| Documentação clínica | Quando a conta é glosada por documentação, o problema estava no registro do cuidador ou na conferência? | Qualidade do input — onde a IA costuma ser a resposta errada |
| Admissão do paciente | Entre o primeiro contato e o paciente em atendimento, quantos dias passam? Onde trava? | Receita adiada e desistência de caso |
| Compras e insumos | Vocês sabem quanto de insumo sobra ou se perde por paciente? | Perda invisível |
| Pessoas | Qual o turnover de cuidador? Quanto custa admitir e treinar um novo? | Custo repetitivo e risco assistencial |
| Retrabalho | Que informação a equipe digita mais de uma vez, em mais de um lugar? | Sinal clássico de Improvement Opportunity |

## Hipóteses iniciais

Nenhuma é fato. Existem para serem derrubadas pelo Discovery.

- **H1** — Escala e cobertura de faltas consomem tempo de gente cara, fora de qualquer sistema.
- **H2** — Documentação incompleta na ponta gera glosa; a causa está na **captura**, não na
  conferência.
- **H3** — O faturamento roda numa planilha paralela ao sistema de gestão.
- **H4** — Existe redigitação entre prontuário, escala e faturamento.
- **H5** — Padronizar a coleta na ponta gera mais valor do que automatizar a conferência no fim.

> **H2 e H5 apontam para a captura, e o processo-alvo típico é a conferência.** Não é contradição: a
> conferência é onde o erro é **detectado** — e o único lugar onde ele é **medível hoje**; a captura
> é onde ele é **causado**. O PROVE mede a detecção e testa a padronização da origem em paralelo. Se
> a origem entregar mais, isso é achado do Discovery, não fracasso do piloto.

## Processos candidatos a mapear

- **Escala e cobertura** — montagem, troca de plantão, falta e absenteísmo, hora extra, deslocamento
- **Admissão do paciente** — captação, avaliação inicial, orçamento, autorização do convênio,
  abertura do caso
- **Documentação clínica** — evolução do cuidador e do técnico, prescrição, checklist de visita,
  registro fotográfico
- **Faturamento e glosa** — fechamento mensal, conferência de documentação, envio, recurso,
  recebimento
- **Compras e insumos** — requisição, cotação, entrega na casa do paciente, estoque e perdas
- **Pessoal** — recrutamento de cuidadores, treinamento, turnover, ponto e folha
- **Auditoria e qualidade** — visita técnica, indicadores, incidentes, reclamações, exigências
  regulatórias

## Sistemas que costumam aparecer

ERP ou sistema de gestão · prontuário eletrônico · sistema de escala · ponto eletrônico ·
faturamento e TISS · planilhas de controle paralelas · **WhatsApp como camada real de
coordenação** · sistema contábil.

> O WhatsApp quase sempre é onde a operação realmente acontece. Trate como sistema, não como ruído.

**Postura diante do sistema incumbente:** o setor tem líderes de mercado consolidados, e o cliente
costuma ter insatisfação com interface e rigidez sem ter intenção de trocar. **A Biahflow entra como
complemento, nunca como substituição** — e o Discovery descobre quais partes do processo já estão
fora do sistema principal.

## Dados a pedir (mínimo 6 meses)

Volume de atendimentos, admissões e altas · escala realizada, trocas, faltas e coberturas · horas
extras por mês e por função · faturamento por fonte pagadora, glosas emitidas, glosas recuperadas,
prazo de recebimento · quadro de pessoal, custo de folha, turnover · consumo e perda de insumos ·
relação de sistemas e possibilidade de exportação.

> **Sempre sem identificação de paciente.** Quando a extração inevitavelmente trouxer identificação,
> o cliente pseudonimiza antes de enviar.

## Perguntas que mudam a proposta, e costumam ficar em aberto

Estas quatro aparecem como **DESCONHECIDO** na qualificação e cada uma move o desenho da solução:

- **Split entre atenção domiciliar e internação domiciliar 24h** — ID gera volume de documentação
  muito maior; cada plantão gera evolução.
- **Volume por operadora** — define a prioridade da biblioteca de regras. Comece pelas duas de maior
  volume.
- **A conferência é 100% ou por amostragem?** — muda radicalmente a proposta de valor.
- **Faturamento mensal por convênio** — é o que ancora a faixa de preço.

E duas implicações recorrentes: **cuidados paliativos** tornam a justificativa de prorrogação de PAD
mais sensível (a operadora questiona mais, e documentação fraca vira glosa); **operação no interior**
amplifica o atraso de documentos vindos do campo.

## Objeções e respostas

| O que ele diz | O que costuma significar | Resposta |
| --- | --- | --- |
| "Se é de graça, qual é a pegadinha?" | Desconfiança legítima | "A pegadinha é que vou pedir acesso e tempo da sua equipe, e feedback sincero. Se você achar que não vale, é melhor não começarmos." |
| "Minha equipe já está sobrecarregada." | Medo de custo oculto | "São cinco a oito conversas de 45 minutos em duas semanas. Eu me adapto ao turno de cada um." |
| "Já contratei consultoria e não deu em nada." | Cicatriz real — a mais importante de tratar | "A diferença é que eu entrego número, não recomendação genérica. E se o diagnóstico apontar que não vale mexer, eu escrevo isso também." |
| "Nossos dados são de paciente, não posso abrir." | Preocupação com LGPD | "Correto, e eu não preciso deles. Trabalho com dados operacionais e amostras anonimizadas. O acordo tem cláusula específica e você define o que sai da empresa." |
| "Isso não é para automatizar a escala?" | Ele já decidiu a solução | "Pode ser. Mas se a escala for o sintoma e a causa estiver no cadastro, automatizar a escala só faz o problema chegar mais rápido." |
| "Vou pensar e te falo." | Falta sponsor, urgência ou confiança | "Claro. Te ligo na [dia] só para saber se é sim ou não — os dois me servem." |
| "Depois vocês vão me cobrar caro, né?" | Medo do funil | "Depois do diagnóstico eu apresento uma proposta para provar a Improvement Opportunity nº 1 do backlog. Você olha e decide. O diagnóstico é seu de qualquer forma." |

## Memória de campo

**Erros comuns**, **padrões reutilizáveis**, **números de referência** e **registro de aprendizado**
seguem **vazios**: a vertical ainda não teve engagement real concluído. Não se preenche com hipótese
— só entra aqui erro observado em campo, padrão que funcionou em mais de um cliente e número que foi
medido.
