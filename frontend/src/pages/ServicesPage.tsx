import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { Service } from "../types";

export function ServicesPage() {
  const [services, setServices] = useState<Service[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => api<Service[]>("/services/").then(setServices).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);

  function updateLocal(id: number, patch: Partial<Service>) {
    setServices(prev => prev.map(service => service.id === id ? { ...service, ...patch } : service));
  }
  async function save(service: Service) {
    setError("");
    try { await api(`/services/${service.id}/`, { method: "PATCH", body: JSON.stringify({ name: service.name, active: service.active }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function remove(id: number) {
    setError("");
    try { await api(`/services/${id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/services/", { method: "POST", body: JSON.stringify({ name }) }); setName(""); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="space-y-7">
    <a href="/indicadores" className="inline-flex items-center gap-2 text-sm font-semibold text-ocean hover:text-ink"><ArrowLeft className="size-4" />Voltar para indicadores</a>
    <header><p className="text-sm font-semibold text-ocean">Gestão</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Serviços</h1><p className="mt-2 text-sm text-slate-500">Categorias usadas nos projetos e no ROI por serviço.</p></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}

    <section className="overflow-hidden rounded-2xl border bg-white">
      <div className="border-b px-5 py-4 sm:px-6"><h2 className="font-semibold text-ink">Serviços cadastrados</h2></div>
      {services.length ? <div className="divide-y">{services.map(service => <div className="flex flex-wrap items-center gap-3 px-5 py-3 sm:px-6" key={service.id}>
        <input className="field max-w-64 flex-1" value={service.name} onChange={event => updateLocal(service.id, { name: event.target.value })} aria-label={`Nome do serviço ${service.id}`} />
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={service.active} onChange={event => updateLocal(service.id, { active: event.target.checked })} />Ativo</label>
        <button className="inline-flex items-center gap-1.5 rounded-xl bg-ocean px-3 py-2 text-sm font-semibold text-white hover:bg-ink" onClick={() => void save(service)}><Save className="size-4" />Salvar</button>
        <button className="grid size-9 place-items-center rounded-xl border text-slate-400 hover:bg-red-50 hover:text-signal" aria-label={`Excluir serviço ${service.name}`} onClick={() => void remove(service.id)}><Trash2 className="size-4" /></button>
      </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-400">Nenhum serviço ainda.</p>}
    </section>

    <form className="flex flex-wrap items-end gap-3 rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void create(event)}>
      <label className="grid gap-2 text-sm font-medium text-slate-700">Novo serviço<input className="field w-64" value={name} onChange={event => setName(event.target.value)} placeholder="Ex.: Consultoria de IA" required /></label>
      <button className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><Plus className="size-4" />Adicionar serviço</button>
    </form>
  </section>;
}
