# ADR 0045 — A camada global vem vendorizada e pinada, e o Project Context sai de baixo dela

**Status:** aceito
**Data:** 26/08/2026
**Fase:** transversal — governança e contexto de agentes

## Contexto

Duas coisas erradas moravam no mesmo caminho.

**A primeira é ambiguidade de nome.** `docs/engineering-os/` continha um arquivo só,
`project-context.md`, que é o Project Context **deste** repositório — escrito aqui, editado
aqui, e apontado por `AGENTS.md`, `CLAUDE.md` e `README.md`. Nos repositórios irmãos desta
organização, esse mesmo caminho significa exatamente o oposto: o espelho vendorizado da camada
global, cópia fiel que **não se edita aqui**. Mesmo caminho, significado invertido. Enquanto
nenhum dos dois usos precisou do outro, a colisão foi barata; no dia em que este repositório
quisesse o espelho, os dois disputariam o diretório.

**A segunda é que a camada global não existia aqui.** O `AGENTS.md` dizia que o Project Context
*"complementa a Engineering OS global; não a substitui"* — e a Engineering OS global não estava
em lugar nenhum que este repositório alcançasse. Nos irmãos, ela era alcançada por um caminho
absoluto da máquina do operador, `~/workspace/engineeringOS/`, que nunca resolveu para o CI nem
para colaborador novo, e que morreu para todos em 25/08/2026 quando o diretório mudou de lugar.
Sem erro: referência que não resolve não é falha, é ausência.

## Decisão

**D1. O Project Context passa a `docs/project-context.md`.** É a convenção dos repositórios
irmãos, e libera o nome `docs/engineering-os/` para o que ele significa em toda a organização.
As referências em `AGENTS.md`, `CLAUDE.md` e `README.md` acompanham; os dez links internos do
próprio documento também, porque subir um nível os quebra todos.

**D2. Um espelho completo da camada global vive em `docs/engineering-os/`.** Cópia fiel, em
inglês, sem tradução e sem edição manual — 91 arquivos, 760 KB. Espelho completo e não recorte:
copiar só os trechos citados quebraria os links internos entre os documentos globais e criaria
uma terceira versão parcial da camada.

**D3. O pino é uma tag SemVer, e o que não é tag é recusado.** `PINNED_TAG` em
`.github/scripts/sync_engineering_os.py` é constante versionada: avançar o pino é diff de uma
linha, revisado como qualquer outra mudança. Branch se move, e pino que se move não é pino. O
`PROVENANCE.md` registra a tag **e** o commit que ela resolve, para o pino continuar conferível
se alguém repontar a tag.

**D4. A camada global entra no topo da precedência**, acima dos canônicos deste repositório. A
precedência é **assimétrica**: uma camada abaixo pode *acrescentar* restrição — mais teste, mais
revisão, mais evidência — e **não pode enfraquecer** guardrail global nem remover gate humano.
Documento daqui mais estrito que o global vale; mais frouxo é defeito, e o conserto é aqui.

Consequência que precisa ficar dita: a partir de agora um avanço de pino pode tornar este
repositório não conforme sem que nenhuma linha daqui mude. É o que o `VERSIONING.md` da origem
chama de `MAJOR` — e, enquanto o major da origem for `0`, é o `MINOR` que carrega isso.

**D5. `.github/scripts/test_docs_links.py` confere todo link relativo, e entra na Qualidade.**
É o que impede a próxima citação de virar texto morto, e o que teria pego, sozinho, os dez
links quebrados pela mudança da D1. Roda como programa, no molde do `test_release_evidence.py`.

**D6. O espelho fica fora do corpus de conhecimento (FDD 029).** O `KB_SOURCES` é allowlist e
não inclui `docs/` solto, então nada precisa mudar — e é deliberado que assim continue: o corpus
responde sobre **este produto**, e 760 KB de governança em inglês diluiriam as buscas sem
responder nada que um agente daqui pergunte.

## Consequências

O nome `docs/engineering-os/` passa a significar a mesma coisa nos cinco repositórios que o têm.
A camada global fica alcançável do próprio checkout — por CI, por colaborador novo, por agente
em nuvem — e a defasagem vira fato datado: `v0.1.0` diz mais que um SHA.

Em troca, 760 KB de documentação em inglês entram no repositório e aparecem nas buscas de
arquivo, e a origem precisa manter disciplina de release: sem tag nova, não há como avançar o
pino.

**Fica aberto:** o espelho envelhece em silêncio entre sincronizações. Uma guarda comparando o
pino com a última tag publicada seria a outra metade — o portão detecta, o conserto é de uma
pessoa —, mas precisa de rede no job.
