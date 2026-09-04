import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import type { BlueprintArea, DigitalEmployeeBlueprint, KpiDirection, KpiUnit, Service, Vertical } from "../types";

const areas: { value: BlueprintArea; label: string }[] = [
  { value: "commercial", label: "Comercial" },
  { value: "finance", label: "Financeiro" },
  { value: "hr", label: "RH" },
  { value: "legal", label: "Jurídico" },
  { value: "support", label: "Atendimento" },
];
// Unidade e direção não têm coluna na variante de propósito: a variante muda o **texto** do KPI
// para o setor, e trocar a unidade faria dois blocos iguais deixarem de se comparar (FDD 027).
const kpiUnits: { value: KpiUnit; label: string }[] = [
  { value: "", label: "Sem unidade" }, { value: "percent", label: "Percentual (%)" },
  { value: "hours", label: "Horas" }, { value: "minutes", label: "Minutos" },
  { value: "currency", label: "Moeda (R$)" }, { value: "count", label: "Contagem" },
];
const blankVariant = { vertical: "", description: "", kpi_label: "", default_hours_saved_month: "", default_roi_month: "" };
type VariantDraft = typeof blankVariant;
type Removing = { kind: "vertical" | "blueprint"; id: number; name: string };

export function BibliotecaPage() {
  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [blueprints, setBlueprints] = useState<DigitalEmployeeBlueprint[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [verticalDraft, setVerticalDraft] = useState({ name: "", slug: "", position: "" });
  const [blueprintDraft, setBlueprintDraft] = useState({ name: "", area: "commercial" as BlueprintArea });
  const [variantDraft, setVariantDraft] = useState<Record<number, VariantDraft>>({});
  const [error, setError] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [removing, setRemoving] = useState<Removing | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  const load = useCallback(
    () => Promise.all([
      api<Vertical[]>("/verticals/"),
      api<DigitalEmployeeBlueprint[]>("/digital-employee-blueprints/"),
      api<Service[]>("/services/"),
    ]).then(([loadedVerticals, loadedBlueprints, loadedServices]) => {
      setVerticals(loadedVerticals); setBlueprints(loadedBlueprints); setServices(loadedServices);
    }).catch((cause: Error) => setError(cause.message)).finally(() => setLoading(false)),
    [],
  );
  useEffect(() => { void load(); }, [load]);

  function updateVertical(id: number, patch: Partial<Vertical>) {
    setVerticals(prev => prev.map(item => item.id === id ? { ...item, ...patch } : item));
  }
  function updateBlueprint(id: number, patch: Partial<DigitalEmployeeBlueprint>) {
    setBlueprints(prev => prev.map(item => item.id === id ? { ...item, ...patch } : item));
  }
  function draftFor(blueprintId: number): VariantDraft {
    return variantDraft[blueprintId] ?? blankVariant;
  }
  function setDraft(blueprintId: number, patch: Partial<VariantDraft>) {
    setVariantDraft(prev => ({ ...prev, [blueprintId]: { ...draftFor(blueprintId), ...patch } }));
  }

  async function saveVertical(vertical: Vertical) {
    setError("");
    try { await api(`/verticals/${vertical.id}/`, { method: "PATCH", body: JSON.stringify({ name: vertical.name, slug: vertical.slug, position: Number(vertical.position), active: vertical.active }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function saveBlueprint(blueprint: DigitalEmployeeBlueprint) {
    setError("");
    try {
      await api(`/digital-employee-blueprints/${blueprint.id}/`, { method: "PATCH", body: JSON.stringify({
        name: blueprint.name, area: blueprint.area, description: blueprint.description,
        kpi_label: blueprint.kpi_label, kpi_unit: blueprint.kpi_unit, kpi_direction: blueprint.kpi_direction,
        default_hours_saved_month: blueprint.default_hours_saved_month || "0",
        default_roi_month: blueprint.default_roi_month || "0", service: blueprint.service, active: blueprint.active,
      }) });
      await load();
    } catch (cause) { setError((cause as Error).message); }
  }
  async function createVertical(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/verticals/", { method: "POST", body: JSON.stringify({ name: verticalDraft.name, slug: verticalDraft.slug, position: Number(verticalDraft.position || 0) }) }); setVerticalDraft({ name: "", slug: "", position: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createBlueprint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/digital-employee-blueprints/", { method: "POST", body: JSON.stringify(blueprintDraft) }); setBlueprintDraft({ name: "", area: "commercial" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function addVariant(blueprintId: number) {
    const draft = draftFor(blueprintId);
    if (!draft.vertical) return;
    setError("");
    try {
      await api("/blueprint-variants/", { method: "POST", body: JSON.stringify({
        blueprint: blueprintId, vertical: Number(draft.vertical), description: draft.description,
        kpi_label: draft.kpi_label,
        // Vazio é `null`, não zero: na variante, em branco **herda** o valor do blueprint.
        default_hours_saved_month: draft.default_hours_saved_month || null,
        default_roi_month: draft.default_roi_month || null,
      }) });
      setVariantDraft(prev => ({ ...prev, [blueprintId]: blankVariant }));
      await load();
    } catch (cause) { setError((cause as Error).message); }
  }
  async function removeVariant(id: number) {
    setError("");
    try { await api(`/blueprint-variants/${id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function remove() {
    if (!removing) return;
    setError(""); setRemoveBusy(true);
    const path = removing.kind === "vertical" ? "verticals" : "digital-employee-blueprints";
    try { await api(`/${path}/${removing.id}/`, { method: "DELETE" }); setRemoving(null); await load(); }
    catch (cause) { setRemoving(null); setError((cause as Error).message); }
    finally { setRemoveBusy(false); }
  }

  if (isLoading) return <p className="text-sm text-slate-600">Carregando biblioteca…</p>;

  return <section className="space-y-7">
    {removing && <ConfirmDialog
      title={removing.kind === "vertical" ? "Excluir vertical" : "Excluir blueprint"}
      message={removing.kind === "vertical"
        ? <>A vertical <strong className="text-ink">{removing.name}</strong> é apagada de vez — aqui não há arquivamento. Só é possível excluir vertical que nenhum cliente e nenhuma variante usam; para aposentar uma em uso, desmarque <strong className="text-ink">Disponível</strong> e salve.</>
        : <>O blueprint <strong className="text-ink">{removing.name}</strong> e as variantes dele são apagados de vez. Só é possível excluir blueprint que ninguém instanciou; para aposentar um em uso, desmarque <strong className="text-ink">Disponível</strong> e salve. Os Funcionários Digitais já entregues não mudam — eles são cópias.</>}
      confirmLabel="Excluir" busy={removeBusy}
      onCancel={() => setRemoving(null)} onConfirm={() => void remove()}
    />}
    <a href="/configuracoes" className="back-link"><ArrowLeft className="size-4" />Voltar para configurações</a>
    <header className="page-head"><p className="eyebrow">Metodologia</p><h1>Biblioteca de Funcionários Digitais</h1><p>O catálogo que a entrega instancia em vez de recriar. Cada bloco pode ser parametrizado por vertical — o mesmo SDR servindo setores diferentes.</p></header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <section className="panel panel--flush">
      <div className="border-b px-5 py-4 sm:px-6"><h2 className="font-semibold text-ink">Verticais</h2><p className="mt-0.5 text-sm text-slate-600">Os setores dos clientes. É por eles que um blueprint se parametriza.</p></div>
      {verticals.length ? <div className="divide-y">{verticals.map(vertical => <div className="flex flex-wrap items-center gap-3 px-5 py-3 sm:px-6" key={vertical.id}>
        <input className="field max-w-56 flex-1" value={vertical.name} onChange={event => updateVertical(vertical.id, { name: event.target.value })} aria-label={`Nome da vertical ${vertical.id}`} />
        <input className="field w-40" value={vertical.slug} onChange={event => updateVertical(vertical.id, { slug: event.target.value })} aria-label={`Identificador da vertical ${vertical.name}`} />
        <input className="field w-20" type="number" value={vertical.position} onChange={event => updateVertical(vertical.id, { position: Number(event.target.value) })} aria-label={`Ordem da vertical ${vertical.name}`} />
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="size-4 rounded border-slate-300 text-accent" checked={vertical.active} onChange={event => updateVertical(vertical.id, { active: event.target.checked })} />Disponível</label>
        <button className="btn" onClick={() => void saveVertical(vertical)}><Save className="size-4" />Salvar</button>
        <button className="btn btn--icon-danger" aria-label={`Excluir vertical ${vertical.name}`} onClick={() => setRemoving({ kind: "vertical", id: vertical.id, name: vertical.name })}><Trash2 className="size-4" /></button>
      </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Nenhuma vertical ainda. Sem elas, os blocos valem para qualquer setor.</p>}
      <form className="flex flex-wrap items-end gap-3 border-t bg-slate-50/60 px-5 py-4 sm:px-6" onSubmit={event => void createVertical(event)}>
        <label className="form-label">Nova vertical<input className="field w-56" value={verticalDraft.name} onChange={event => setVerticalDraft({ ...verticalDraft, name: event.target.value })} placeholder="Ex.: Igrejas" required /></label>
        <label className="form-label">Identificador<input className="field w-40" value={verticalDraft.slug} onChange={event => setVerticalDraft({ ...verticalDraft, slug: event.target.value })} placeholder="igrejas" required /></label>
        <label className="form-label">Ordem<input className="field w-20" type="number" value={verticalDraft.position} onChange={event => setVerticalDraft({ ...verticalDraft, position: event.target.value })} placeholder="0" /></label>
        <button className="btn" type="submit"><Plus className="size-4" />Adicionar vertical</button>
      </form>
    </section>

    <section className="space-y-4">
      <h2 className="font-semibold text-ink">Blocos do catálogo</h2>
      {blueprints.map(blueprint => <section className="panel panel--flush" key={blueprint.id}>
        <div className="flex flex-wrap items-center gap-3 border-b bg-slate-50/60 px-5 py-4 sm:px-6">
          <input className="field max-w-56 flex-1" value={blueprint.name} onChange={event => updateBlueprint(blueprint.id, { name: event.target.value })} aria-label={`Nome do blueprint ${blueprint.id}`} />
          <select className="field w-40" value={blueprint.area} onChange={event => updateBlueprint(blueprint.id, { area: event.target.value as BlueprintArea })} aria-label={`Área de ${blueprint.name}`}>{areas.map(area => <option key={area.value} value={area.value}>{area.label}</option>)}</select>
          <button className="btn" onClick={() => void saveBlueprint(blueprint)}><Save className="size-4" />Salvar</button>
          <button className="btn btn--icon-danger" aria-label={`Excluir blueprint ${blueprint.name}`} onClick={() => setRemoving({ kind: "blueprint", id: blueprint.id, name: blueprint.name })}><Trash2 className="size-4" /></button>
        </div>
        <div className="px-5 py-4 sm:px-6">
          <label className="mb-4 flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="size-4 rounded border-slate-300 text-accent" checked={blueprint.active} onChange={event => updateBlueprint(blueprint.id, { active: event.target.checked })} />Disponível para instanciar</label>
          {!blueprint.active && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm text-slate-700">Bloco aposentado: não é oferecido em entrega nova. Os Funcionários Digitais já instanciados continuam iguais — eles são cópias.</p>}
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="form-label sm:col-span-2">O que este bloco faz<textarea className="field min-h-20" value={blueprint.description} onChange={event => updateBlueprint(blueprint.id, { description: event.target.value })} aria-label={`Descrição de ${blueprint.name}`} placeholder="Vai para a descrição do Funcionário Digital e para a proposta gerada pela IA" /></label>
            <label className="form-label">KPI canônico<input className="field" value={blueprint.kpi_label} onChange={event => updateBlueprint(blueprint.id, { kpi_label: event.target.value })} aria-label={`KPI de ${blueprint.name}`} placeholder="Ex.: Leads qualificados/mês" /></label>
            <label className="form-label">Unidade do KPI<select className="field" value={blueprint.kpi_unit} onChange={event => updateBlueprint(blueprint.id, { kpi_unit: event.target.value as KpiUnit })} aria-label={`Unidade do KPI de ${blueprint.name}`}>{kpiUnits.map(unit => <option key={unit.value} value={unit.value}>{unit.label}</option>)}</select></label>
            <label className="form-label">Direção do KPI<select className="field" value={blueprint.kpi_direction} onChange={event => updateBlueprint(blueprint.id, { kpi_direction: event.target.value as KpiDirection })} aria-label={`Direção do KPI de ${blueprint.name}`}><option value="up">Maior é melhor</option><option value="down">Menor é melhor</option></select></label>
            <label className="form-label">Nível de produto<select className="field" value={blueprint.service ?? ""} onChange={event => updateBlueprint(blueprint.id, { service: event.target.value ? Number(event.target.value) : null })} aria-label={`Nível de produto de ${blueprint.name}`}><option value="">Qualquer nível</option>{services.map(service => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>
            <label className="form-label">Horas poupadas/mês (padrão)<input className="field" type="number" min="0" step="0.1" value={blueprint.default_hours_saved_month} onChange={event => updateBlueprint(blueprint.id, { default_hours_saved_month: event.target.value })} aria-label={`Horas padrão de ${blueprint.name}`} /></label>
            <label className="form-label">ROI/mês (padrão)<input className="field" type="number" min="0" step="0.01" value={blueprint.default_roi_month} onChange={event => updateBlueprint(blueprint.id, { default_roi_month: event.target.value })} aria-label={`ROI padrão de ${blueprint.name}`} /></label>
          </div>

          <p className="section-label mb-2 mt-5">Variantes por vertical</p>
          <p className="mb-2 text-xs text-slate-600">Campo em branco na variante herda o valor do bloco acima.</p>
          <div className="divide-y">{blueprint.variants.map(variant => <div className="flex flex-wrap items-center gap-3 py-2" key={variant.id}>
            <span className="state state--0">{variant.vertical_name}</span>
            <span className="flex-1 text-sm text-slate-600">{variant.description || <em className="text-slate-500">herda a descrição do bloco</em>}</span>
            {variant.kpi_label && <span className="text-xs text-slate-600">KPI: {variant.kpi_label}</span>}
            <button className="btn btn--icon-danger size-8 rounded-lg" aria-label={`Excluir variante ${variant.vertical_name} de ${blueprint.name}`} onClick={() => void removeVariant(variant.id)}><Trash2 className="size-3.5" /></button>
          </div>)}</div>
          <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={event => { event.preventDefault(); void addVariant(blueprint.id); }}>
            <label className="form-label">Vertical<select className="field w-44" value={draftFor(blueprint.id).vertical} onChange={event => setDraft(blueprint.id, { vertical: event.target.value })} aria-label={`Vertical da nova variante de ${blueprint.name}`} required><option value="">Escolha…</option>{verticals.map(vertical => <option key={vertical.id} value={vertical.id}>{vertical.name}</option>)}</select></label>
            <label className="form-label flex-1">Descrição para o setor<input className="field" value={draftFor(blueprint.id).description} onChange={event => setDraft(blueprint.id, { description: event.target.value })} aria-label={`Descrição da nova variante de ${blueprint.name}`} placeholder="Em branco, herda a do bloco" /></label>
            <label className="form-label">KPI<input className="field w-40" value={draftFor(blueprint.id).kpi_label} onChange={event => setDraft(blueprint.id, { kpi_label: event.target.value })} aria-label={`KPI da nova variante de ${blueprint.name}`} /></label>
            <button className="btn btn--icon" aria-label={`Adicionar variante a ${blueprint.name}`} type="submit"><Plus className="size-4" /></button>
          </form>
        </div>
      </section>)}
      {!blueprints.length && <p className="empty-state">Nenhum bloco no catálogo. Cadastre o primeiro abaixo — é ele que a entrega vai instanciar em vez de recriar.</p>}
    </section>

    <form className="toolbar" onSubmit={event => void createBlueprint(event)}>
      <label className="form-label">Novo bloco<input className="field w-56" value={blueprintDraft.name} onChange={event => setBlueprintDraft({ ...blueprintDraft, name: event.target.value })} placeholder="Ex.: SDR" required /></label>
      <label className="form-label">Área<select className="field w-44" value={blueprintDraft.area} onChange={event => setBlueprintDraft({ ...blueprintDraft, area: event.target.value as BlueprintArea })}>{areas.map(area => <option key={area.value} value={area.value}>{area.label}</option>)}</select></label>
      <button className="btn" type="submit"><Plus className="size-4" />Adicionar bloco</button>
    </form>
  </section>;
}
