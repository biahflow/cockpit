import { ArrowRight, CalendarDays, CircleDollarSign, Download, FileText, GripVertical, Plus, Save, SlidersHorizontal, Sparkles, UploadCloud, X } from "lucide-react";
import { type DragEvent, type FormEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { api, documentDownloadUrl } from "../api";
import { useAuth } from "../auth";
import { AgentPanel } from "../components/AgentPanel";
import { ArtifactsPanel } from "../components/ArtifactsPanel";
import type { Client, Contact, DocumentEntry, Opportunity, PipelineStage, Service, ServiceTier } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const blankDraft = { title: "", client: "", estimated_value: "", stage: "", expected_close_date: "", service: "" };

export function CommercialPage() {
  const { user, aiEnabled } = useAuth();
  const [aiText, setAiText] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [artifactsToken, setArtifactsToken] = useState(0);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState(blankDraft);
  const [isComposerOpen, setComposerOpen] = useState(false);
  const [converting, setConverting] = useState<Opportunity | null>(null);
  const [dates, setDates] = useState({ start_date: "", due_date: "" });
  const [detail, setDetail] = useState<Opportunity | null>(null);
  const [detailDraft, setDetailDraft] = useState({ title: "", scope: "", estimated_value: "", expected_close_date: "", contact: "", stage: "", service: "" });
  const [detailContacts, setDetailContacts] = useState<Contact[]>([]);
  const [detailDocs, setDetailDocs] = useState<DocumentEntry[]>([]);
  const detailFile = useRef<HTMLInputElement>(null);
  const load = useCallback(() => Promise.all([api<PipelineStage[]>("/pipeline-stages/"), api<Opportunity[]>("/opportunities/"), api<Client[]>("/clients/"), api<Service[]>("/services/")]).then(([loadedStages, loadedOpportunities, loadedClients, loadedServices]) => { setStages(loadedStages); setOpportunities(loadedOpportunities); setClients(loadedClients); setServices(loadedServices); if (loadedStages[0]) setDraft(current => current.stage ? current : { ...current, stage: String(loadedStages[0].id) }); }).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);
  async function move(event: DragEvent<HTMLElement>, stage: PipelineStage) { event.preventDefault(); const id = Number(event.dataTransfer.getData("opportunity")); if (!id) return; try { await api(`/opportunities/${id}/`, { method: "PATCH", body: JSON.stringify({ stage: stage.id }) }); await load(); } catch (cause) { setError((cause as Error).message); } }
  async function createOpportunity(event: FormEvent<HTMLFormElement>) { event.preventDefault(); try { await api("/opportunities/", { method: "POST", body: JSON.stringify({ ...draft, client: Number(draft.client), stage: Number(draft.stage), service: draft.service ? Number(draft.service) : null }) }); setDraft(current => ({ ...blankDraft, stage: current.stage })); setComposerOpen(false); await load(); } catch (cause) { setError((cause as Error).message); } }
  async function convert(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!converting) return; try { await api(`/opportunities/${converting.id}/convert-to-project/`, { method: "POST", body: JSON.stringify({ client: converting.client, name: converting.title, ...dates, status: "planning" }) }); setConverting(null); setDates({ start_date: "", due_date: "" }); await load(); } catch (cause) { setError((cause as Error).message); } }

  async function openDetail(item: Opportunity) {
    setDetail(item);
    setDetailDraft({ title: item.title, scope: item.scope, estimated_value: item.estimated_value, expected_close_date: item.expected_close_date, contact: item.contact ? String(item.contact) : "", stage: String(item.stage), service: item.service ? String(item.service) : "" });
    setDetailContacts([]); setDetailDocs([]); setAiText("");
    try {
      const [contacts, docs] = await Promise.all([api<Contact[]>(`/contacts/?client=${item.client}`), api<DocumentEntry[]>(`/documents/?opportunity=${item.id}`)]);
      setDetailContacts(contacts); setDetailDocs(docs);
    } catch (cause) { setError((cause as Error).message); }
  }
  async function saveDetail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail) return;
    try {
      const updated = await api<Opportunity>(`/opportunities/${detail.id}/`, { method: "PATCH", body: JSON.stringify({ title: detailDraft.title, scope: detailDraft.scope, estimated_value: detailDraft.estimated_value, expected_close_date: detailDraft.expected_close_date, contact: detailDraft.contact ? Number(detailDraft.contact) : null, stage: Number(detailDraft.stage), service: detailDraft.service ? Number(detailDraft.service) : null }) });
      setDetail(updated); await load();
    } catch (cause) { setError((cause as Error).message); }
  }
  async function uploadDetailDoc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const file = detailFile.current?.files?.[0]; if (!file || !detail) return;
    try {
      const body = new FormData(); body.append("opportunity", String(detail.id)); body.append("file", file);
      await api("/documents/", { method: "POST", body });
      if (detailFile.current) detailFile.current.value = "";
      setDetailDocs(await api<DocumentEntry[]>(`/documents/?opportunity=${detail.id}`));
    } catch (cause) { setError((cause as Error).message); }
  }
  function startConversion(item: Opportunity) { setDetail(null); setConverting(item); }
  async function runAi(kind: "summary" | "proposal" | "contract") {
    if (!detail) return; setAiBusy(true); setAiText("");
    try {
      const result = await api<{ text: string; artifact?: unknown }>(`/opportunities/${detail.id}/${kind}/`, { method: "POST" });
      // Proposta e contrato viram artefato registrado (FDD 016); o resumo segue efêmero.
      if (result.artifact) setArtifactsToken(token => token + 1); else setAiText(result.text);
    }
    catch (cause) { setError((cause as Error).message); } finally { setAiBusy(false); }
  }
  async function saveSummaryAsDocument() {
    if (!detail || !aiText.trim()) return;
    try {
      const body = new FormData();
      body.append("opportunity", String(detail.id));
      body.append("file", new File([aiText], `resumo-${detail.title}.txt`, { type: "text/plain" }));
      await api("/documents/", { method: "POST", body });
      setDetailDocs(await api<DocumentEntry[]>(`/documents/?opportunity=${detail.id}`));
      setAiText("");
    } catch (cause) { setError((cause as Error).message); }
  }
  const reloadDetailDocs = useCallback(() => {
    if (!detail) return;
    void api<DocumentEntry[]>(`/documents/?opportunity=${detail.id}`).then(setDetailDocs).catch(() => undefined);
  }, [detail]);

  const sellableServices = services.filter(service => service.active);

  return <section className="space-y-7"><header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Comercial</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Pipeline de oportunidades</h1><p className="mt-2 text-sm text-slate-600">Mova negociações adiante e transforme ganhos em projetos.</p></div><div className="flex flex-wrap items-center gap-3 self-start sm:self-auto">{user?.role === "admin" && <a href="/pipeline" className="inline-flex items-center gap-2 rounded-xl border bg-white px-4 py-2.5 text-sm font-semibold text-ink hover:border-ocean"><SlidersHorizontal className="size-4 text-ocean" />Configurar etapas</a>}<button className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-2.5 text-sm font-semibold text-white hover:bg-ink" onClick={() => setComposerOpen(true)}><Plus className="size-4" />Nova oportunidade</button></div></header>{error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    <AgentPanel agentKey="comercial" title="Agente Comercial" roles={["sales"]} placeholder="Ex.: quais oportunidades estão paradas?" />
    {/* `tabIndex`/`role`/`aria-label`: uma faixa que rola na horizontal precisa receber foco,
        senão quem navega por teclado não alcança as etapas fora da tela (WCAG 2.1.1). */}
    <div className="flex gap-4 overflow-x-auto pb-3" tabIndex={0} role="region" aria-label="Etapas do pipeline">{stages.map(stage => { const items = opportunities.filter(item => item.stage === stage.id); return <section className="w-72 shrink-0 rounded-2xl border bg-slate-100/70 p-3" key={stage.id} onDragOver={event => event.preventDefault()} onDrop={event => void move(event, stage)}><header className="mb-3 flex items-center justify-between px-1"><div><h2 className="text-sm font-semibold text-ink">{stage.name}</h2><p className="mt-0.5 text-xs text-slate-600">{items.length} oportunidades</p></div><span className="rounded-lg bg-white px-2 py-1 text-xs font-semibold text-ocean">{money.format(items.reduce((sum, item) => sum + Number(item.estimated_value), 0))}</span></header><div className="grid min-h-44 gap-3">{items.map(item => <article className="cursor-pointer rounded-xl border bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md active:cursor-grabbing" draggable key={item.id} onDragStart={event => event.dataTransfer.setData("opportunity", String(item.id))} onClick={() => void openDetail(item)}><div className="flex justify-between gap-2"><p className="text-sm font-semibold leading-5 text-ink">{item.title}</p><GripVertical className="size-4 shrink-0 cursor-grab text-slate-300" /></div>{item.service_name && <p className="mt-2"><span className={`inline-block rounded-lg px-2 py-0.5 text-[11px] font-semibold ${tierBadgeClass(item.service_tier)}`}>{item.service_name}</span></p>}<p className="mt-4 flex items-center gap-1.5 text-xs text-slate-600"><CalendarDays className="size-3.5" />{new Date(`${item.expected_close_date}T12:00:00`).toLocaleDateString("pt-BR")}</p><p className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-ocean"><CircleDollarSign className="size-3.5" />{money.format(Number(item.estimated_value))}</p>{stage.kind === "won" && <button className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-ocean hover:text-ink" onClick={event => { event.stopPropagation(); setConverting(item); }}>Criar projeto <ArrowRight className="size-3.5" /></button>}</article>)}{!items.length && <div className="grid min-h-24 place-items-center rounded-xl border border-dashed border-slate-200 bg-white/40 px-3 text-center text-xs text-slate-600">Arraste uma oportunidade para esta etapa</div>}</div></section>; })}</div>
    {isComposerOpen && <Modal title="Nova oportunidade" onClose={() => setComposerOpen(false)}><form className="grid gap-4" onSubmit={event => void createOpportunity(event)}><Field label="Título"><input className="field" value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} required /></Field><Field label="Cliente"><select className="field" value={draft.client} onChange={event => setDraft({ ...draft, client: event.target.value })} required><option value="">Selecione</option>{clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}</select></Field><Field label="Nível de produto"><select className="field" value={draft.service} onChange={event => setDraft({ ...draft, service: event.target.value })}><option value="">Sem nível definido</option>{sellableServices.map(service => <option key={service.id} value={service.id}>{serviceLabel(service)}</option>)}</select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Valor estimado"><input className="field" type="number" min="0" step="0.01" value={draft.estimated_value} onChange={event => setDraft({ ...draft, estimated_value: event.target.value })} required /></Field><Field label="Previsão de fechamento"><input className="field" type="date" value={draft.expected_close_date} onChange={event => setDraft({ ...draft, expected_close_date: event.target.value })} required /></Field></div><button className="rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit">Adicionar ao pipeline</button></form></Modal>}
    {converting && <Modal title="Criar projeto" onClose={() => setConverting(null)}><p className="mb-5 text-sm text-slate-600">Você está convertendo <strong className="text-ink">{converting.title}</strong>. Defina a janela inicial de entrega.</p><form className="grid gap-4" onSubmit={event => void convert(event)}><div className="grid gap-4 sm:grid-cols-2"><Field label="Início"><input className="field" type="date" value={dates.start_date} onChange={event => setDates({ ...dates, start_date: event.target.value })} required /></Field><Field label="Prazo final"><input className="field" type="date" value={dates.due_date} onChange={event => setDates({ ...dates, due_date: event.target.value })} required /></Field></div><button className="rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit">Criar projeto</button></form></Modal>}
    {detail && <Modal title="Detalhe da oportunidade" onClose={() => setDetail(null)}>
      <form className="grid gap-4" onSubmit={event => void saveDetail(event)}>
        <Field label="Título"><input className="field" value={detailDraft.title} onChange={event => setDetailDraft({ ...detailDraft, title: event.target.value })} required /></Field>
        <Field label="Escopo"><textarea className="field min-h-20" value={detailDraft.scope} onChange={event => setDetailDraft({ ...detailDraft, scope: event.target.value })} placeholder="Descreva o escopo da negociação" /></Field>
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Valor estimado"><input className="field" type="number" min="0" step="0.01" value={detailDraft.estimated_value} onChange={event => setDetailDraft({ ...detailDraft, estimated_value: event.target.value })} required /></Field><Field label="Previsão de fechamento"><input className="field" type="date" value={detailDraft.expected_close_date} onChange={event => setDetailDraft({ ...detailDraft, expected_close_date: event.target.value })} required /></Field></div>
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Contato"><select className="field" value={detailDraft.contact} onChange={event => setDetailDraft({ ...detailDraft, contact: event.target.value })}><option value="">Sem contato</option>{detailContacts.map(contact => <option key={contact.id} value={contact.id}>{contact.name}</option>)}</select></Field><Field label="Etapa"><select className="field" value={detailDraft.stage} onChange={event => setDetailDraft({ ...detailDraft, stage: event.target.value })}>{stages.map(stage => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></Field></div>
        <Field label="Nível de produto"><select className="field" value={detailDraft.service} onChange={event => setDetailDraft({ ...detailDraft, service: event.target.value })}><option value="">Sem nível definido</option>{sellableServices.map(service => <option key={service.id} value={service.id}>{serviceLabel(service)}</option>)}</select></Field>
        <div className="flex flex-wrap gap-3"><button className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><Save className="size-4" />Salvar</button>{stages.find(stage => stage.id === detail.stage)?.kind === "won" && <button type="button" className="inline-flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold text-ink hover:border-ocean" onClick={() => startConversion(detail)}>Converter em projeto <ArrowRight className="size-4 text-ocean" /></button>}</div>
      </form>
      <div className="mt-6 border-t pt-5">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink"><FileText className="size-4 text-ocean" />Documentos</h3>
        {detailDocs.length ? <div className="mt-3 divide-y">{detailDocs.map(doc => <div className="flex items-center gap-3 py-2" key={doc.id}><FileText className="size-4 shrink-0 text-slate-600" /><span className="min-w-0 flex-1 truncate text-sm text-ink">{doc.original_name}</span>{doc.drive_link && <a className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 hover:text-ocean" href={doc.drive_link} target="_blank" rel="noreferrer" aria-label={`Abrir ${doc.original_name} no Drive`}>Drive</a>}<a className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-ocean" href={documentDownloadUrl(doc.id)} aria-label={`Baixar ${doc.original_name}`}><Download className="size-4" /></a></div>)}</div> : <p className="mt-3 text-sm text-slate-600">Nenhum documento vinculado.</p>}
        <form className="mt-3 flex gap-2" onSubmit={event => void uploadDetailDoc(event)}><input className="field" type="file" ref={detailFile} aria-label="Arquivo da oportunidade" /><button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Enviar documento" type="submit"><UploadCloud className="size-4" /></button></form>
      </div>
      {aiEnabled && <div className="mt-6 border-t pt-5">
        <div className="flex flex-wrap items-center gap-2"><Sparkles className="size-4 text-ocean" /><h3 className="text-sm font-semibold text-ink">IA</h3><button type="button" className="ml-auto rounded-xl border px-3 py-1.5 text-sm font-semibold text-ink hover:border-ocean disabled:opacity-60" onClick={() => void runAi("summary")} disabled={aiBusy}>Resumir</button><button type="button" className="rounded-xl border px-3 py-1.5 text-sm font-semibold text-ink hover:border-ocean disabled:opacity-60" onClick={() => void runAi("proposal")} disabled={aiBusy}>Gerar proposta</button><button type="button" className="rounded-xl border px-3 py-1.5 text-sm font-semibold text-ink hover:border-ocean disabled:opacity-60" onClick={() => void runAi("contract")} disabled={aiBusy}>Gerar contrato</button></div>
        {aiBusy && <p className="mt-3 text-sm text-slate-600">Gerando…</p>}
        {aiText && <div className="mt-3"><textarea className="field min-h-40" value={aiText} onChange={event => setAiText(event.target.value)} aria-label="Rascunho gerado pela IA" /><div className="mt-2 flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-slate-600">Revise antes de salvar — a IA gera um rascunho.</p><button type="button" className="rounded-xl bg-ocean px-4 py-2 text-sm font-semibold text-white hover:bg-ink" onClick={() => void saveSummaryAsDocument()}>Salvar como documento</button></div></div>}
      </div>}
      <ArtifactsPanel opportunity={detail.id} reloadToken={artifactsToken} onChange={reloadDetailDocs} />
    </Modal>}
  </section>;
}

// Os três níveis avançam do diagnóstico gratuito à implantação; a cor acompanha essa escada.
const tierBadges: Record<ServiceTier, string> = {
  discovery_express: "bg-mint text-ocean",
  discovery_assessment: "bg-ocean/10 text-ocean",
  implantacao: "bg-ocean text-white",
  "": "bg-slate-100 text-slate-600",
};
function tierBadgeClass(tier: ServiceTier) { return tierBadges[tier] ?? tierBadges[""]; }
function serviceLabel(service: Service) { return service.tier ? `${service.name} — ${Number(service.list_price) === 0 ? "gratuito" : money.format(Number(service.list_price))}` : service.name; }

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="grid gap-2 text-sm font-medium text-slate-700">{label}{children}</label>; }
function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) { return <div className="fixed inset-0 z-40 grid place-items-center bg-ink/45 p-4" role="dialog" aria-modal="true" aria-label={title}><div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl sm:p-6"><div className="mb-5 flex items-center justify-between"><h2 className="text-lg font-semibold text-ink">{title}</h2><button className="grid size-8 place-items-center rounded-lg text-slate-600 hover:bg-slate-100" aria-label="Fechar" onClick={onClose}><X className="size-4" /></button></div>{children}</div></div>; }
