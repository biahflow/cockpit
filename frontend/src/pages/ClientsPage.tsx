import { Building2, Plus, Search } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { StatusDot } from "../components/StatusDot";
import type { Client, ClientOverview, ClientStatus } from "../types";

const FILTERS: { key: "all" | ClientStatus; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "active", label: "Ativos" },
  { key: "prospect", label: "Prospects" },
];

export function ClientsPage() {
  const [clients, setClients] = useState<ClientOverview[]>([]);
  const [name, setName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [error, setError] = useState("");
  const [isCreating, setCreating] = useState(false);
  const [filter, setFilter] = useState<"all" | ClientStatus>("all");
  const load = useCallback(() => api<{ clients: ClientOverview[] }>(`/clients/overview/${filter === "all" ? "" : `?status=${filter}`}`).then(result => setClients(result.clients)).catch((cause: Error) => setError(cause.message)), [filter]);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setCreating(true); try { await api<Client>("/clients/", { method: "POST", body: JSON.stringify({ name, legal_name: legalName, tax_id: taxId }) }); setName(""); setLegalName(""); setTaxId(""); await load(); } catch (cause) { setError((cause as Error).message); } finally { setCreating(false); } }

  return <section className="space-y-7"><header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Relacionamento</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Clientes</h1><p className="mt-2 text-sm text-slate-600">Mantenha a base que sustenta seus projetos.</p></div><span className="rounded-xl bg-mint px-3 py-2 text-sm font-semibold text-ocean">{clients.length} cadastrados</span></header>{error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    <div className="grid gap-5 lg:grid-cols-[.72fr_1.28fr]"><form className="rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void submit(event)}><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-mint text-ocean"><Plus className="size-5" /></span><div><h2 className="font-semibold text-ink">Novo cliente</h2><p className="text-sm text-slate-600">Comece pelo nome principal.</p></div></div><label className="mt-6 grid gap-2 text-sm font-medium text-slate-700">Nome do cliente<input className="field" value={name} onChange={event => setName(event.target.value)} placeholder="Ex.: Empresa Exemplo" required /></label><label className="mt-4 grid gap-2 text-sm font-medium text-slate-700">Razão social<input className="field" value={legalName} onChange={event => setLegalName(event.target.value)} placeholder="Opcional" /></label><label className="mt-4 grid gap-2 text-sm font-medium text-slate-700">CNPJ / CPF<input className="field" value={taxId} onChange={event => setTaxId(event.target.value)} placeholder="Opcional" /></label><button className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60" disabled={isCreating} type="submit"><Plus className="size-4" />{isCreating ? "Cadastrando…" : "Cadastrar cliente"}</button></form>
      <section className="overflow-hidden rounded-2xl border bg-white"><div className="flex items-center justify-between border-b px-5 py-5 sm:px-6"><div className="flex items-center gap-2"><span className="grid size-9 place-items-center rounded-xl bg-slate-50 text-slate-600"><Search className="size-4" /></span><h2 className="font-semibold text-ink">Base de clientes</h2></div><div className="flex gap-1 rounded-xl bg-slate-50 p-1">{FILTERS.map(option => <button key={option.key} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${filter === option.key ? "bg-white text-ocean shadow-sm" : "text-slate-600 hover:text-ink"}`} onClick={() => setFilter(option.key)}>{option.label}</button>)}</div></div>{clients.length ? <div className="divide-y">{clients.map(client => <a href={`/clientes/${client.client_id}`} className="flex items-center gap-4 px-5 py-4 transition hover:bg-slate-50/70 sm:px-6" key={client.client_id}><StatusDot level={client.health?.level ?? null} /><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-600"><Building2 className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{client.name}</p><p className="mt-0.5 text-xs text-slate-600">{client.phase ? `Jornada · ${client.phase.name}` : "Sem jornada ativa"}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${client.status === "prospect" ? "bg-slate-100 text-slate-600" : "bg-mint text-ocean"}`}>{client.status === "prospect" ? "Prospect" : "Ativo"}</span></a>)}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-mint text-ocean"><Building2 className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">Sua base começa aqui</p><p className="mt-1 text-sm text-slate-600">Cadastre o primeiro cliente ao lado.</p></div></div>}</section></div>
  </section>;
}
