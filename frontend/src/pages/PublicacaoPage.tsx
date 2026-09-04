import { ArrowLeft, Flame, Quote, Target, Workflow } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import {
  api,
  listImprovementOpportunities,
  listPainPointsByAccount,
  publishEvidence,
  publishFinding,
  publishImprovementOpportunity,
  publishPainPoint,
  publishProcess,
  unpublishEvidence,
  unpublishFinding,
  unpublishImprovementOpportunity,
  unpublishPainPoint,
  unpublishProcess,
} from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import { PublicacaoBadge, epistemicoBadgeClass } from "../components/StatusDot";
import { mensagemDeFalha } from "../erros";
import type {
  Account,
  Evidence,
  Finding,
  ImprovementOpportunity,
  PainPoint,
  Process,
  PublicationState,
} from "../types";

/**
 * A tela que decide **o que o cliente vê** — `/contas/:id/publicacao`.
 *
 * Governada pelo DAP `docs/design/dap-publicacao-discovery-r1/`, revisão 1, decisões
 * **A1 · B1 · C1 · D1 · E1 · F1 · G1**. Mudar a superfície exige revisão nova do pacote, não
 * julgamento na hora.
 *
 * **A1 — o ato é sobre o conjunto, não sobre uma linha.** Decidir o que atravessa para a aba
 * Discovery do portal é uma decisão sobre o Discovery *da conta*; e a cadeia impõe ordem
 * (`Process` → `Evidence` → `Finding` → `PainPoint` → `ImprovementOpportunity`), que numa tela por
 * processo o operador subiria por tentativa e erro, navegando entre telas. A `ProcessDetailPage`
 * ganha só o selo de leitura e um link para cá. **Nenhum link novo no menu lateral**: publicação é
 * sempre de uma conta, e um item de menu que abre pedindo "qual conta?" é um beco — a mesma razão
 * já registrada em `/contas/:id/priorizacao` e `/contas/:id/valor`.
 *
 * **C1 — a hierarquia visual *é* a cadeia**: mapa → achado → evidência aninhada sob o achado →
 * dor, e as oportunidades num painel próprio no fim, porque elas agrupam dores de mais de um mapa.
 * É assim que a tela ensina a ordem em vez de deixar descobrir.
 *
 * **E1 — a tela nunca reexpressa a regra.** O que falta e o que prende são frases do servidor
 * (`publication.frase_do_que_falta` e `frase_do_impedimento`, publicadas em `publication_state`).
 * Não há mapa chave→rótulo em TypeScript: ele seria a segunda definição da copy que já existe no
 * backend, e as duas divergem no primeiro conserto sem nada ficar vermelho.
 *
 * **F1 — a tela conhece a *ordem* da cadeia, e só a ordem.** Ela dispara os `POST` um a um nessa
 * sequência; nunca conclui que um item *vai* passar. Quem decide é o servidor, item a item, e cada
 * recusa volta com a frase dele.
 *
 * **G1 — o botão de ocultar não é oferecido no item preso.** Um botão habilitado para um `POST`
 * que o servidor nega é o defeito que `CLAUDE.md` nomeia para o PROVE.
 *
 * Ficam **reservados** no pacote, e por isso não existem aqui: a pré-visualização "como o cliente
 * vê" e o histórico de publicação. Controle inerte é defeito, não placeholder.
 */

/** Os cinco recursos que atravessam. O nome é o do modelo, em `snake_case`, para a chave de
 *  seleção ser legível em teste e em depuração. */
type Recurso = "process" | "evidence" | "finding" | "pain_point" | "improvement_opportunity";
type Chave = string;

const chaveDe = (recurso: Recurso, id: number): Chave => `${recurso}:${id}`;
const recursoDaChave = (chave: Chave) => chave.slice(0, chave.indexOf(":")) as Recurso;
const idDaChave = (chave: Chave) => Number(chave.slice(chave.indexOf(":") + 1));

/**
 * A ordem da cadeia — o **único** conhecimento de regra que esta tela carrega (decisão F1).
 *
 * É a mesma escada de `backend/apps/core/publication.py`: a evidência sustenta o achado, o achado
 * sustenta a dor, a dor sustenta a oportunidade, e o processo ancora os dois do meio. Ordenar não
 * é reexpressar a regra; concluir "isto vai passar" seria.
 */
const ORDEM_DA_CADEIA: readonly Recurso[] = ["process", "evidence", "finding", "pain_point", "improvement_opportunity"];

const PUBLICAR: Record<Recurso, (id: number) => Promise<unknown>> = {
  process: publishProcess,
  evidence: publishEvidence,
  finding: publishFinding,
  pain_point: publishPainPoint,
  improvement_opportunity: publishImprovementOpportunity,
};
const OCULTAR: Record<Recurso, (id: number) => Promise<unknown>> = {
  process: unpublishProcess,
  evidence: unpublishEvidence,
  finding: unpublishFinding,
  pain_point: unpublishPainPoint,
  improvement_opportunity: unpublishImprovementOpportunity,
};

/** O sujeito da frase do diálogo de ocultar. É copy da superfície — o nome do que se retira —, e
 *  não rótulo de regra de publicação: nenhuma destas palavras sai de `publication.py`. */
const SUJEITO: Record<Recurso, string> = {
  process: "O mapa",
  evidence: "A evidência",
  finding: "O achado",
  pain_point: "A dor",
  improvement_opportunity: "A oportunidade",
};

/**
 * O motivo de uma recusa **como o servidor a escreveu**, sem a orientação por código de `erros.ts`.
 *
 * `mensagemDeFalha` acrescenta "recarregue para ver o que vale agora" no 409 e "confira o degrau"
 * no 400 — as duas certas na tela de Cobrança e erradas aqui: nada mudou desde que a tela
 * carregou, e não há degrau nenhum. O board desenha a linha com o texto puro do servidor, e a
 * decisão E1 é sobre exatamente isso. A faixa de **carga**, essa, segue usando `mensagemDeFalha`:
 * ali a orientação por código é o que ajuda.
 */
const motivoDoServidor = (cause: unknown) =>
  (cause as { message?: string }).message || "Não foi possível publicar este item.";

const dataCurta = (iso: string) => new Date(iso).toLocaleDateString("pt-BR");

/** Uma linha da árvore, já resolvida: é a forma que o `renderLinha` consome. */
type Linha = {
  recurso: Recurso;
  id: number;
  titulo: string;
  descricao: string;
  estado: PublicationState;
  /** O recuo da árvore: 0 = mapa, 1 = achado/dor, 2 = evidência sob o achado. */
  nivel: 0 | 1 | 2;
  icone: ReactNode;
  /** O selo vizinho da linha — hoje só o epistêmico do achado. Vem **antes** do de publicação, que
   *  é sempre o último da `.row-meta` (decisão D1). */
  selo?: ReactNode;
};

export function PublicacaoPage({ accountId }: { accountId: number }) {
  const { user } = useAuth();
  const [account, setAccount] = useState<Account>();
  const [processos, setProcessos] = useState<Process[]>([]);
  const [evidencias, setEvidencias] = useState<Evidence[]>([]);
  const [achados, setAchados] = useState<Finding[]>([]);
  const [dores, setDores] = useState<PainPoint[]>([]);
  const [oportunidades, setOportunidades] = useState<ImprovementOpportunity[]>([]);
  const [selecionadas, setSelecionadas] = useState<Set<Chave>>(new Set());
  /** O lote em curso: a fila na ordem da cadeia e em qual item ela está. */
  const [emCurso, setEmCurso] = useState<{ fila: Chave[]; indice: number } | null>(null);
  /** As recusas do último lote, item a item, com a frase do servidor. */
  const [falhas, setFalhas] = useState<Record<Chave, string>>({});
  const [resumo, setResumo] = useState("");
  const [ocultando, setOcultando] = useState<{ recurso: Recurso; id: number; titulo: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [semAcesso, setSemAcesso] = useState(false);

  const load = useCallback(() => Promise.all([
    api<Account>(`/accounts/${accountId}/`),
    api<Process[]>(`/processes/?account=${accountId}`),
    api<Evidence[]>(`/evidence/?account=${accountId}`),
    api<Finding[]>(`/findings/?account=${accountId}`),
    listPainPointsByAccount(accountId),
    listImprovementOpportunities(accountId),
  ]).then(([conta, mapas, fontes, afirmacoes, doresDaConta, oportunidadesDaConta]) => {
    setAccount(conta); setProcessos(mapas); setEvidencias(fontes); setAchados(afirmacoes);
    setDores(doresDaConta); setOportunidades(oportunidadesDaConta); setSemAcesso(false);
  }).catch((cause: unknown) => {
    // O recorte da Entrega (RFC 0003) chega como 404 na conta: quem não participa de projeto
    // nenhum dela não a alcança pela rota. Só quem é da Entrega vê a frase — para admin e Vendas
    // um 404 significa mesmo "esta conta não existe".
    const status = (cause as { status?: number }).status;
    if (user?.role === "delivery" && (status === 403 || status === 404)) { setSemAcesso(true); return; }
    setError(mensagemDeFalha(cause));
  }), [accountId, user?.role]);
  useEffect(() => { void load(); }, [load]);

  const evidenciaExiste = (id: number) => evidencias.some(evidencia => evidencia.id === id);
  const registroDe = (recurso: Recurso, id: number): { publication_state: PublicationState } | undefined => {
    if (recurso === "process") return processos.find(item => item.id === id);
    if (recurso === "evidence") return evidencias.find(item => item.id === id);
    if (recurso === "finding") return achados.find(item => item.id === id);
    if (recurso === "pain_point") return dores.find(item => item.id === id);
    return oportunidades.find(item => item.id === id);
  };
  /** Só o que ainda não atravessou tem caixa de seleção — e o **bloqueado tem** (decisão F1). O
   *  registro ausente (arquivado, ou fora do recorte da conta) não é selecionável: ele não está na
   *  tela, e enfileirá-lo produziria um `POST` sobre uma linha que ninguém viu. */
  const selecionavel = (chave: Chave) => {
    const registro = registroDe(recursoDaChave(chave), idDaChave(chave));
    return registro !== undefined && registro.publication_state.state !== "published";
  };

  /** O "para baixo" da cascata: quem aparece **dentro** daquele item na árvore. Estrutura pura —
   *  nenhuma regra de publicação passa por aqui. */
  const subarvore = (recurso: Recurso, id: number): Chave[] => {
    if (recurso === "process") {
      const doMapa = achados.filter(achado => achado.process === id);
      return [
        ...doMapa.flatMap(achado => [
          chaveDe("finding", achado.id),
          ...achado.evidences.filter(evidenciaExiste).map(eid => chaveDe("evidence", eid)),
        ]),
        ...dores.filter(dor => dor.process === id).map(dor => chaveDe("pain_point", dor.id)),
      ];
    }
    if (recurso === "finding") {
      const achado = achados.find(candidato => candidato.id === id);
      return achado ? achado.evidences.filter(evidenciaExiste).map(eid => chaveDe("evidence", eid)) : [];
    }
    return [];
  };

  /**
   * O "para cima" da cascata: **o que aquele item precisa que suba antes**.
   *
   * Quem responde é o servidor — `publication_state.missing`, as chaves que a decisão E1 mantém no
   * payload justamente para isto. A tela não pergunta "este achado é fato?" nem "esta dor tem
   * achado vivo?": ela lê o que o backend disse que falta e marca os candidatos daquele degrau. É
   * a diferença entre consumir a resposta e reescrever a pergunta.
   *
   * Um degrau marca **todos** os candidatos vivos e não publicados, e não "um": o requisito é *ao
   * menos um*, e escolher qual seria a tela decidindo por quem publica, sempre para o mesmo lado.
   */
  const requisitos = (chave: Chave): Chave[] => {
    const recurso = recursoDaChave(chave);
    const id = idDaChave(chave);
    const registro = registroDe(recurso, id);
    if (!registro) return [];
    return registro.publication_state.missing.flatMap(requisito => {
      if (requisito === "published_process") {
        // Só achado e dor citam mapa — a evidência é a folha e o mapa é raiz do próprio ramo
        // (`publication.py`). O `undefined` é o ramo que o servidor nunca produz, escrito em vez de
        // suposto: um `missing` novo em outro recurso não pode virar seleção de um registro alheio.
        const ancora = recurso === "finding" ? achados.find(achado => achado.id === id)?.process
          : recurso === "pain_point" ? dores.find(dor => dor.id === id)?.process
          : undefined;
        return ancora !== null && ancora !== undefined && processos.some(mapa => mapa.id === ancora)
          ? [chaveDe("process", ancora)] : [];
      }
      if (requisito === "published_evidence") {
        const achado = achados.find(candidato => candidato.id === id);
        return achado ? achado.evidences.filter(evidenciaExiste).map(eid => chaveDe("evidence", eid)) : [];
      }
      if (requisito === "published_finding") {
        const dor = dores.find(candidata => candidata.id === id);
        return dor ? dor.findings.filter(fid => achados.some(achado => achado.id === fid)).map(fid => chaveDe("finding", fid)) : [];
      }
      const oportunidade = oportunidades.find(candidata => candidata.id === id);
      return oportunidade
        ? oportunidade.pain_points.filter(pid => dores.some(dor => dor.id === pid)).map(pid => chaveDe("pain_point", pid))
        : [];
    });
  };

  /** Marcar: leva a subárvore junto e, de cada item marcado, o que ele precisa que suba antes —
   *  transitivamente, até o ponto fixo. */
  function marcar(recurso: Recurso, id: number) {
    setSelecionadas(atuais => {
      const proximas = new Set(atuais);
      const fila = [chaveDe(recurso, id), ...subarvore(recurso, id)];
      while (fila.length) {
        const chave = fila.pop() as Chave;
        if (proximas.has(chave) || !selecionavel(chave)) continue;
        proximas.add(chave);
        fila.push(...requisitos(chave));
      }
      return proximas;
    });
  }

  /** Desmarcar leva a subárvore junto e **não** mexe nos ancestrais: quem foi puxado para cima
   *  pode continuar valendo para outro item ainda marcado, e desfazê-lo em silêncio tiraria da
   *  fila algo que quem seleciona não pediu para tirar. */
  function desmarcar(recurso: Recurso, id: number) {
    setSelecionadas(atuais => {
      const fora = new Set([chaveDe(recurso, id), ...subarvore(recurso, id)]);
      return new Set([...atuais].filter(chave => !fora.has(chave)));
    });
  }

  /**
   * O lote: `POST` sequenciais na ordem da cadeia, e **falha parcial não desfaz nada**.
   *
   * Desfazer o que subiu para "deixar a tela consistente" apagaria decisões humanas por causa de
   * recusas alheias a elas — é o argumento das duas guardas de arquivamento (FDD 045, FDD 048).
   * Cada recusa fica na linha do item, com a frase do servidor, e o resumo diz quantos passaram.
   */
  async function publicarSelecionados(ordemDeLeitura: Chave[]) {
    const fila = ORDEM_DA_CADEIA.flatMap(recurso =>
      ordemDeLeitura.filter(chave => recursoDaChave(chave) === recurso && selecionadas.has(chave)));
    if (!fila.length) return;
    setError(""); setResumo(""); setFalhas({});
    const recusas: Record<Chave, string> = {};
    for (const [indice, chave] of fila.entries()) {
      setEmCurso({ fila, indice });
      try { await PUBLICAR[recursoDaChave(chave)](idDaChave(chave)); }
      catch (cause) { recusas[chave] = motivoDoServidor(cause); }
    }
    setEmCurso(null);
    setFalhas(recusas);
    // A seleção zera: o que passou perdeu a caixa, e manter o resto marcado deixaria o contador do
    // botão afirmando uma fila que já rodou. O que foi recusado continua dito na linha.
    setSelecionadas(new Set());
    const recusados = Object.keys(recusas).length;
    const passaram = fila.length - recusados;
    if (recusados) {
      setResumo(`${recusados} de ${fila.length} ${recusados === 1 ? "item não foi publicado" : "itens não foram publicados"}. `
        + (passaram
          ? `${passaram === 1 ? "O item que passou continua visível" : `Os ${passaram} que passaram continuam visíveis`} ao cliente — nada foi desfeito.`
          : "Nada foi desfeito."));
    }
    await load();
  }

  async function ocultarDoCliente() {
    if (!ocultando) return;
    setBusy(true); setError("");
    try { await OCULTAR[ocultando.recurso](ocultando.id); setOcultando(null); await load(); }
    catch (cause) { setOcultando(null); setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  if (semAcesso) return <section className="space-y-7">
    <a href={`/contas/${accountId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para a conta</a>
    <section className="panel"><p className="empty-state">Você não participa de nenhum projeto desta conta.</p></section>
  </section>;
  if (error && !account) return <div role="alert" className="alert--error">{error}</div>;
  // O mesmo esqueleto de `ProcessDetailPage` — não um estado de carregamento novo, e sem texto de
  // espera: um "Carregando…" ao lado de um esqueleto diz duas vezes a mesma coisa.
  if (!account) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  const nomeDoProcesso = (id: number | null) => processos.find(processo => processo.id === id)?.name ?? "";
  const idsDeProcesso = new Set(processos.map(processo => processo.id));
  const semMapa = (id: number | null) => id === null || !idsDeProcesso.has(id);

  /**
   * A evidência aparece **pela forma da fonte e pela data**, nunca pelo trecho.
   *
   * `raw_excerpt` e `content_hash` não atravessam para o portal (FDD 051), e o board não os desenha
   * nem deste lado — mostrá-los aqui sugeriria que o cliente os verá. `reference` é o localizador
   * da fonte, e esse sim identifica a evidência sem transcrever nada.
   */
  const linhaDaEvidencia = (evidencia: Evidence, nivel: 0 | 1 | 2): Linha => ({
    recurso: "evidence", id: evidencia.id,
    titulo: `${evidencia.kind_display} — ${dataCurta(evidencia.captured_at)}`,
    descricao: evidencia.reference ? `Evidência · ${evidencia.reference}` : "Evidência",
    estado: evidencia.publication_state, nivel, icone: null,
  });
  const linhaDoAchado = (achado: Finding, nivel: 0 | 1): Linha => ({
    recurso: "finding", id: achado.id, titulo: achado.statement,
    descricao: semMapa(achado.process)
      ? "Achado · sem mapa citado"
      : `Achado · ancorado em "${nomeDoProcesso(achado.process)}"`,
    estado: achado.publication_state, nivel,
    icone: <span className="metric-icon"><Quote className="size-4" /></span>,
    selo: <span className={`state ${epistemicoBadgeClass(achado.epistemic_status)}`}>{achado.epistemic_status_display}</span>,
  });
  const linhaDaDor = (dor: PainPoint, nivel: 0 | 1): Linha => ({
    recurso: "pain_point", id: dor.id, titulo: dor.title,
    descricao: `Dor · impacto ${dor.impact_type_display.toLowerCase()} · ${dor.status_display.toLowerCase()}`,
    estado: dor.publication_state, nivel,
    icone: <span className="metric-icon"><Flame className="size-4" /></span>,
  });
  /** As evidências que aquele achado cita, na ordem em que ele as cita. Uma evidência citada por
   *  dois achados aparece sob os dois — a chave de seleção é a mesma, então marcar num lugar marca
   *  no outro, que é o que o M2M significa. */
  const evidenciasDo = (achado: Finding) =>
    achado.evidences.flatMap(eid => evidencias.filter(evidencia => evidencia.id === eid));

  /**
   * A árvore, montada uma vez e lida por três consumidores: a renderização, os contadores e a fila
   * do lote. **Todo registro carregado aparece exatamente uma vez** — o que não tem mapa (ou cita
   * um mapa arquivado) entra no fim, em nível raiz, com a descrição dizendo o que falta citar.
   * Escondê-lo deixaria um dos cinco publicáveis sem porta na única tela que publica.
   */
  const arvore: Linha[] = [
    ...processos.flatMap(processo => [
      {
        recurso: "process" as const, id: processo.id, titulo: processo.name,
        descricao: "Mapa do processo", estado: processo.publication_state, nivel: 0 as const,
        icone: <span className="metric-icon"><Workflow className="size-4" /></span>,
      },
      ...achados.filter(achado => achado.process === processo.id).flatMap(achado => [
        linhaDoAchado(achado, 1),
        ...evidenciasDo(achado).map(evidencia => linhaDaEvidencia(evidencia, 2)),
      ]),
      ...dores.filter(dor => dor.process === processo.id).map(dor => linhaDaDor(dor, 1)),
    ]),
    ...achados.filter(achado => semMapa(achado.process)).flatMap(achado => [
      linhaDoAchado(achado, 0),
      ...evidenciasDo(achado).map(evidencia => linhaDaEvidencia(evidencia, 1)),
    ]),
    ...dores.filter(dor => semMapa(dor.process)).map(dor => linhaDaDor(dor, 0)),
  ];
  // A evidência que nenhum achado cita não teria onde aparecer — e ela é um dos cinco publicáveis.
  const citadas = new Set(achados.flatMap(achado => achado.evidences));
  arvore.push(...evidencias.filter(evidencia => !citadas.has(evidencia.id))
    .map(evidencia => ({ ...linhaDaEvidencia(evidencia, 0 as const), descricao: "Evidência · sem achado que a cite" })));

  const linhasDeOportunidade: Linha[] = oportunidades.map(oportunidade => ({
    recurso: "improvement_opportunity", id: oportunidade.id, titulo: oportunidade.title,
    descricao: `Oportunidade de melhoria · ${oportunidade.pain_points.length} ${oportunidade.pain_points.length === 1 ? "dor agrupada" : "dores agrupadas"}`
      // O score sai do servidor como `"78.00"` — texto, como todo decimal desta API —, e a linha o
      // mostra na mesma forma da tela de priorização. Sem avaliação ele vem nulo e **some**: um
      // zero aqui afirmaria que a oportunidade foi avaliada e vale zero.
      + (oportunidade.score === null ? "" : ` · Opportunity Score ${Number(oportunidade.score).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}`),
    estado: oportunidade.publication_state, nivel: 0,
    icone: <span className="metric-icon"><Target className="size-4" /></span>,
  }));

  const todas = [...arvore, ...linhasDeOportunidade];
  const ordemDeLeitura = todas.map(linha => chaveDe(linha.recurso, linha.id));
  const quantos = (estado: PublicationState["state"]) => todas.filter(linha => linha.estado.state === estado).length;
  const visiveis = quantos("published");
  const prontos = quantos("ready");
  const bloqueados = quantos("blocked");

  function renderLinha(linha: Linha) {
    const chave = chaveDe(linha.recurso, linha.id);
    const publicado = linha.estado.state === "published";
    const preso = publicado && linha.estado.blocked_by > 0;
    const posicao = emCurso ? emCurso.fila.indexOf(chave) : -1;
    // O recuo é o que sobrevive ao celular: a cadeia se lê pelo deslocamento à esquerda e pelo
    // fundo, não por colunas — três níveis somam 52px numa tela de 342px de conteúdo.
    const recuo = ["", "bg-canvas pl-9 sm:pl-14", "bg-surface-subtle pl-13 sm:pl-22"][linha.nivel];
    return <div className={`row ${recuo}`} key={chave}>
      {/* **A caixa existe em todo item não publicado, inclusive no bloqueado** (decisão F1). Sem
          isso o lote deixaria de fora o caso mais comum — a conta em que nada foi publicado ainda,
          onde todo filho está bloqueado até o pai subir. O `aria-label` nomeia o item porque a tela
          tem uma destas por linha, e "Selecionar" repetido quinze vezes não localiza nenhuma. */}
      {!publicado && <input
        type="checkbox" className="size-4 shrink-0 rounded border-slate-300 text-brand-500"
        aria-label={`Selecionar para publicar: ${linha.titulo}`}
        checked={selecionadas.has(chave)} disabled={emCurso !== null}
        onChange={event => event.target.checked ? marcar(linha.recurso, linha.id) : desmarcar(linha.recurso, linha.id)}
      />}
      {linha.icone}
      <div className="row-main">
        <strong>{linha.titulo}</strong>
        <span>{linha.descricao}</span>
        {/* A frase vem do servidor, e só o rótulo "Falta:" é da superfície. No item bloqueado e
            selecionado ela muda de papel — de "por que você não pode" para "o que vai junto" —
            sem mudar de texto, porque o estado que ela descreve é o mesmo. */}
        {linha.estado.state === "blocked" && <span>Falta: {linha.estado.missing_phrase}</span>}
        {preso && <span>{linha.estado.blocked_phrase}</span>}
        {posicao >= 0 && emCurso && <span>
          {posicao < emCurso.indice ? "Publicado agora" : posicao === emCurso.indice ? "Publicando…" : "Na fila"}
          {" "}— {posicao + 1}º na ordem da cadeia
        </span>}
        {falhas[chave] && <span className="text-danger">{falhas[chave]}</span>}
      </div>
      {/* Fora de `.row-main`: `.row-main span`/`strong` sobrescrevem display e cor de qualquer
          primitiva aninhada ali, e o `.state` perderia a própria pele em silêncio. */}
      <div className="row-meta">
        {linha.selo}
        <PublicacaoBadge estado={linha.estado.state} />
        {/* Decisão **G1**: no item preso o botão fica desabilitado e o impedimento está na linha —
            não num `title=`. Habilitá-lo seria oferecer um `POST` que o servidor nega. */}
        {publicado && <button
          type="button" className="btn btn--secondary ml-auto"
          disabled={preso || busy}
          aria-label={`Ocultar do cliente: ${linha.titulo}`}
          onClick={() => setOcultando({ recurso: linha.recurso, id: linha.id, titulo: linha.titulo })}
        >Ocultar do cliente</button>}
      </div>
    </div>;
  }

  return <section className="space-y-7">
    <a href={`/contas/${accountId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para a conta</a>
    {ocultando && <ConfirmDialog
      title="Ocultar do cliente"
      message={<>{SUJEITO[ocultando.recurso]} <strong className="text-ink">{ocultando.titulo}</strong> sai da aba Discovery do portal do cliente — ele deixa de ver o que está vendo hoje. Nada é apagado: o registro continua aqui, e publicar de novo é um clique.</>}
      confirmLabel="Ocultar" busy={busy}
      onCancel={() => setOcultando(null)} onConfirm={() => void ocultarDoCliente()}
    />}
    <header className="page-head">
      <p className="eyebrow">Discovery estruturado</p>
      <h1>Publicação do Discovery — {account.name}</h1>
      <p>O que estiver visível aqui atravessa para a aba Discovery do portal do cliente. O que estiver oculto não existe para ele.</p>
    </header>
    {error && <p role="alert" className="alert--error">{error}</p>}
    {resumo && <p role="alert" className="alert--error">{resumo}</p>}

    <div className="toolbar">
      <div className="filter-bar">
        <span className="filter-chip filter-chip--on">{visiveis} {visiveis === 1 ? "visível ao cliente" : "visíveis ao cliente"}</span>
        <span className="filter-chip">{prontos} {prontos === 1 ? "pronto para publicar" : "prontos para publicar"}</span>
        <span className="filter-chip">{bloqueados} {bloqueados === 1 ? "bloqueado" : "bloqueados"}</span>
      </div>
      {/* Quebra em largura cheia abaixo de `sm` pela razão medida em `PriorizacaoPage`: o rótulo do
          `.btn` não hifeniza, e em 390px ele empurrava a página para fora. */}
      <button
        type="button" className="btn w-full shrink-0 sm:ml-auto sm:w-auto"
        disabled={emCurso !== null || !selecionadas.size}
        onClick={() => void publicarSelecionados(ordemDeLeitura)}
      >{emCurso ? "Aguarde…" : `Publicar selecionados (${selecionadas.size})`}</button>
    </div>

    {/* **A árvore continua listada mesmo sem pendência**, e é essa a diferença entre os dois
        vazios: aqui não falta conteúdo, falta pendência. Esconder a lista tiraria a resposta à
        pergunta que traz alguém a esta tela — *o que o cliente está vendo?* — e deixaria a
        ocultação sem porta. */}
    {todas.length > 0 && !prontos && !bloqueados
      && <p className="empty-state">Todo o Discovery desta conta já está visível ao cliente. Nada aguarda publicação.</p>}

    <section className="panel panel--flush">
      <div className="panel-heading">
        <div className="flex min-w-0 items-center gap-3">
          <span className="metric-icon"><Workflow className="size-4" /></span>
          <div>
            <h2 className="font-semibold text-ink">Mapas, achados, evidências e dores</h2>
            <p className="text-sm text-slate-600">{processos.length} {processos.length === 1 ? "mapa" : "mapas"} · {achados.length} {achados.length === 1 ? "achado" : "achados"} · {evidencias.length} {evidencias.length === 1 ? "evidência" : "evidências"} · {dores.length} {dores.length === 1 ? "dor" : "dores"}</p>
          </div>
        </div>
      </div>
      {arvore.length
        ? <div className="panel-rows">{arvore.map(renderLinha)}</div>
        // A mesma frase que a `AccountDetailPage` já usa na seção "Processos mapeados": sem
        // Discovery não há o que publicar, e a tela não inventa uma segunda redação para o mesmo
        // vazio.
        : <div className="p-5 sm:p-6"><p className="empty-state">Nenhum processo mapeado para esta conta.</p></div>}
    </section>

    {/* A oportunidade é o **topo da escada** e agrupa dores de mais de um mapa: pendurá-la sob um
        deles afirmaria uma origem única que ela não tem (decisão C1). */}
    <section className="panel panel--flush">
      <div className="panel-heading">
        <div className="flex min-w-0 items-center gap-3">
          <span className="metric-icon"><Target className="size-4" /></span>
          <div>
            <h2 className="font-semibold text-ink">Improvement Opportunities</h2>
            <p className="text-sm text-slate-600">O topo da escada — agrupa dores de mais de um mapa, e por isso fica fora da árvore</p>
          </div>
        </div>
      </div>
      {linhasDeOportunidade.length
        ? <div className="panel-rows">{linhasDeOportunidade.map(renderLinha)}</div>
        : <div className="p-5 sm:p-6"><p className="empty-state">Nenhuma Improvement Opportunity nesta conta. O agrupamento de dores mora na priorização.</p></div>}
    </section>
  </section>;
}
