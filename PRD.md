# PRD — Portal Biahflow

> Atualizado em 05/08/2026. O escopo do MVP original (CRM → conversão → execução) foi entregue e
> o produto avançou para a **jornada de consultoria assistida por IA** (RFC 0002). O estado de
> entrega, item a item, vive no `roadmap.md`; este documento descreve o produto atual.

## Problema

A Biahflow precisa centralizar a passagem da venda para a entrega — antes dispersa entre conversas,
planilhas e documentos — e conduzir a consultoria como um produto repetível, do primeiro contato do
lead à operação contínua dos Funcionários Digitais no cliente.

## Público e objetivo

Usuários internos das áreas Administrativa, Vendas e Entrega. O portal é a **fonte da verdade** da
operação: registra clientes e leads, conduz oportunidades por um pipeline, transforma oportunidades
ganhas em projetos acompanháveis e alimenta o portal do cliente. A IA **acelera, não decide**: tudo
que ela produz é rascunho sujeito a revisão humana.

## Escopo

**Comercial.** Captação de leads pelo site (intake), qualificação por IA e agendamento automático de
reunião para leads qualificados. Clientes, contatos e oportunidades com valor e previsão de
fechamento, num pipeline configurável. **Três níveis de produto** (Discovery Express gratuito,
Discovery + Assessment, Implantação) que acompanham a oportunidade e definem escopo, preço e
cronograma inicial.

**Entrega.** Conversão da oportunidade ganha em projeto — sem duplicar cliente ou contexto — com
kickoff automático (marcos, tarefas, pasta no Drive e aviso ao dono). Jornada de transformação em
fases nomeadas com entregáveis, reuniões, pendências, documentos privados e Funcionários Digitais
como entidade acompanhada por KPI e ROI.

**Inteligência.** Assistente contextual por projeto e agentes especializados por área
(Comercial/Entrega/Financeiro), com contexto restrito e auditoria. Discovery, Assessment, AI Score
de maturidade, propostas e contratos gerados a partir da transcrição das reuniões. Indicadores de
ROI, health score, previsão de atrasos com explicação dos sinais e recomendações revisáveis.

**Plataforma.** Convites por e-mail, permissões por função, notificações in-app e por e-mail com
digest diário, integrações atrás de flag alternável em runtime (IA, Drive, Calendário, Assinatura,
Sincronia de tarefas) e API versionada `/api/v1/`.

## Fora de escopo

- **Consumo** do portal do cliente — o Biahflow emite webhook e snapshot; a interface do cliente é
  o repositório `portal_cliente`, em trilho separado (ADR 0003).
- **Outros provedores de assinatura** — o adaptador homologado é o Clicksign (ADR 0007); DocuSign e
  afins entram como novas classes do mesmo protocolo, ainda não construídas.
- **Ações autônomas de IA** — nenhum agente executa efeito colateral sozinho; memória multi-turno e
  ferramentas de ação ficam para decisão futura (ADR 0006).
- **Dados comerciais no portal do cliente** — valor, custo e margem nunca cruzam a fronteira.

## Critérios de sucesso

- Uma oportunidade ganha torna-se um projeto exatamente uma vez, sem duplicar cliente ou contexto
  comercial, e já nasce com o cronograma do nível de produto vendido.
- Pessoas de Entrega acompanham prazos, itens vencidos, saúde e risco dos projetos em um só lugar.
- Documentos não podem ser obtidos por usuários sem permissão.
- Todo artefato gerado por IA é auditável, avaliável e passa por revisão humana antes de sair.
- É possível medir a conversão entre os níveis de produto e o ROI por cliente, projeto e serviço.
