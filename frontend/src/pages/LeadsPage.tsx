import { ArrowRight, Building2, Inbox, Landmark, Mail, MessageSquare, Phone, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import type { Lead, LeadFit, LeadStatus } from "../types";

const statusLabel: Record<LeadStatus, string> = { new: "Novo", contacted: "Contatado", qualified: "Qualificado", discarded: "Descartado" };
const fitLabel: Record<Exclude<LeadFit, "">, string> = { high: "Fit alto", medium: "Fit médio", low: "Fit baixo" };
// Variantes de `.state`, não as cores delas: um `bg-emerald-50` escrito aqui é uma segunda
// definição de "concluído", e ela diverge da primeira sem nada ficar vermelho.
const fitCls: Record<Exclude<LeadFit, "">, string> = {
  high: "state--1",
  medium: "state--2",
  low: "state--off",
};
const statusCls: Record<LeadStatus, string> = {
  new: "state--0",
  contacted: "state--2",
  qualified: "state--1",
  discarded: "state--off",
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
    <header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Comercial</p><h1>Leads</h1><p>Contatos recebidos pelo site. Triê e converta em oportunidades.</p></div><span className="self-start rounded-xl bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-700 sm:self-auto">{newCount} novos</span></header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <div className="filter-bar">{filters.map(value => <button key={value} className={`filter-chip${filter === value ? " filter-chip--on" : ""}`} onClick={() => setFilter(value)}>{value === "all" ? "Todos" : value === "archived" ? "Arquivados" : statusLabel[value]}</button>)}</div>

    {visible.length ? <div className="grid gap-4">{visible.map(lead => <article className="panel sm:p-6" key={lead.id}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><h2 className="text-base font-semibold text-ink">{lead.name}</h2><div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">{lead.company && <span className="flex items-center gap-1.5"><Building2 className="size-3.5" />{lead.company}</span>}<span className="flex items-center gap-1.5"><Mail className="size-3.5" />{lead.email}</span>{lead.phone && <span className="flex items-center gap-1.5"><Phone className="size-3.5" />{lead.phone}</span>}{lead.enrichment?.cnae_label && <span className="flex items-center gap-1.5" title={`Cadastro público · CNPJ ${lead.enrichment.cnpj || lead.cnpj}`}><Landmark className="size-3.5" />{lead.enrichment.cnae_label}{lead.enrichment.size ? ` · ${lead.enrichment.size}` : ""}</span>}</div></div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {lead.ai_fit && <span className={`state ${fitCls[lead.ai_fit]}`}>{fitLabel[lead.ai_fit]}{lead.ai_score !== null ? ` · ${lead.ai_score}` : ""}</span>}
          <span className={`state ${statusCls[lead.status]}`}>{statusLabel[lead.status]}</span>
        </div>
      </div>
      {lead.ai_summary && <p className="mt-3 flex gap-2 rounded-xl bg-brand-50/60 p-3 text-sm text-brand-700"><Sparkles className="mt-0.5 size-4 shrink-0" />{lead.ai_summary}{lead.ai_recommended_action && <span className="text-muted"> — {lead.ai_recommended_action}</span>}</p>}
      {lead.message && <p className="mt-3 flex gap-2 rounded-xl bg-slate-50 p-3 text-sm text-muted"><MessageSquare className="mt-0.5 size-4 shrink-0 text-muted" />{lead.message}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {filter === "archived" ? <button className="btn btn--secondary" disabled={restoring === lead.id} onClick={() => void restore(lead.id)}><RotateCcw className="size-4" />{restoring === lead.id ? "Restaurando…" : "Restaurar"}</button> : <>
        <select className="field w-40" value={lead.status} onChange={event => void changeStatus(lead.id, event.target.value as LeadStatus)} aria-label={`Status do lead ${lead.name}`}>{(Object.keys(statusLabel) as LeadStatus[]).map(value => <option key={value} value={value}>{statusLabel[value]}</option>)}</select>
        {lead.opportunity ? <span className="state state--1">Convertido</span> : <button className="btn" onClick={() => void convert(lead.id)}>Converter em oportunidade <ArrowRight className="size-4" /></button>}
        <button className="btn btn--icon-danger ml-auto" aria-label={`Arquivar lead ${lead.name}`} onClick={() => setArchiving(lead)}><Trash2 className="size-4" /></button>
        </>}
      </div>
    </article>)}</div> : <div className="panel grid min-h-56 place-items-center p-6 text-center"><div><span className="metric-icon mx-auto size-11"><Inbox className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">Nenhum lead {filter === "all" ? "recebido" : filter === "archived" ? "arquivado" : "neste status"}</p><p className="mt-1 text-sm text-muted">Leads enviados pelo formulário do site aparecem aqui.</p></div></div>}
  </section>;
}
