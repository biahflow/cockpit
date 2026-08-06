import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import type { JourneyPhaseTemplate } from "../types";

export function JourneyConfigPage() {
  const [phases, setPhases] = useState<JourneyPhaseTemplate[]>([]);
  const [phaseDraft, setPhaseDraft] = useState({ name: "", description: "", position: "" });
  const [deliverableDraft, setDeliverableDraft] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [removingPhase, setRemovingPhase] = useState<JourneyPhaseTemplate | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  const load = useCallback(() => api<JourneyPhaseTemplate[]>("/journey-phases/").then(setPhases).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);

  function updateLocal(id: number, patch: Partial<JourneyPhaseTemplate>) {
    setPhases(prev => prev.map(phase => phase.id === id ? { ...phase, ...patch } : phase));
  }
  async function savePhase(phase: JourneyPhaseTemplate) {
    setError("");
    try { await api(`/journey-phases/${phase.id}/`, { method: "PATCH", body: JSON.stringify({ name: phase.name, description: phase.description, position: Number(phase.position) }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function removePhase() {
    if (!removingPhase) return;
    setError(""); setRemoveBusy(true);
    try { await api(`/journey-phases/${removingPhase.id}/`, { method: "DELETE" }); setRemovingPhase(null); await load(); }
    catch (cause) { setRemovingPhase(null); setError((cause as Error).message); }
    finally { setRemoveBusy(false); }
  }
  async function createPhase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/journey-phases/", { method: "POST", body: JSON.stringify({ name: phaseDraft.name, description: phaseDraft.description, position: Number(phaseDraft.position || 0) }) }); setPhaseDraft({ name: "", description: "", position: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function addDeliverable(phaseId: number) {
    const name = (deliverableDraft[phaseId] ?? "").trim();
    if (!name) return;
    setError("");
    try { await api("/phase-deliverables/", { method: "POST", body: JSON.stringify({ phase: phaseId, name, position: 0 }) }); setDeliverableDraft(prev => ({ ...prev, [phaseId]: "" })); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function removeDeliverable(id: number) {
    setError("");
    try { await api(`/phase-deliverables/${id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="space-y-7">
    {removingPhase && <ConfirmDialog
      title="Excluir fase da jornada"
      message={<>A fase <strong className="text-ink">{removingPhase.name}</strong> e os entregáveis dela são apagados de vez — aqui não há arquivamento. Projetos que já materializaram esta fase não são afetados.</>}
      confirmLabel="Excluir" busy={removeBusy}
      onCancel={() => setRemovingPhase(null)} onConfirm={() => void removePhase()}
    />}
    <a href="/configuracoes" className="inline-flex items-center gap-2 text-sm font-semibold text-ocean hover:text-ink"><ArrowLeft className="size-4" />Voltar para configurações</a>
    <header><p className="text-sm font-semibold text-ocean">Metodologia</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Jornada de Transformação</h1><p className="mt-2 text-sm text-slate-600">Nomeie e ordene as fases e seus entregáveis. Cada projeto novo herda este modelo.</p></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}

    <div className="space-y-4">{phases.map(phase => <section className="overflow-hidden rounded-2xl border bg-white" key={phase.id}>
      <div className="flex flex-wrap items-center gap-3 border-b bg-slate-50/60 px-5 py-4 sm:px-6">
        <input className="field max-w-56 flex-1" value={phase.name} onChange={event => updateLocal(phase.id, { name: event.target.value })} aria-label={`Nome da fase ${phase.id}`} />
        <input className="field w-20" type="number" value={phase.position} onChange={event => updateLocal(phase.id, { position: Number(event.target.value) })} aria-label={`Ordem da fase ${phase.id}`} />
        <button className="inline-flex items-center gap-1.5 rounded-xl bg-ocean px-3 py-2 text-sm font-semibold text-white hover:bg-ink" onClick={() => void savePhase(phase)}><Save className="size-4" />Salvar</button>
        <button className="grid size-9 place-items-center rounded-xl border text-slate-600 hover:bg-red-50 hover:text-signal" aria-label={`Excluir fase ${phase.name}`} onClick={() => setRemovingPhase(phase)}><Trash2 className="size-4" /></button>
      </div>
      <div className="px-5 py-4 sm:px-6">
        <input className="field mb-4" value={phase.description} placeholder="Descrição da fase (opcional)" onChange={event => updateLocal(phase.id, { description: event.target.value })} aria-label={`Descrição da fase ${phase.name}`} />
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">Entregáveis</p>
        <div className="divide-y">{phase.deliverables.map(deliverable => <div className="flex items-center gap-3 py-2" key={deliverable.id}>
          <span className="flex-1 text-sm text-ink">{deliverable.name}</span>
          <button className="grid size-8 place-items-center rounded-lg border text-slate-600 hover:bg-red-50 hover:text-signal" aria-label={`Excluir entregável ${deliverable.name}`} onClick={() => void removeDeliverable(deliverable.id)}><Trash2 className="size-3.5" /></button>
        </div>)}</div>
        <form className="mt-3 flex gap-2" onSubmit={event => { event.preventDefault(); void addDeliverable(phase.id); }}>
          <input className="field" value={deliverableDraft[phase.id] ?? ""} placeholder="Novo entregável" onChange={event => setDeliverableDraft(prev => ({ ...prev, [phase.id]: event.target.value }))} aria-label={`Novo entregável da fase ${phase.name}`} />
          <button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label={`Adicionar entregável à fase ${phase.name}`} type="submit"><Plus className="size-4" /></button>
        </form>
      </div>
    </section>)}</div>

    <form className="flex flex-wrap items-end gap-3 rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void createPhase(event)}>
      <label className="grid gap-2 text-sm font-medium text-slate-700">Nova fase<input className="field w-56" value={phaseDraft.name} onChange={event => setPhaseDraft({ ...phaseDraft, name: event.target.value })} placeholder="Ex.: Activation" required /></label>
      <label className="grid gap-2 text-sm font-medium text-slate-700">Ordem<input className="field w-20" type="number" value={phaseDraft.position} onChange={event => setPhaseDraft({ ...phaseDraft, position: event.target.value })} placeholder="0" /></label>
      <button className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><Plus className="size-4" />Adicionar fase</button>
    </form>
  </section>;
}
