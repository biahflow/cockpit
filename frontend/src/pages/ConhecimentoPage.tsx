import { AlertTriangle, BookOpen, CircleHelp, UserX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import type { KnowledgeArea, KnowledgePiece, KnowledgeStatus, KnowledgeSummary } from "../types";

const statusLabel: Record<KnowledgeStatus, string> = {
  sem_dono: "Sem dono", vencido: "Vencido", a_vencer: "A vencer", corrente: "Corrente",
};

const statusTone: Record<KnowledgeStatus, string> = {
  sem_dono: "bg-red-50 text-danger",
  vencido: "bg-red-50 text-danger",
  a_vencer: "bg-amber-50 text-amber-800",
  corrente: "bg-emerald-50 text-emerald-800",
};

const formatDate = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR");

export function ConhecimentoPage() {
  const { user } = useAuth();
  const [pieces, setPieces] = useState<KnowledgePiece[]>([]);
  const [areas, setAreas] = useState<KnowledgeArea[]>([]);
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [busy, setBusy] = useState(0);
  const [error, setError] = useState("");
  const [isLoading, setLoading] = useState(true);

  const load = useCallback(() => {
    const query = statusFilter ? `?status=${statusFilter}` : "";
    return Promise.all([
      api<KnowledgePiece[]>(`/knowledge-pieces/${query}`).then(setPieces),
      api<KnowledgeSummary>("/knowledge-pieces/summary/").then(setSummary),
      api<KnowledgeArea[]>("/knowledge-areas/").then(setAreas),
    ])
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  useEffect(() => { void load(); }, [load]);

  async function verificar(piece: KnowledgePiece) {
    setError(""); setBusy(piece.id);
    try { await api(`/knowledge-pieces/${piece.id}/verify/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(0); }
  }

  if (isLoading) return <p className="text-sm text-slate-600">Carregando o inventário…</p>;

  const semDono = areas.filter(area => area.owner === null);
  const lacunas = pieces.filter(piece => piece.is_gap);
  const comArquivo = pieces.filter(piece => !piece.is_gap);
  const podeVerificar = (piece: KnowledgePiece) =>
    Boolean(user?.is_admin) || piece.owner_name === `${user?.first_name} ${user?.last_name}`.trim();

  return <section className="space-y-7">
    <header>
      <p className="text-sm font-semibold text-accent">Metodologia</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Conhecimento</h1>
      <p className="mt-2 text-sm text-slate-600">Quem responde por quê, e o que já venceu. É deste material que os agentes tiram resposta com fonte — e é por isso que peça velha servida como corrente é pior que peça nenhuma.</p>
    </header>

    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-danger">{error}</p>}

    <div className="grid gap-4 sm:grid-cols-4">
      {(["sem_dono", "vencido", "a_vencer", "corrente"] as KnowledgeStatus[]).map(estado =>
        <article key={estado} className="rounded-2xl border bg-white p-5">
          <p className="text-sm font-medium text-slate-600">{statusLabel[estado]}</p>
          <p className={`mt-1 text-2xl font-semibold ${estado === "corrente" ? "text-ink" : estado === "a_vencer" ? "text-amber-800" : "text-danger"}`}>{summary?.[estado] ?? 0}</p>
        </article>)}
    </div>

    {/* Primeiro de propósito: "peça sem dono é peça em falta", e o que falta decidir tem de ser a
        primeira coisa que aparece — não um filtro que alguém precisa lembrar de aplicar. */}
    {semDono.length > 0 && <section className="rounded-2xl border border-red-200 bg-red-50/40 p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-xl bg-red-100 text-danger"><UserX className="size-4" /></span>
        <div>
          <h2 className="font-semibold text-ink">Áreas sem dono</h2>
          <p className="text-sm text-slate-600">Sem responsável, ninguém é avisado quando o material vence. Defina o dono em cada área.</p>
        </div>
      </div>
      <ul className="mt-3 flex flex-wrap gap-2">
        {semDono.map(area => <li key={area.id} className="rounded-lg bg-white px-3 py-1.5 text-sm font-semibold text-slate-700">{area.name}</li>)}
      </ul>
    </section>}

    <div className="flex flex-wrap items-end gap-3 rounded-2xl border bg-white p-4 sm:p-5">
      <label className="grid gap-2 text-sm font-medium text-slate-700">Estado
        <select className="field w-48" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
          <option value="">Todos</option>
          {Object.entries(statusLabel).map(([valor, rotulo]) => <option key={valor} value={valor}>{rotulo}</option>)}
        </select>
      </label>
    </div>

    {comArquivo.length ? <section className="overflow-hidden rounded-2xl border bg-white">
      <div className="divide-y">
        {comArquivo.map(piece => <article key={piece.id} className="flex flex-wrap items-center gap-3 px-5 py-4 sm:px-6">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent-50 text-accent"><BookOpen className="size-4" /></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold text-ink">{piece.title}</h2>
              <span className={`rounded-lg px-2 py-0.5 text-xs font-semibold ${statusTone[piece.status]}`}>{statusLabel[piece.status]}</span>
              <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{piece.kind_display}</span>
            </div>
            <p className="mt-0.5 text-xs text-slate-600">
              {piece.area_name || "sem área"} · {piece.owner_name || "sem dono"} · {piece.source_path}
              {piece.last_verified_at ? ` · verificado em ${formatDate(piece.last_verified_at)}` : " · nunca verificado"}
              {piece.next_review_at ? ` · revisa em ${formatDate(piece.next_review_at)}` : " · não vence"}
            </p>
          </div>
          {podeVerificar(piece) && <button type="button" disabled={busy === piece.id} onClick={() => void verificar(piece)}
            className="shrink-0 rounded-xl border px-3 py-2 text-sm font-semibold text-accent hover:border-accent disabled:opacity-60">
            {busy === piece.id ? "…" : "Marcar como verificado"}
          </button>}
        </article>)}
      </div>
    </section> : <p className="rounded-2xl border bg-white p-6 text-sm text-slate-600">Nenhuma peça neste filtro. O inventário é populado por <code>manage.py ingest_knowledge</code>, a partir da metodologia versionada no repositório.</p>}

    {lacunas.length > 0 && <section className="rounded-2xl border bg-white p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-xl bg-amber-50 text-amber-800"><CircleHelp className="size-4" /></span>
        <div>
          <h2 className="font-semibold text-ink">Lacunas</h2>
          <p className="text-sm text-slate-600">O que só uma pessoa sabe fazer e ainda não está escrito. Onde alguém novo trava vira item daqui.</p>
        </div>
      </div>
      <ul className="mt-3 grid gap-2">
        {lacunas.map(piece => <li key={piece.id} className="flex items-center gap-2 text-sm text-slate-700">
          <AlertTriangle className="size-3.5 shrink-0 text-amber-700" />{piece.title}
          <span className="text-xs text-slate-600">· {piece.area_name || "sem área"}</span>
        </li>)}
      </ul>
    </section>}
  </section>;
}
