import { ArrowLeft, GripVertical, Plus, Save, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import type { PipelineStage } from "../types";

const kindLabel: Record<string, string> = { open: "Aberta", won: "Ganho", lost: "Perdido" };

export function PipelinePage() {
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [draft, setDraft] = useState({ name: "", kind: "open", position: "" });
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState<PipelineStage | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  const load = useCallback(() => api<PipelineStage[]>("/pipeline-stages/").then(setStages).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);

  function updateLocal(id: number, patch: Partial<PipelineStage>) {
    setStages(prev => prev.map(stage => stage.id === id ? { ...stage, ...patch } : stage));
  }
  async function save(stage: PipelineStage) {
    setError("");
    try { await api(`/pipeline-stages/${stage.id}/`, { method: "PATCH", body: JSON.stringify({ name: stage.name, kind: stage.kind, position: Number(stage.position) }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function remove() {
    if (!removing) return;
    setError(""); setRemoveBusy(true);
    try { await api(`/pipeline-stages/${removing.id}/`, { method: "DELETE" }); setRemoving(null); await load(); }
    catch (cause) { setRemoving(null); setError((cause as Error).message); }
    finally { setRemoveBusy(false); }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/pipeline-stages/", { method: "POST", body: JSON.stringify({ name: draft.name, kind: draft.kind, position: Number(draft.position || 0) }) }); setDraft({ name: "", kind: "open", position: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="space-y-7">
    {removing && <ConfirmDialog
      title="Excluir etapa"
      message={<>A etapa <strong className="text-ink">{removing.name}</strong> é apagada de vez — aqui não há arquivamento. Etapas com oportunidades vinculadas não podem ser excluídas.</>}
      confirmLabel="Excluir" busy={removeBusy}
      onCancel={() => setRemoving(null)} onConfirm={() => void remove()}
    />}
    <a href="/comercial" className="back-link"><ArrowLeft className="size-4" />Voltar para o Comercial</a>
    <header className="page-head"><p className="eyebrow">Comercial</p><h1>Etapas do pipeline</h1><p>Ordene e nomeie as etapas. Só pode haver uma etapa "Ganho" e uma "Perdido".</p></header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <section className="panel panel--flush">
      <div className="panel-heading"><h2>Etapas atuais</h2></div>
      <div className="panel-rows">{stages.map(stage => <div className="row gap-3 py-3" key={stage.id}>
        <GripVertical className="size-4 shrink-0 text-slate-300" />
        <input className="field max-w-56 flex-1" value={stage.name} onChange={event => updateLocal(stage.id, { name: event.target.value })} aria-label={`Nome da etapa ${stage.id}`} />
        <select className="field w-32" value={stage.kind} onChange={event => updateLocal(stage.id, { kind: event.target.value as PipelineStage["kind"] })} aria-label={`Tipo da etapa ${stage.id}`}>{Object.entries(kindLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <input className="field w-20" type="number" value={stage.position} onChange={event => updateLocal(stage.id, { position: Number(event.target.value) })} aria-label={`Ordem da etapa ${stage.id}`} />
        <button className="btn" onClick={() => void save(stage)}><Save className="size-4" />Salvar</button>
        <button className="btn btn--icon-danger" aria-label={`Excluir etapa ${stage.name}`} onClick={() => setRemoving(stage)}><Trash2 className="size-4" /></button>
      </div>)}</div>
    </section>

    <form className="toolbar" onSubmit={event => void create(event)}>
      <label className="form-label">Nova etapa<input className="field w-56" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} placeholder="Ex.: Proposta enviada" required /></label>
      <label className="form-label">Tipo<select className="field w-32" value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value })}>{Object.entries(kindLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="form-label">Ordem<input className="field w-20" type="number" value={draft.position} onChange={event => setDraft({ ...draft, position: event.target.value })} placeholder="0" /></label>
      <button className="btn" type="submit"><Plus className="size-4" />Adicionar etapa</button>
    </form>
  </section>;
}
