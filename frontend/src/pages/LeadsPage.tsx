import { ArrowRight, Building2, Inbox, Mail, MessageSquare, Phone, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import type { Lead, LeadFit, LeadStatus } from "../types";

const statusLabel: Record<LeadStatus, string> = { new: "Novo", contacted: "Contatado", qualified: "Qualificado", discarded: "Descartado" };
const fitLabel: Record<Exclude<LeadFit, "">, string> = { high: "Fit alto", medium: "Fit médio", low: "Fit baixo" };
const fitCls: Record<Exclude<LeadFit, "">, string> = {
  high: "bg-emerald-50 text-emerald-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};
const statusCls: Record<LeadStatus, string> = {
  new: "bg-ocean/10 text-ocean",
  contacted: "bg-amber-50 text-amber-700",
  qualified: "bg-emerald-50 text-emerald-700",
  discarded: "bg-slate-100 text-slate-600",
};
// "archived" não é status de lead: é o recorte do que saiu da lista. Entra aqui porque o diálogo
// de arquivar promete restauração, e a promessa precisava de um lugar onde ser cumprida (FDD 025).
type Filtro = LeadStatus | "all" | "archived";
const filters: Filtro[] = ["all", "new", "contacted", "qualified", "discarded", "archived"];

export function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [filter, setFilter] = useState<Filtro>("all");
  const [restoring, setRestoring] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [archiving, setArchiving] = useState<Lead | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);

  const load = useCallback(
    () => api<Lead[]>(`/leads/${filter === "archived" ? "?archived=1" : ""}`).then(setLeads).catch((cause: Error) => setError(cause.message)),
    [filter],
  );
  useEffect(() => { void load(); }, [load]);

  async function changeStatus(id: number, status: LeadStatus) {
    try { await api(`/leads/${id}/`, { method: "PATCH", body: JSON.stringify({ status }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function convert(id: number) {
    try { await api(`/leads/${id}/convert/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function restore(id: number) {
    setError(""); setRestoring(id);
    try { await api(`/leads/${id}/unarchive/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setRestoring(null); }
  }
  async function archive() {
    if (!archiving) return;
    setArchiveBusy(true);
    try { await api(`/leads/${archiving.id}/`, { method: "DELETE" }); setArchiving(null); await load(); }
    catch (cause) { setArchiving(null); setError((cause as Error).message); }
    finally { setArchiveBusy(false); }
  }

  const visible = filter === "all" || filter === "archived" ? leads : leads.filter(lead => lead.status === filter);
  const newCount = leads.filter(lead => lead.status === "new").length;

  return <section className="space-y-7">
    {archiving && <ConfirmDialog
      title="Arquivar lead"
      message={<>O lead <strong className="text-ink">{archiving.name}</strong> sai da lista. O histórico fica guardado e pode ser restaurado.</>}
      confirmLabel="Arquivar" busy={archiveBusy}
      onCancel={() => setArchiving(null)} onConfirm={() => void archive()}
    />}
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Comercial</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Leads</h1><p className="mt-2 text-sm text-slate-600">Contatos recebidos pelo site. Triê e converta em oportunidades.</p></div><span className="self-start rounded-xl bg-mint px-3 py-2 text-sm font-semibold text-ocean sm:self-auto">{newCount} novos</span></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}

    <div className="flex flex-wrap gap-2">{filters.map(value => <button key={value} className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition ${filter === value ? "bg-ocean text-white" : "border bg-white text-slate-600 hover:text-ink"}`} onClick={() => setFilter(value)}>{value === "all" ? "Todos" : value === "archived" ? "Arquivados" : statusLabel[value]}</button>)}</div>

    {visible.length ? <div className="grid gap-4">{visible.map(lead => <article className="rounded-2xl border bg-white p-5 sm:p-6" key={lead.id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><h2 className="text-base font-semibold text-ink">{lead.name}</h2><div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">{lead.company && <span className="flex items-center gap-1.5"><Building2 className="size-3.5" />{lead.company}</span>}<span className="flex items-center gap-1.5"><Mail className="size-3.5" />{lead.email}</span>{lead.phone && <span className="flex items-center gap-1.5"><Phone className="size-3.5" />{lead.phone}</span>}</div></div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {lead.ai_fit && <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${fitCls[lead.ai_fit]}`}>{fitLabel[lead.ai_fit]}{lead.ai_score !== null ? ` · ${lead.ai_score}` : ""}</span>}
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusCls[lead.status]}`}>{statusLabel[lead.status]}</span>
        </div>
      </div>
      {lead.ai_summary && <p className="mt-3 flex gap-2 rounded-xl bg-mint/50 p-3 text-sm text-ocean"><Sparkles className="mt-0.5 size-4 shrink-0" />{lead.ai_summary}{lead.ai_recommended_action && <span className="text-slate-600"> — {lead.ai_recommended_action}</span>}</p>}
      {lead.message && <p className="mt-3 flex gap-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-600"><MessageSquare className="mt-0.5 size-4 shrink-0 text-slate-600" />{lead.message}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {filter === "archived" ? <button className="inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-semibold text-ocean hover:border-ocean disabled:opacity-60" disabled={restoring === lead.id} onClick={() => void restore(lead.id)}><RotateCcw className="size-4" />{restoring === lead.id ? "Restaurando…" : "Restaurar"}</button> : <>
        <select className="field w-40" value={lead.status} onChange={event => void changeStatus(lead.id, event.target.value as LeadStatus)} aria-label={`Status do lead ${lead.name}`}>{(Object.keys(statusLabel) as LeadStatus[]).map(value => <option key={value} value={value}>{statusLabel[value]}</option>)}</select>
        {lead.opportunity ? <span className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700">Convertido</span> : <button className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-2 text-sm font-semibold text-white hover:bg-ink" onClick={() => void convert(lead.id)}>Converter em oportunidade <ArrowRight className="size-4" /></button>}
        <button className="ml-auto grid size-9 place-items-center rounded-xl border text-slate-600 hover:bg-red-50 hover:text-signal" aria-label={`Arquivar lead ${lead.name}`} onClick={() => setArchiving(lead)}><Trash2 className="size-4" /></button>
        </>}
      </div>
    </article>)}</div> : <div className="grid min-h-56 place-items-center rounded-2xl border bg-white p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-mint text-ocean"><Inbox className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">Nenhum lead {filter === "all" ? "recebido" : filter === "archived" ? "arquivado" : "neste status"}</p><p className="mt-1 text-sm text-slate-600">Leads enviados pelo formulário do site aparecem aqui.</p></div></div>}
  </section>;
}
