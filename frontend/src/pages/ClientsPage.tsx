import { Building2, Plus, RotateCcw, Search } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { StatusDot } from "../components/StatusDot";
import type { Client, ClientOverview, ClientStatus } from "../types";

type Filter = "all" | ClientStatus | "archived";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "active", label: "Ativos" },
  { key: "prospect", label: "Prospects" },
  { key: "archived", label: "Arquivados" },
];

// Vazio por filtro, e não um texto só: "cadastre o primeiro cliente" ao lado de uma base que tem
// clientes faz a tela mentir — e manda fazer algo que não encheria o filtro. Cada aba explica a
// regra que a deixa vazia.
const EMPTY: Record<Filter, { title: string; hint: string }> = {
  all: { title: "Sua base começa aqui", hint: "Cadastre o primeiro cliente ao lado." },
  active: { title: "Nenhum cliente ativo", hint: "Ativo é quem já fechou: um prospect vira ativo quando a oportunidade dele é ganha, ou você marca no cadastro que ele já é cliente." },
  prospect: { title: "Nenhum prospect", hint: "Prospect é quem ainda não fechou — entra pelo cadastro ao lado ou pela conversão de um lead." },
  archived: { title: "Nada arquivado", hint: "Clientes arquivados aparecem aqui e podem voltar para a base a qualquer momento." },
};

export function ClientsPage() {
  const [clients, setClients] = useState<ClientOverview[]>([]);
  const [name, setName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [status, setStatus] = useState<ClientStatus>("prospect");
  const [error, setError] = useState("");
  const [isCreating, setCreating] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [archived, setArchived] = useState<Client[]>([]);
  const [restoring, setRestoring] = useState<number | null>(null);
  // A aba Arquivados fala com `/clients/?archived=1`, não com `/clients/overview/`: o overview é
  // agregador montado à mão e não passa pelo `get_queryset` do `ArchiveModelViewSet`, então nunca
  // enxergaria o arquivado. Saúde e jornada também não fazem sentido para quem saiu da base.
  const load = useCallback(() => {
    if (filter === "archived") {
      return api<Client[]>("/clients/?archived=1").then(setArchived).catch((cause: Error) => setError(cause.message));
    }
    return api<{ clients: ClientOverview[] }>(`/clients/overview/${filter === "all" ? "" : `?status=${filter}`}`).then(result => setClients(result.clients)).catch((cause: Error) => setError(cause.message));
  }, [filter]);
  useEffect(() => { void load(); }, [load]);
  async function restore(id: number) {
    setError(""); setRestoring(id);
    try { await api(`/clients/${id}/unarchive/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setRestoring(null); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setCreating(true); try { await api<Client>("/clients/", { method: "POST", body: JSON.stringify({ name, legal_name: legalName, tax_id: taxId, status }) }); setName(""); setLegalName(""); setTaxId(""); setStatus("prospect"); await load(); } catch (cause) { setError((cause as Error).message); } finally { setCreating(false); } }

  return <section className="space-y-7"><header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-accent">Relacionamento</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Clientes</h1><p className="mt-2 text-sm text-slate-600">Mantenha a base que sustenta seus projetos.</p></div><span className="rounded-xl bg-accent-50 px-3 py-2 text-sm font-semibold text-accent">{filter === "archived" ? `${archived.length} arquivados` : `${clients.length} cadastrados`}</span></header>{error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-danger">{error}</p>}
    <div className="grid gap-5 lg:grid-cols-[.72fr_1.28fr]"><form className="rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void submit(event)}><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-accent-50 text-accent"><Plus className="size-5" /></span><div><h2 className="font-semibold text-ink">Novo cliente</h2><p className="text-sm text-slate-600">Comece pelo nome principal.</p></div></div><label className="mt-6 grid gap-2 text-sm font-medium text-slate-700">Nome do cliente<input className="field" value={name} onChange={event => setName(event.target.value)} placeholder="Ex.: Empresa Exemplo" required /></label><label className="mt-4 grid gap-2 text-sm font-medium text-slate-700">Razão social<input className="field" value={legalName} onChange={event => setLegalName(event.target.value)} placeholder="Opcional" /></label><label className="mt-4 grid gap-2 text-sm font-medium text-slate-700">CNPJ / CPF<input className="field" value={taxId} onChange={event => setTaxId(event.target.value)} placeholder="Opcional" /></label><label className="mt-4 grid gap-2 text-sm font-medium text-slate-700">Situação<select className="field" value={status} onChange={event => setStatus(event.target.value as ClientStatus)}><option value="prospect">Prospect — ainda não fechou</option><option value="active">Cliente ativo — já fechou</option></select></label><button className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60" disabled={isCreating} type="submit"><Plus className="size-4" />{isCreating ? "Cadastrando…" : "Cadastrar cliente"}</button></form>
      <section className="overflow-hidden rounded-2xl border bg-white"><div className="flex items-center justify-between border-b px-5 py-5 sm:px-6"><div className="flex items-center gap-2"><span className="grid size-9 place-items-center rounded-xl bg-slate-50 text-slate-600"><Search className="size-4" /></span><h2 className="font-semibold text-ink">Base de clientes</h2></div><div className="flex gap-1 rounded-xl bg-slate-50 p-1">{FILTERS.map(option => <button key={option.key} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${filter === option.key ? "bg-white text-accent shadow-sm" : "text-slate-600 hover:text-ink"}`} onClick={() => setFilter(option.key)}>{option.label}</button>)}</div></div>{filter === "archived"
        ? (archived.length ? <div className="divide-y">{archived.map(client => <div className="flex items-center gap-4 px-5 py-4 sm:px-6" key={client.id}><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-500"><Building2 className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-slate-600">{client.name}</p><p className="mt-0.5 text-xs text-slate-500">Arquivado</p></div><button className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold text-accent hover:border-accent disabled:opacity-60" disabled={restoring === client.id} onClick={() => void restore(client.id)}><RotateCcw className="size-4" />{restoring === client.id ? "Restaurando…" : "Restaurar"}</button></div>)}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-50 text-accent"><Building2 className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">{EMPTY.archived.title}</p><p className="mt-1 max-w-sm text-sm text-slate-600">{EMPTY.archived.hint}</p></div></div>)
        : clients.length ? <div className="divide-y">{clients.map(client => <a href={`/clientes/${client.client_id}`} className="flex items-center gap-4 px-5 py-4 transition hover:bg-slate-50/70 sm:px-6" key={client.client_id}><StatusDot level={client.health?.level ?? null} /><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-600"><Building2 className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{client.name}</p><p className="mt-0.5 text-xs text-slate-600">{client.phase ? `Jornada · ${client.phase.name}` : "Sem jornada ativa"}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${client.status === "prospect" ? "bg-slate-100 text-slate-600" : "bg-accent-50 text-accent"}`}>{client.status === "prospect" ? "Prospect" : "Ativo"}</span></a>)}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-50 text-accent"><Building2 className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">{EMPTY[filter].title}</p><p className="mt-1 max-w-sm text-sm text-slate-600">{EMPTY[filter].hint}</p></div></div>}</section></div>
  </section>;
}
