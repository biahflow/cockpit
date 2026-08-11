import { Plus, Save, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import type { Service, ServiceTier } from "../types";

const tiers: { value: ServiceTier; label: string }[] = [
  { value: "", label: "Serviço avulso" },
  { value: "discovery_express", label: "Discovery Express" },
  { value: "discovery_assessment", label: "Discovery + Assessment" },
  { value: "implantacao", label: "Implantação" },
];
const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function ServicesPage() {
  const [services, setServices] = useState<Service[]>([]);
  const [name, setName] = useState("");
  const [tier, setTier] = useState<ServiceTier>("");
  const [error, setError] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [isCreating, setCreating] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [archiving, setArchiving] = useState<Service | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);

  const load = useCallback(
    () => api<Service[]>("/services/").then(setServices).catch((cause: Error) => setError(cause.message)).finally(() => setLoading(false)),
    [],
  );
  useEffect(() => { void load(); }, [load]);

  function updateLocal(id: number, patch: Partial<Service>) {
    setServices(prev => prev.map(service => service.id === id ? { ...service, ...patch } : service));
  }
  async function save(service: Service) {
    setError(""); setSavingId(service.id);
    try { await api(`/services/${service.id}/`, { method: "PATCH", body: JSON.stringify({ name: service.name, active: service.active, tier: service.tier, list_price: service.list_price, summary: service.summary }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setSavingId(null); }
  }
  async function archive() {
    if (!archiving) return;
    setError(""); setArchiveBusy(true);
    try { await api(`/services/${archiving.id}/`, { method: "DELETE" }); setArchiving(null); await load(); }
    catch (cause) { setArchiving(null); setError((cause as Error).message); }
    finally { setArchiveBusy(false); }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setCreating(true);
    try { await api("/services/", { method: "POST", body: JSON.stringify({ name, tier }) }); setName(""); setTier(""); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setCreating(false); }
  }

  const levels = services.filter(service => service.tier);
  const loose = services.filter(service => !service.tier);

  if (isLoading) return <p className="text-sm text-slate-600">Carregando serviços…</p>;

  return <section className="space-y-7">
    {archiving && <ConfirmDialog
      title="Arquivar serviço"
      message={<>O serviço <strong className="text-ink">{archiving.name}</strong> sai do catálogo e deixa de ser oferecido em novas oportunidades. As que já o usam continuam intactas.</>}
      confirmLabel="Arquivar"
      busy={archiveBusy}
      onCancel={() => setArchiving(null)}
      onConfirm={() => void archive()}
    />}
    <header className="page-head"><p className="eyebrow">Gestão</p><h1>Serviços e níveis de produto</h1><p>Os três níveis conduzem o pipeline, a proposta e o cronograma inicial do projeto. Serviços avulsos entram só no ROI por serviço.</p></header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <section className="space-y-4">
      <h2 className="font-semibold text-ink">Níveis de produto</h2>
      {levels.length ? <div className="grid gap-4 lg:grid-cols-3">{levels.map(service => <article className="panel grid gap-3 sm:p-6" key={service.id}>
        <p className="eyebrow">{service.tier_display}</p>
        <label className="form-label">Nome<input className="field" value={service.name} onChange={event => updateLocal(service.id, { name: event.target.value })} aria-label={`Nome do serviço ${service.id}`} /></label>
        <label className="form-label">Preço de tabela<input className="field" type="number" min="0" step="0.01" value={service.list_price} onChange={event => updateLocal(service.id, { list_price: event.target.value })} aria-label={`Preço de ${service.name}`} /></label>
        <p className="-mt-1 text-xs text-muted">{Number(service.list_price) === 0 ? "Gratuito — porta de entrada da metodologia." : money.format(Number(service.list_price))}</p>
        <label className="form-label">O que está incluso<textarea className="field min-h-24" value={service.summary} onChange={event => updateLocal(service.id, { summary: event.target.value })} aria-label={`Escopo de ${service.name}`} placeholder="Alimenta a proposta gerada pela IA" /></label>
        <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={service.active} onChange={event => updateLocal(service.id, { active: event.target.checked })} />Disponível para venda</label>
        <button className="btn" disabled={savingId === service.id} onClick={() => void save(service)}><Save className="size-4" />{savingId === service.id ? "Salvando…" : "Salvar"}</button>
      </article>)}</div> : <p className="empty-state">Nenhum nível de produto configurado.</p>}
    </section>

    <section className="panel panel--flush">
      <div className="panel-heading"><h2>Serviços avulsos</h2></div>
      {loose.length ? <div className="panel-rows">{loose.map(service => <div className="row gap-3 py-3" key={service.id}>
        <input className="field max-w-64 flex-1" value={service.name} onChange={event => updateLocal(service.id, { name: event.target.value })} aria-label={`Nome do serviço ${service.id}`} />
        <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={service.active} onChange={event => updateLocal(service.id, { active: event.target.checked })} />Ativo</label>
        <button className="btn" disabled={savingId === service.id} onClick={() => void save(service)}><Save className="size-4" />{savingId === service.id ? "Salvando…" : "Salvar"}</button>
        {/* "Arquivar", não "Excluir": o DELETE grava `archived_at` e o registro continua no banco.
            O repo já reserva "Excluir" para o hard delete de etapa e fase da jornada. */}
        <button className="btn btn--icon-danger" aria-label={`Arquivar serviço ${service.name}`} onClick={() => setArchiving(service)}><Trash2 className="size-4" /></button>
      </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-muted">Nenhum serviço avulso ainda.</p>}
    </section>

    <form className="toolbar" onSubmit={event => void create(event)}>
      <label className="form-label">Novo serviço<input className="field w-64" value={name} onChange={event => setName(event.target.value)} placeholder="Ex.: Consultoria de IA" required /></label>
      <label className="form-label">Nível<select className="field w-56" value={tier} onChange={event => setTier(event.target.value as ServiceTier)}>{tiers.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <button className="btn" disabled={isCreating} type="submit"><Plus className="size-4" />{isCreating ? "Adicionando…" : "Adicionar serviço"}</button>
    </form>
  </section>;
}
