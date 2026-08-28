# FDD 016 — Artefatos da jornada

## Jornada

Fase 4 da visão da metodologia (RFC 0002), fechando a última lacuna do roadmap. As quatro etapas
que produzem texto — **Discovery**, **Assessment**, **Proposta** e **Contrato** — não tinham onde
morar. `_ai_run` devolvia `{text, interaction}` e o `AiInteraction` guardava só metadados de
auditoria (tokens, quem, nota), nunca o conteúdo. Na prática: proposta e contrato só sobreviviam
se alguém clicasse "Salvar como documento" (um `.txt` distinguível apenas pelo nome do arquivo);
Discovery e Assessment nem isso — o diagnóstico sumia ao recarregar a página.

Cada artefato passa a ser um registro com **conteúdo, estado próprio e carimbos de tempo**. Isso
resolve a perda de trabalho e, de quebra, torna medível a **conversão entre etapas** — antes só
existia conversão por nível de produto (`funnel.by_tier`, FDD 015) e por estágio do pipeline.

O `Document` **não** é substituído: ele segue sendo o arquivo e o alvo da assinatura eletrônica.
O artefato apenas o referencia quando o rascunho revisado vira documento.

## Regras

- **Um modelo, quatro tipos.** `Artifact` com `kind` (`discovery`/`assessment`/`proposal`/
  `contract`) em vez de quatro modelos — mesma escolha do `Service.tier` (FDD 015), e o que deixa
  o funil por etapa ser uma consulta só. Ver ADR 0008.
- **Vínculo único:** exatamente um de `commercial_opportunity`/`project`, validado em `clean()` e no
  serializer — mesma invariante do `Document`, e pelo mesmo motivo: o vínculo define quem enxerga
  o conteúdo. Não há campo `client`; o cliente vem sempre pela ponta vinculada.
- **Estados:** `draft → review → sent → accepted | rejected`. Rascunho e revisão vão e voltam
  enquanto o humano trabalha; depois de enviado só resta a decisão do cliente, que é terminal.
  As transições vivem em `ARTIFACT_TRANSITIONS` (`models.py`) e são validadas no serializer;
  `save()` carimba `sent_at` e `decided_at` sozinho, como `Pendencia`/`WorkItem` já faziam.
- **Geração por IA:** `_ai_run` ganhou `artifact_kind`/`source_meeting`. As quatro actions
  existentes (`opportunities/{id}/proposal|contract`, `meetings/{id}/discovery|assessment`) passam
  a criar o artefato em **rascunho** com o texto gerado, ligado ao `AiInteraction` que o auditou e,
  nas de reunião, à `Meeting` de origem. Guardas inalteradas: flag de IA, limite diário, auditoria.
  Nada muda para quem já consumia essas rotas — `text` e `interaction` seguem iguais e a chave
  `artifact` é **aditiva** (contrato `/api/v1/` preservado). IA desligada não cria artefato.
- **CRUD:** `/api/v1/artifacts/` sobre `ArchiveModelViewSet` (exclusão lógica como todo recurso de
  negócio), filtrável por `commercial_opportunity` (com `opportunity` vivo como alias da
  `/api/v1/`), `project`, `kind` e `status`. `created_by` vem da sessão,
  nunca do payload.
- **RBAC** (`resource = "artifact"`): Comercial lê e escreve tudo; Entrega lê e escreve apenas os
  artefatos **ligados a projeto** — proposta e contrato carregam valor e condição comercial, então
  ficam fora da consulta de quem é da entrega, como já acontece com as oportunidades não ganhas.
  Indicadores segue restrito a admin/comercial, então o funil por etapa não vaza.
  A segregação valia só na leitura (`get_queryset`) até a FDD 017 fechá-la também na escrita — e a
  mesma regra passou a valer para o `Document`, que é onde o texto revisado vai parar.
- **Contrato assinado fecha sozinho:** ao aplicar o evento do fornecedor (`esign.apply_event`), os
  artefatos de contrato do documento acompanham a decisão — `signed → accepted`,
  `declined → rejected`. A idempotência vem do retorno antecipado que já existia: a reentrega do
  webhook não chega a tocar o artefato (ADR 0007, FDD 009).
- **Funil por etapa:** `GET /analytics/` passa a trazer `funnel.by_stage` ao lado de `by_tier`,
  com total, enviados, aceitos, recusados, taxa de aceitação e `reached` — **clientes distintos**
  que chegaram à etapa, que é o que revela a queda de uma etapa para a seguinte. Sempre as quatro
  linhas, mesmo zeradas.

## Aceite

Em **Comercial**, gerar uma proposta numa oportunidade passa a registrá-la: ela aparece no painel
"Artefatos da jornada" como rascunho, com o texto editável, e continua lá depois de recarregar a
página. O texto revisado é salvo, o artefato avança para "em revisão" e "enviado", e "Salvar como
documento" cria o `Document` já ligado ao artefato. Em **Projetos**, Discovery e Assessment de uma
reunião com transcrição aparecem no mesmo painel em vez de sumirem ao fechar a tela. Pedir
assinatura de um contrato e receber o webhook de assinado leva o artefato a "aceito" sem
intervenção. Em **Indicadores**, o bloco "Conversão por etapa da jornada" mostra quantos clientes
chegaram a cada etapa e a taxa de aceitação de cada uma.

## Regressão crítica

Artefato sem vínculo, ou com as duas pontas, é rejeitado. Rascunho não pula direto para "aceito"
e um artefato decidido não volta atrás. O webhook de assinatura leva o contrato a "aceito" uma vez
só — a reentrega não recarimba `decided_at`. A resposta das quatro rotas de IA mantém `text` e
`interaction`. Com IA desligada (503), nenhum artefato é criado. Entrega não enxerga artefatos de
oportunidade.
