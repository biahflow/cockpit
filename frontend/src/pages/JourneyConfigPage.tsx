import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import { GATE_DECISION_LABEL, gateDecisionByEffect, gateDecisions } from "../journey";
import type { JourneyPhaseTemplate } from "../types";

export function JourneyConfigPage() {
  const [phases, setPhases] = useState<JourneyPhaseTemplate[]>([]);
  const [phaseDraft, setPhaseDraft] = useState({ name: "", description: "", position: "" });
  const [deliverableDraft, setDeliverableDraft] = useState<Record<number, string>>({});
  const [checklistDraft, setChecklistDraft] = useState<Record<number, string>>({});
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
    try { await api(`/journey-phases/${phase.id}/`, { method: "PATCH", body: JSON.stringify({ name: phase.name, description: phase.description, position: Number(phase.position), active: phase.active, requires_gate: phase.requires_gate }) }); await load(); }
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
  // O checklist é o **quality gate** da fase, e não uma segunda lista de entregáveis: o
  // entregável é o que sai daqui, o item de checklist é a condição para que possa sair (FDD 033).
  async function addChecklistItem(phaseId: number) {
    const text = (checklistDraft[phaseId] ?? "").trim();
    if (!text) return;
    setError("");
    try { await api("/phase-checklist-items/", { method: "POST", body: JSON.stringify({ phase: phaseId, text, position: 0 }) }); setChecklistDraft(prev => ({ ...prev, [phaseId]: "" })); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function removeChecklistItem(id: number) {
    setError("");
    try { await api(`/phase-checklist-items/${id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="space-y-7">
    {removingPhase && <ConfirmDialog
      title="Excluir fase da jornada"
      message={<>A fase <strong className="text-ink">{removingPhase.name}</strong> e os entregáveis dela são apagados de vez — aqui não há arquivamento. Só é possível excluir fase que nenhum projeto materializou; para aposentar uma fase em uso, desmarque <strong className="text-ink">Herdada por projetos novos</strong> e salve.</>}
      confirmLabel="Excluir" busy={removeBusy}
      onCancel={() => setRemovingPhase(null)} onConfirm={() => void removePhase()}
    />}
    <a href="/configuracoes" className="back-link"><ArrowLeft className="size-4" />Voltar para configurações</a>
    <header className="page-head"><p className="eyebrow">Metodologia</p><h1>Jornada de Transformação</h1><p>Nomeie e ordene as fases, seus entregáveis e o checklist de qualidade; marque as que terminam em decision gate. Cada projeto novo herda este modelo.</p></header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <div className="space-y-4">{phases.map(phase => <section className="panel panel--flush" key={phase.id}>
      <div className="row border-b border-line bg-slate-50/60 gap-3">
        <input className="field max-w-56 flex-1" value={phase.name} onChange={event => updateLocal(phase.id, { name: event.target.value })} aria-label={`Nome da fase ${phase.id}`} />
        <input className="field w-20" type="number" value={phase.position} onChange={event => updateLocal(phase.id, { position: Number(event.target.value) })} aria-label={`Ordem da fase ${phase.id}`} />
        <button className="btn" onClick={() => void savePhase(phase)}><Save className="size-4" />Salvar</button>
        <button className="btn btn--icon-danger" aria-label={`Excluir fase ${phase.name}`} onClick={() => setRemovingPhase(phase)}><Trash2 className="size-4" /></button>
      </div>
      <div className="px-5 py-4 sm:px-6">
        <div className="mb-4 flex flex-wrap gap-x-6 gap-y-2">
          <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" className="size-4 rounded border-slate-300 text-brand-500" checked={phase.active} onChange={event => updateLocal(phase.id, { active: event.target.checked })} />Herdada por projetos novos</label>
          <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" className="size-4 rounded border-slate-300 text-brand-500" checked={phase.requires_gate} onChange={event => updateLocal(phase.id, { requires_gate: event.target.checked })} />Termina em decision gate</label>
        </div>
        {!phase.active && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm text-slate-700">Fase aposentada: não entra em projeto novo. Os projetos que já passaram por ela continuam com a delas.</p>}
        {/* O aviso nomeia o vocabulário **desta** fase (ADR 0053): a classificação canônica é
            que diz se o gate é o da Feasibility (quatro saídas) ou o do PROVE (três). Dizer as
            quatro numa fase de PROVE mandaria a equipe procurar um botão que a tela não oferece. */}
        {phase.requires_gate && <p className="mb-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">A equipe precisa registrar {gateDecisions(phase.canonical_stage).map(decision => GATE_DECISION_LABEL[decision]).join(" / ")} para fechar esta fase. {GATE_DECISION_LABEL[gateDecisionByEffect(phase.canonical_stage, "reopen")]} reabre a fase anterior; {GATE_DECISION_LABEL[gateDecisionByEffect(phase.canonical_stage, "halt")]} para a jornada aqui.</p>}
        <input className="field mb-4" value={phase.description} placeholder="Descrição da fase (opcional)" onChange={event => updateLocal(phase.id, { description: event.target.value })} aria-label={`Descrição da fase ${phase.name}`} />
        <p className="eyebrow mb-2">Entregáveis</p>
        <div className="divide-y divide-line">{phase.deliverables.map(deliverable => <div className="flex items-center gap-3 py-2" key={deliverable.id}>
          <span className="flex-1 text-sm text-ink">{deliverable.name}</span>
          <button className="btn btn--icon-danger size-8 rounded-lg" aria-label={`Excluir entregável ${deliverable.name}`} onClick={() => void removeDeliverable(deliverable.id)}><Trash2 className="size-3.5" /></button>
        </div>)}</div>
        <form className="mt-3 flex gap-2" onSubmit={event => { event.preventDefault(); void addDeliverable(phase.id); }}>
          <input className="field" value={deliverableDraft[phase.id] ?? ""} placeholder="Novo entregável" onChange={event => setDeliverableDraft(prev => ({ ...prev, [phase.id]: event.target.value }))} aria-label={`Novo entregável da fase ${phase.name}`} />
          <button className="btn btn--icon" aria-label={`Adicionar entregável à fase ${phase.name}`} type="submit"><Plus className="size-4" /></button>
        </form>
        <p className="eyebrow mb-2 mt-5">Checklist de qualidade</p>
        <div className="divide-y divide-line">{phase.checklist_items.map(item => <div className="flex items-center gap-3 py-2" key={item.id}>
          <span className="flex-1 text-sm text-ink">{item.text}</span>
          <button className="btn btn--icon-danger size-8 rounded-lg" aria-label={`Excluir item ${item.text}`} onClick={() => void removeChecklistItem(item.id)}><Trash2 className="size-3.5" /></button>
        </div>)}</div>
        <form className="mt-3 flex gap-2" onSubmit={event => { event.preventDefault(); void addChecklistItem(phase.id); }}>
          <input className="field" value={checklistDraft[phase.id] ?? ""} placeholder="Nova pergunta (ex.: Baseline definido?)" onChange={event => setChecklistDraft(prev => ({ ...prev, [phase.id]: event.target.value }))} aria-label={`Novo item do checklist da fase ${phase.name}`} />
          <button className="btn btn--icon" aria-label={`Adicionar item ao checklist da fase ${phase.name}`} type="submit"><Plus className="size-4" /></button>
        </form>
      </div>
    </section>)}</div>

    <form className="toolbar" onSubmit={event => void createPhase(event)}>
      <label className="form-label">Nova fase<input className="field w-56" value={phaseDraft.name} onChange={event => setPhaseDraft({ ...phaseDraft, name: event.target.value })} placeholder="Ex.: Activation" required /></label>
      <label className="form-label">Ordem<input className="field w-20" type="number" value={phaseDraft.position} onChange={event => setPhaseDraft({ ...phaseDraft, position: event.target.value })} placeholder="0" /></label>
      <button className="btn" type="submit"><Plus className="size-4" />Adicionar fase</button>
    </form>
  </section>;
}
