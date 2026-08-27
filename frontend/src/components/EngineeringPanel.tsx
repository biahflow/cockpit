import { AlertTriangle, Clock, GitBranch } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { GithubCiState, GithubIssueState, GithubPrState, GithubProjection } from "../types";

/**
 * O painel **Engenharia** do detalhe do projeto (FDD 041, DAP GH-41 r1 aprovado em 27/08/2026).
 *
 * A regra que este componente existe para cumprir: **estado obsoleto nunca veste a cor do estado
 * observado.** Quando o backend diz `is_stale`, todo selo cai para `.state--off` e a linha de
 * proveniência sobe a pastilha `.state--2` — o âmbar **troca de lugar** em vez de aparecer, para
 * continuar querendo dizer uma coisa só na tela inteira. Um selo verde que na verdade é de
 * anteontem é pior que nenhum selo: afirma com confiança algo que o Pulse não sabe mais.
 *
 * O custo está assumido e escrito no DAP: ao cair para o neutro, o painel deixa de responder "o
 * CI passou?" num relance justamente quando alguém tem pressa. A troca é deliberada.
 *
 * Somente leitura, e por decisão: reabrir Issue, re-disparar CI e reprovisionar estão desenhados
 * no DAP como **reservados** e não são renderizados aqui — nem desabilitados, nem cinzas, nem
 * escondidos atrás de menu. Controle inerte no produto é defeito, não marcador de lugar.
 */

// Mapa devolve **variante**, nunca a cor (ADR 0026). Uma segunda definição de "concluído" diverge
// da primeira em silêncio, e `src/test/primitivas.test.ts` é quem cobra isso.
const ISSUE_LABEL: Record<GithubIssueState, string> = { open: "Issue aberta", closed: "Issue fechada" };
// Em curso é informação, não sucesso nem aviso; fechada é terminal esperado.
const ISSUE_VARIANT: Record<GithubIssueState, string> = { open: "state--0", closed: "state--1" };
const PR_LABEL: Record<GithubPrState, string> = {
  none: "Sem PR", open: "PR aberto", merged: "PR merged", closed: "PR fechado sem merge",
};
// "Sem PR" é ausência de estado — o mesmo papel de "Arquivado". `merged` é terminal esperado **e
// não é `DONE`** (ADR 0040): o aceite de negócio é do One, e este painel não escreve nenhuma
// palavra de conclusão. `closed` sem merge é terminal *inesperado*: seguiu, mas há dívida — âmbar,
// não vermelho, porque não é falha do sistema.
const PR_VARIANT: Record<GithubPrState, string> = {
  none: "state--off", open: "state--0", merged: "state--1", closed: "state--2",
};
const CI_LABEL: Record<GithubCiState, string> = {
  none: "Sem check", pending: "CI rodando", success: "CI verde", failure: "CI vermelho",
};
// "Sem check" é ausência, não reprovação: pintá-lo de âmbar transformaria "não há política" em
// "há problema". `failure` é a única do painel que é vermelha por resultado.
const CI_VARIANT: Record<GithubCiState, string> = {
  none: "state--off", pending: "state--0", success: "state--1", failure: "state--3",
};
const VIA_LABEL = { webhook: "webhook", reconciliation: "reconciliação" } as const;

// Os três erros são três textos e não um, porque **a ação corretiva de cada um é diferente**:
// GitHub fora do ar passa sozinho, permissão negada exige alguém mexer no token, referência
// ausente exige consertar o vínculo. Uma copy única esconderia a diferença que decide quem age.
// Nenhum deles ecoa token, escopo concedido ou resposta da API (NFR-004).
function mensagemDeErro(projecao: GithubProjection): string {
  if (projecao.last_error_kind === "forbidden") {
    return `A credencial do Pulse não alcança ${projecao.repository}. Revise o token e o escopo da integração em Configurações.`;
  }
  if (projecao.last_error_kind === "missing") {
    return `A referência ${projecao.reference} não existe mais no GitHub. O vínculo continua registrado no Pulse e aponta para o nada.`;
  }
  return "Não foi possível falar com o GitHub. O estado abaixo é o último conhecido.";
}

/** Idade em linguagem de gente. O número vem do backend; aqui só se escolhe a unidade. */
function idade(segundos: number): string {
  if (segundos < 60) return "há instantes";
  const minutos = Math.floor(segundos / 60);
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `há ${horas} h`;
  return `há ${Math.floor(horas / 24)} d`;
}

// O sufixo que distingue "ainda estamos tentando" de "paramos de conseguir".
function sufixoDoErro(projecao: GithubProjection): string {
  if (projecao.last_error_kind === "unavailable" && projecao.last_error_age_seconds !== null) {
    return ` · última tentativa de contato ${idade(projecao.last_error_age_seconds)}`;
  }
  if (projecao.last_error_kind === "forbidden") return " · sem acesso desde então";
  return "";
}

function Selo({ variante, children }: { variante: string; children: string }) {
  return <span className={`state ${variante}`}>{children}</span>;
}

function Linha({ projecao }: { projecao: GithubProjection }) {
  // **Erro também neutraliza**, e não só a idade: os três estados de falha mostram o último
  // estado conhecido, e ele não pode continuar vestindo a cor de uma confirmação que não houve.
  const neutro = projecao.is_stale || projecao.last_error_kind !== "";
  const variante = (mapa: string) => (neutro ? "state--off" : mapa);
  const ausente = projecao.last_error_kind === "missing";
  const proveniencia = `Observado ${idade(projecao.age_seconds)} · ${VIA_LABEL[projecao.observed_via]}${sufixoDoErro(projecao)}`;

  return <li className="row">
    <div className="w-full min-w-0 space-y-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <a
          className="type-code type-body font-semibold text-brand-600 underline underline-offset-2"
          href={projecao.issue_url}
          target="_blank"
          rel="noreferrer"
        >{projecao.reference}</a>
        {projecao.issue_title && <span className="type-body min-w-0 text-ink">{projecao.issue_title}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {/* A referência apagada é o **único erro que ganha selo vermelho**, porque o defeito está
            nela mesma. Os outros três selos caem ao neutro: não há o que saber sobre eles. */}
        {ausente
          ? <Selo variante="state--3">Não encontrada (404)</Selo>
          : <Selo variante={variante(ISSUE_VARIANT[projecao.issue_state])}>{ISSUE_LABEL[projecao.issue_state]}</Selo>}
        <Selo variante={variante(PR_VARIANT[projecao.pr_state])}>{PR_LABEL[projecao.pr_state]}</Selo>
        {/* O SHA não é estado, é endereço: nunca ganha cor semântica, só a perde. Sete
            caracteres, que é como o GitHub o abrevia. */}
        <span className={`type-code type-label rounded bg-surface-subtle px-1.5 py-0.5 font-medium ${neutro ? "text-slate-600" : "text-ink"}`}>
          {projecao.head_sha ? projecao.head_sha.slice(0, 7) : "—"}
        </span>
        <Selo variante={variante(CI_VARIANT[projecao.ci_state])}>{CI_LABEL[projecao.ci_state]}</Selo>
      </div>
      {/* **Nunca se mostra estado sem dizer quando e por onde foi observado.** A linha não é
          opcional em nenhum dos oito estados, inclusive nos três de erro. */}
      {projecao.is_stale
        ? <>
            <p className="type-meta"><span className="state state--2"><Clock className="size-3" aria-hidden="true" />{proveniencia}</span></p>
            <p className="type-meta max-w-prose text-muted">Este é o <strong className="text-ink">último estado conhecido</strong>, não o estado atual.</p>
          </>
        : <p className="type-meta text-muted">{proveniencia}</p>}
    </div>
  </li>;
}

function Cabecalho() {
  return <div className="panel-heading panel-heading--icon">
    <span className="metric-icon"><GitBranch className="size-4" /></span>
    <div>
      <h2>Engenharia</h2>
      <p className="type-body text-muted">Estado observado no GitHub. O Pulse projeta; o GitHub decide.</p>
    </div>
  </div>;
}

export function EngineeringPanel({ project }: { project: number }) {
  const [projecoes, setProjecoes] = useState<GithubProjection[]>();
  const [semAcesso, setSemAcesso] = useState(false);
  const [falha, setFalha] = useState("");

  const load = useCallback(() => api<GithubProjection[]>(`/github-projections/?project=${project}`)
    .then(lista => { setProjecoes(lista); setSemAcesso(false); setFalha(""); })
    .catch((cause: { message?: string; status?: number }) => {
      setProjecoes([]);
      // 403 não é falha: é a resposta certa para quem não participa desta parte do trabalho.
      if (cause.status === 403) { setSemAcesso(true); return; }
      setFalha(cause.message || "Não foi possível carregar o estado de engenharia.");
    }), [project]);
  useEffect(() => { void load(); }, [load]);

  if (projecoes === undefined) {
    // Esqueleto sem selo colorido: um selo cinza aqui seria indistinguível do estado obsoleto.
    // O raio de cada forma acompanha o da forma real — pastilha em `full`, SHA em 4 px.
    return <section className="panel panel--flush" aria-busy="true">
      <Cabecalho />
      <div className="animate-pulse space-y-3 px-5 py-4 sm:px-6">
        <div className="h-3.5 w-1/2 rounded bg-surface-subtle" />
        <div className="flex gap-2">
          <div className="h-5 w-24 rounded-full bg-surface-subtle" />
          <div className="h-5 w-20 rounded-full bg-surface-subtle" />
          <div className="h-5 w-16 rounded bg-surface-subtle" />
        </div>
        <div className="h-2.5 w-1/3 rounded bg-surface-subtle" />
      </div>
    </section>;
  }

  // A copy do não autorizado é **invariante** — a mesma com ou sem referência —, e é por isso que
  // ela pode ser mostrada: não vaza a existência de trabalho de engenharia. Um painel que sumisse
  // por papel faria a mesma tela ter duas formas por motivo invisível (DAP GH-41 r1, decisão 6).
  const vazio = semAcesso
    ? "Estado de engenharia não faz parte do seu acesso."
    : "Nenhuma referência de GitHub neste projeto.";

  // Uma mensagem por causa distinta: duas referências fora do ar dizem a mesma coisa uma vez.
  const alertas = [...new Set(projecoes.filter(p => p.last_error_kind !== "").map(mensagemDeErro))];

  return <section className="panel panel--flush">
    <Cabecalho />
    {falha && <p role="alert" className="alert--error mx-5 mt-4 sm:mx-6">{falha}</p>}
    {alertas.map(mensagem => <p role="alert" className="alert--error mx-5 mt-4 flex gap-2 sm:mx-6" key={mensagem}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{mensagem}
    </p>)}
    {projecoes.length
      ? <ul className="panel-rows">{projecoes.map(projecao => <Linha key={projecao.id} projecao={projecao} />)}</ul>
      : <p className="empty-state mx-5 my-4 sm:mx-6">{vazio}</p>}
  </section>;
}
