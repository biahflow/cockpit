import { ArrowRight, CalendarDays, CircleDollarSign, Download, FileText, GripVertical, MessageSquareText, Plus, RotateCcw, Save, SlidersHorizontal, Sparkles, Trash2, UploadCloud, X } from "lucide-react";
import { type DragEvent, type FormEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { api, documentDownloadUrl } from "../api";
import { useAuth } from "../auth";
import { AgentPanel } from "../components/AgentPanel";
import { ArtifactsPanel } from "../components/ArtifactsPanel";
import { ConfirmDialog, Modal } from "../components/Modal";
import { canWriteBeyondDelivery } from "../roles";
import { rotuloDoDegrau } from "../tiers";
import type { Account, Activity, ActivityKind, Contact, DocumentEntry, CommercialOpportunity, PipelineStage, Project, Service, ServiceTier } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const blankDraft = { title: "", account: "", estimated_value: "", stage: "", expected_close_date: "", service: "" };
const blankActivity = { kind: "call" as ActivityKind, happened_on: new Date().toISOString().slice(0, 10), summary: "", notes: "" };
const activityKindLabels: Record<ActivityKind, string> = { call: "Ligação", meeting: "Reunião", email: "E-mail", note: "Nota" };

export function CommercialPage() {
  const { user, aiEnabled } = useAuth();
  const [aiText, setAiText] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [artifactsToken, setArtifactsToken] = useState(0);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [opportunities, setOpportunities] = useState<CommercialOpportunity[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState(blankDraft);
  const [isComposerOpen, setComposerOpen] = useState(false);
  const [converting, setConverting] = useState<CommercialOpportunity | null>(null);
  const [created, setCreated] = useState<Project | null>(null);
  const [dates, setDates] = useState({ start_date: "", due_date: "" });
  const [detail, setDetail] = useState<CommercialOpportunity | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailNotice, setDetailNotice] = useState("");
  const [detailDraft, setDetailDraft] = useState({ title: "", scope: "", estimated_value: "", expected_close_date: "", contact: "", stage: "", service: "" });
  const [detailContacts, setDetailContacts] = useState<Contact[]>([]);
  const [detailDocs, setDetailDocs] = useState<DocumentEntry[]>([]);
  const [detailActivities, setDetailActivities] = useState<Activity[]>([]);
  const [activityDraft, setActivityDraft] = useState(blankActivity);
  const [archiving, setArchiving] = useState<CommercialOpportunity | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [archived, setArchived] = useState<CommercialOpportunity[]>([]);
  const [restoring, setRestoring] = useState<number | null>(null);
  const detailFile = useRef<HTMLInputElement>(null);
  const load = useCallback(() => Promise.all([api<PipelineStage[]>("/pipeline-stages/"), api<CommercialOpportunity[]>("/opportunities/"), api<Account[]>("/clients/"), api<Service[]>("/services/")]).then(([loadedStages, loadedOpportunities, loadedAccounts, loadedServices]) => { setStages(loadedStages); setOpportunities(loadedOpportunities); setAccounts(loadedAccounts); setServices(loadedServices); if (loadedStages[0]) setDraft(current => current.stage ? current : { ...current, stage: String(loadedStages[0].id) }); }).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);
  async function move(event: DragEvent<HTMLElement>, stage: PipelineStage) { event.preventDefault(); const id = Number(event.dataTransfer.getData("opportunity")); if (!id) return; try { await api(`/opportunities/${id}/`, { method: "PATCH", body: JSON.stringify({ stage: stage.id }) }); await load(); } catch (cause) { setError((cause as Error).message); } }
  async function createOpportunity(event: FormEvent<HTMLFormElement>) { event.preventDefault(); try { await api("/opportunities/", { method: "POST", body: JSON.stringify({ ...draft, account: Number(draft.account), stage: Number(draft.stage), service: draft.service ? Number(draft.service) : null }) }); setDraft(current => ({ ...blankDraft, stage: current.stage })); setComposerOpen(false); await load(); } catch (cause) { setError((cause as Error).message); } }
  async function convert(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!converting) return; try { const created = await api<Project>(`/opportunities/${converting.id}/convert-to-project/`, { method: "POST", body: JSON.stringify({ name: converting.title, ...dates, status: "planning" }) }); setConverting(null); setDates({ start_date: "", due_date: "" }); setCreated(created); await load(); } catch (cause) { setError((cause as Error).message); } }

  async function openDetail(item: CommercialOpportunity) {
    setDetail(item);
    setDetailError(""); setDetailNotice(""); setNotice("");
    setDetailDraft({ title: item.title, scope: item.scope, estimated_value: item.estimated_value, expected_close_date: item.expected_close_date, contact: item.contact ? String(item.contact) : "", stage: String(item.stage), service: item.service ? String(item.service) : "" });
    setDetailContacts([]); setDetailDocs([]); setDetailActivities([]); setActivityDraft(blankActivity); setAiText("");
    try {
      const [contacts, docs, activities] = await Promise.all([api<Contact[]>(`/contacts/?account=${item.account}`), api<DocumentEntry[]>(`/documents/?commercial_opportunity=${item.id}`), api<Activity[]>(`/activities/?commercial_opportunity=${item.id}`)]);
      setDetailContacts(contacts); setDetailDocs(docs); setDetailActivities(activities);
    } catch (cause) { setDetailError((cause as Error).message); }
  }
  async function createDetailActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail) return;
    setDetailError(""); setDetailNotice("");
    try {
      await api("/activities/", { method: "POST", body: JSON.stringify({ account: detail.account, commercial_opportunity: detail.id, ...activityDraft }) });
      setActivityDraft(blankActivity);
      setDetailActivities(await api<Activity[]>(`/activities/?commercial_opportunity=${detail.id}`));
    } catch (cause) { setDetailError((cause as Error).message); }
  }
  async function archiveDetailActivity(activity: Activity) {
    if (!detail) return;
    setDetailError(""); setDetailNotice("");
    try { await api(`/activities/${activity.id}/`, { method: "DELETE" }); setDetailActivities(await api<Activity[]>(`/activities/?commercial_opportunity=${detail.id}`)); }
    catch (cause) { setDetailError((cause as Error).message); }
  }
  async function saveDetail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail) return;
    setDetailError(""); setDetailNotice(""); setNotice("");
    try {
      await api<CommercialOpportunity>(`/opportunities/${detail.id}/`, { method: "PATCH", body: JSON.stringify({ title: detailDraft.title, scope: detailDraft.scope, estimated_value: detailDraft.estimated_value, expected_close_date: detailDraft.expected_close_date, contact: detailDraft.contact ? Number(detailDraft.contact) : null, stage: Number(detailDraft.stage), service: detailDraft.service ? Number(detailDraft.service) : null }) });
      await load();
      setDetail(null);
      setNotice("Oportunidade salva.");
    } catch (cause) { setDetailError((cause as Error).message); }
  }
  async function uploadDetailDoc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail) return;
    setDetailError(""); setDetailNotice("");
    const file = detailFile.current?.files?.[0];
    if (!file) { setDetailError("Escolha um arquivo para enviar."); return; }
    try {
      const body = new FormData(); body.append("commercial_opportunity", String(detail.id)); body.append("file", file);
      await api("/documents/", { method: "POST", body });
      if (detailFile.current) detailFile.current.value = "";
      setDetailDocs(await api<DocumentEntry[]>(`/documents/?commercial_opportunity=${detail.id}`));
      setDetailNotice("Documento enviado.");
    } catch (cause) { setDetailError((cause as Error).message); }
  }
  function startConversion(item: CommercialOpportunity) { setDetail(null); setConverting(item); }
  async function runAi(kind: "summary" | "proposal" | "contract") {
    if (!detail) return; setDetailError(""); setDetailNotice(""); setAiBusy(true); setAiText("");
    try {
      const result = await api<{ text: string; artifact?: unknown }>(`/opportunities/${detail.id}/${kind}/`, { method: "POST" });
      // Proposta e contrato viram artefato registrado (FDD 016); o resumo segue efêmero.
      if (result.artifact) setArtifactsToken(token => token + 1); else setAiText(result.text);
    }
    catch (cause) { setDetailError((cause as Error).message); } finally { setAiBusy(false); }
  }
  async function saveSummaryAsDocument() {
    if (!detail || !aiText.trim()) return;
    setDetailError(""); setDetailNotice("");
    try {
      const body = new FormData();
      body.append("commercial_opportunity", String(detail.id));
      body.append("file", new File([aiText], `resumo-${detail.title}.txt`, { type: "text/plain" }));
      await api("/documents/", { method: "POST", body });
      setDetailDocs(await api<DocumentEntry[]>(`/documents/?commercial_opportunity=${detail.id}`));
      setAiText("");
      setDetailNotice("Resumo salvo como documento.");
    } catch (cause) { setDetailError((cause as Error).message); }
  }
  // O kanban não comporta uma coluna de arquivados — o quadro dá lugar a uma lista simples.
  const loadArchived = useCallback(
    () => api<CommercialOpportunity[]>("/opportunities/?archived=1").then(setArchived).catch((cause: Error) => setError(cause.message)),
    [],
  );
  useEffect(() => { if (showArchived) void loadArchived(); }, [showArchived, loadArchived]);
  async function restore(id: number) {
    setError(""); setRestoring(id);
    try { await api(`/opportunities/${id}/unarchive/`, { method: "POST" }); await loadArchived(); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setRestoring(null); }
  }
  async function archiveOpportunity() {
    if (!archiving) return;
    setArchiveBusy(true);
    try {
      await api(`/opportunities/${archiving.id}/`, { method: "DELETE" });
      setArchiving(null); setDetail(null); await load();
      if (showArchived) await loadArchived();
    } catch (cause) { setArchiving(null); setError((cause as Error).message); }
    finally { setArchiveBusy(false); }
  }
  const reloadDetailDocs = useCallback(() => {
    if (!detail) return;
    void api<DocumentEntry[]>(`/documents/?commercial_opportunity=${detail.id}`).then(setDetailDocs).catch(() => undefined);
  }, [detail]);

  const sellableServices = services.filter(service => service.active);

  return <section className="space-y-7"><header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Comercial</p><h1>Pipeline de oportunidades</h1><p>Mova negociações adiante e transforme ganhos em projetos.</p></div><div className="flex flex-wrap items-center gap-3 self-start sm:self-auto">{user?.is_admin && <a href="/pipeline" className="btn btn--secondary"><SlidersHorizontal className="size-4 text-brand-500" />Configurar etapas</a>}<div className="filter-bar"><button className={`filter-chip ${showArchived ? "" : "filter-chip--on"}`} onClick={() => setShowArchived(false)}>Pipeline</button><button className={`filter-chip ${showArchived ? "filter-chip--on" : ""}`} onClick={() => setShowArchived(true)}>Arquivadas</button></div><button className="btn" onClick={() => setComposerOpen(true)}><Plus className="size-4" />Nova oportunidade</button></div></header>{error && <p role="alert" className="alert--error">{error}</p>}{notice && <p role="status" className="alert--ok">{notice}</p>}
    {created && <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"><span>Projeto <strong>{created.name}</strong> criado, com marcos e tarefas do nível de produto.</span><span className="flex items-center gap-3"><a className="inline-flex items-center gap-1.5 font-semibold text-emerald-900 underline underline-offset-2" href={`/projetos/${created.id}`}>Abrir projeto <ArrowRight className="size-3.5" /></a><button type="button" aria-label="Fechar aviso" className="rounded-lg p-1 text-emerald-900/70 hover:bg-emerald-100" onClick={() => setCreated(null)}><X className="size-4" /></button></span></div>}
    <AgentPanel agentKey="comercial" title="Agente Comercial" roles={["sales"]} placeholder="Ex.: quais oportunidades estão paradas?" />
    {/* `tabIndex`/`role`/`aria-label`: uma faixa que rola na horizontal precisa receber foco,
        senão quem navega por teclado não alcança as etapas fora da tela (WCAG 2.1.1). */}
    {showArchived ? <section className="panel panel--flush">
      <div className="border-b px-5 py-4 sm:px-6"><h2 className="font-semibold text-ink">Oportunidades arquivadas</h2><p className="mt-1 text-sm text-slate-600">Fora do pipeline. Restaurar devolve a oportunidade à etapa em que estava.</p></div>
      {archived.length ? <div className="divide-y">{archived.map(item => <div className="flex flex-wrap items-center gap-3 px-5 py-4 sm:px-6" key={item.id}>
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{item.title}</p><p className="mt-0.5 text-xs text-slate-600">{item.stage_name} · {money.format(Number(item.estimated_value))}</p></div>
        <button className="btn btn--secondary shrink-0" disabled={restoring === item.id} onClick={() => void restore(item.id)}><RotateCcw className="size-4" />{restoring === item.id ? "Restaurando…" : "Restaurar"}</button>
      </div>)}</div> : <p className="px-6 py-10 text-center text-sm text-slate-600">Nenhuma oportunidade arquivada.</p>}
    </section> : <div className="flex gap-4 overflow-x-auto pb-3" tabIndex={0} role="region" aria-label="Etapas do pipeline">{stages.map(stage => { const items = opportunities.filter(item => item.stage === stage.id); return <section className="w-72 shrink-0 rounded-2xl border bg-slate-100/70 p-3" key={stage.id} onDragOver={event => event.preventDefault()} onDrop={event => void move(event, stage)}><header className="mb-3 flex items-center justify-between px-1"><div><h2 className="text-sm font-semibold text-ink">{stage.name}</h2><p className="mt-0.5 text-xs text-slate-600">{items.length} oportunidades</p></div><span className="rounded-lg bg-white px-2 py-1 text-xs font-semibold text-accent">{money.format(items.reduce((sum, item) => sum + Number(item.estimated_value), 0))}</span></header><div className="grid min-h-44 gap-3">{items.map(item => <article className="cursor-pointer rounded-xl border bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md active:cursor-grabbing" draggable key={item.id} onDragStart={event => event.dataTransfer.setData("opportunity", String(item.id))} onClick={() => void openDetail(item)}><div className="flex justify-between gap-2"><p className="text-sm font-semibold leading-5 text-ink">{item.title}</p><GripVertical className="size-4 shrink-0 cursor-grab text-slate-300" /></div>{item.service_name && <p className="mt-2"><span className={`state ${tierBadgeClass(item.service_tier)}`}>{item.service_name}</span></p>}<p className="mt-4 flex items-center gap-1.5 text-xs text-slate-600"><CalendarDays className="size-3.5" />{new Date(`${item.expected_close_date}T12:00:00`).toLocaleDateString("pt-BR")}</p><p className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-accent"><CircleDollarSign className="size-3.5" />{money.format(Number(item.estimated_value))}</p>{stage.kind === "won" && (item.project_archived
                /* Nem link (o projeto arquivado responde 404) nem "Criar projeto" (a conversão roda
                   uma vez e devolveria 409): o estado é a única informação honesta aqui. */
                ? <p className="mt-4 text-xs font-semibold text-slate-500">Projeto arquivado</p>
                : item.project
                ? <a className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-ink" href={`/projetos/${item.project}`} onClick={event => event.stopPropagation()}>Ver projeto <ArrowRight className="size-3.5" /></a>
                : <button className="back-link mt-4 text-xs" onClick={event => { event.stopPropagation(); setConverting(item); }}>Criar projeto <ArrowRight className="size-3.5" /></button>)}</article>)}{!items.length && <div className="empty-state grid min-h-24 place-items-center">Arraste uma oportunidade para esta etapa</div>}</div></section>; })}</div>}
    {isComposerOpen && <Modal title="Nova oportunidade" onClose={() => setComposerOpen(false)}><form className="grid gap-4" onSubmit={event => void createOpportunity(event)}><Field label="Título"><input className="field" value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} required /></Field><Field label="Cliente"><select className="field" value={draft.account} onChange={event => setDraft({ ...draft, account: event.target.value })} required><option value="">Selecione</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></Field><Field label="Nível de produto"><select className="field" value={draft.service} onChange={event => setDraft({ ...draft, service: event.target.value })}><option value="">Sem nível definido</option>{sellableServices.map(service => <option key={service.id} value={service.id}>{rotuloDoDegrau(service)}</option>)}</select></Field><div className="form-grid"><Field label="Valor estimado"><input className="field" type="number" min="0" step="0.01" value={draft.estimated_value} onChange={event => setDraft({ ...draft, estimated_value: event.target.value })} required /></Field><Field label="Previsão de fechamento"><input className="field" type="date" value={draft.expected_close_date} onChange={event => setDraft({ ...draft, expected_close_date: event.target.value })} required /></Field></div><button className="btn" type="submit">Adicionar ao pipeline</button></form></Modal>}
    {converting && <Modal title="Criar projeto" onClose={() => setConverting(null)}><p className="mb-5 text-sm text-slate-600">Você está convertendo <strong className="text-ink">{converting.title}</strong>. Defina a janela inicial de entrega.</p><form className="grid gap-4" onSubmit={event => void convert(event)}><div className="form-grid"><Field label="Início"><input className="field" type="date" value={dates.start_date} onChange={event => setDates({ ...dates, start_date: event.target.value })} required /></Field><Field label="Prazo final"><input className="field" type="date" value={dates.due_date} onChange={event => setDates({ ...dates, due_date: event.target.value })} required /></Field></div><button className="btn" type="submit">Criar projeto</button></form></Modal>}
    {archiving && <ConfirmDialog
      title="Arquivar oportunidade"
      message={<>A oportunidade <strong className="text-ink">{archiving.title}</strong> sai do pipeline e do histórico ativo. Ela continua guardada e pode ser restaurada depois.</>}
      confirmLabel="Arquivar"
      busy={archiveBusy}
      onCancel={() => setArchiving(null)}
      onConfirm={() => void archiveOpportunity()}
    />}
    {detail && <Modal title="Detalhe da oportunidade" width="3xl" onClose={() => { setDetail(null); setDetailError(""); setDetailNotice(""); }}>
      {detailError && <p role="alert" className="alert--error mb-4">{detailError}</p>}
      {detailNotice && <p role="status" className="alert--ok mb-4">{detailNotice}</p>}
      <form className="grid gap-4" onSubmit={event => void saveDetail(event)}>
        <Field label="Título"><input className="field" value={detailDraft.title} onChange={event => setDetailDraft({ ...detailDraft, title: event.target.value })} required /></Field>
        <Field label="Escopo"><textarea className="field min-h-20" value={detailDraft.scope} onChange={event => setDetailDraft({ ...detailDraft, scope: event.target.value })} placeholder="Descreva o escopo da negociação" /></Field>
        <div className="form-grid"><Field label="Valor estimado"><input className="field" type="number" min="0" step="0.01" value={detailDraft.estimated_value} onChange={event => setDetailDraft({ ...detailDraft, estimated_value: event.target.value })} required /></Field><Field label="Previsão de fechamento"><input className="field" type="date" value={detailDraft.expected_close_date} onChange={event => setDetailDraft({ ...detailDraft, expected_close_date: event.target.value })} required /></Field></div>
        <div className="form-grid"><Field label="Contato"><select className="field" value={detailDraft.contact} onChange={event => setDetailDraft({ ...detailDraft, contact: event.target.value })}><option value="">Sem contato</option>{detailContacts.map(contact => <option key={contact.id} value={contact.id}>{contact.name}</option>)}</select></Field><Field label="Etapa"><select className="field" value={detailDraft.stage} onChange={event => setDetailDraft({ ...detailDraft, stage: event.target.value })}>{stages.map(stage => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></Field></div>
        <Field label="Nível de produto"><select className="field" value={detailDraft.service} onChange={event => setDetailDraft({ ...detailDraft, service: event.target.value })}><option value="">Sem nível definido</option>{sellableServices.map(service => <option key={service.id} value={service.id}>{rotuloDoDegrau(service)}</option>)}</select></Field>
        <div className="flex flex-wrap gap-3"><button className="btn" type="submit"><Save className="size-4" />Salvar</button>{stages.find(stage => stage.id === detail.stage)?.kind === "won" && (detail.project_archived
          ? <p className="empty-state inline-flex items-center py-3">Projeto arquivado — restaure em Projetos para retomar</p>
          : detail.project
          ? <a className="btn btn--secondary" href={`/projetos/${detail.project}`}>Ver projeto <ArrowRight className="size-4 text-emerald-600" /></a>
          : <button type="button" className="btn btn--secondary" onClick={() => startConversion(detail)}>Converter em projeto <ArrowRight className="size-4 text-brand-500" /></button>)}
          {user?.is_admin && <button type="button" className="btn btn--secondary btn--secondary-danger ml-auto" onClick={() => setArchiving(detail)}><Trash2 className="size-4" />Arquivar</button>}</div>
      </form>
      <div className="mt-6 border-t pt-5">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink"><FileText className="size-4 text-accent" />Documentos</h3>
        {detailDocs.length ? <div className="mt-3 divide-y">{detailDocs.map(doc => <div className="flex items-center gap-3 py-2" key={doc.id}><FileText className="size-4 shrink-0 text-slate-600" /><span className="min-w-0 flex-1 truncate text-sm text-ink">{doc.original_name}</span>{doc.drive_link && <a className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 hover:text-accent" href={doc.drive_link} target="_blank" rel="noreferrer" aria-label={`Abrir ${doc.original_name} no Drive`}>Drive</a>}<a className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-accent" href={documentDownloadUrl(doc.id)} aria-label={`Baixar ${doc.original_name}`}><Download className="size-4" /></a></div>)}</div> : <p className="mt-3 text-sm text-slate-600">Nenhum documento vinculado.</p>}
        <form className="mt-3 flex gap-2" onSubmit={event => void uploadDetailDoc(event)}><input className="field" type="file" ref={detailFile} aria-label="Arquivo da oportunidade" /><button className="btn btn--icon" aria-label="Enviar documento" type="submit"><UploadCloud className="size-4" /></button></form>
      </div>
      <div className="mt-6 border-t pt-5">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink"><MessageSquareText className="size-4 text-accent" />Interações</h3>
        {detailActivities.length ? <div className="panel-rows mt-3">{detailActivities.map(activity => <div className="row" key={activity.id}>
          <div className="row-main">
            <strong>{activity.summary}</strong>
            <span>{activity.kind_display} · {new Date(`${activity.happened_on}T12:00:00`).toLocaleDateString("pt-BR")}</span>
            {activity.notes && <span>{activity.notes}</span>}
          </div>
          {canWriteBeyondDelivery(user) && <div className="row-meta justify-end"><button className="rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-danger" aria-label={`Arquivar interação: ${activity.summary}`} onClick={() => void archiveDetailActivity(activity)}><Trash2 className="size-4" /></button></div>}
        </div>)}</div> : <p className="mt-3 text-sm text-slate-600">Nenhuma interação registrada.</p>}
        {canWriteBeyondDelivery(user) && <form className="form-grid mt-3" onSubmit={event => void createDetailActivity(event)}>
          <label className="form-label">Tipo<select className="field" value={activityDraft.kind} onChange={event => setActivityDraft({ ...activityDraft, kind: event.target.value as ActivityKind })}>{Object.entries(activityKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="form-label">Data<input className="field" type="date" value={activityDraft.happened_on} onChange={event => setActivityDraft({ ...activityDraft, happened_on: event.target.value })} required /></label>
          <label className="form-label sm:col-span-2">Resumo<input className="field" value={activityDraft.summary} onChange={event => setActivityDraft({ ...activityDraft, summary: event.target.value })} placeholder="Do que se tratou o contato" required /></label>
          <label className="form-label sm:col-span-2">Notas<textarea className="field min-h-20" value={activityDraft.notes} onChange={event => setActivityDraft({ ...activityDraft, notes: event.target.value })} placeholder="Opcional" /></label>
          <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Registrar interação</button>
        </form>}
      </div>
      {aiEnabled && <div className="mt-6 border-t pt-5">
        <div className="flex flex-wrap items-center gap-2"><Sparkles className="size-4 text-accent" /><h3 className="text-sm font-semibold text-ink">IA</h3><button type="button" className="btn btn--secondary ml-auto" onClick={() => void runAi("summary")} disabled={aiBusy}>Resumir</button><button type="button" className="btn btn--secondary" onClick={() => void runAi("proposal")} disabled={aiBusy}>Gerar proposta</button><button type="button" className="btn btn--secondary" onClick={() => void runAi("contract")} disabled={aiBusy}>Gerar contrato</button></div>
        {aiBusy && <p className="mt-3 text-sm text-slate-600">Gerando…</p>}
        {aiText && <div className="mt-3"><textarea className="field min-h-64 resize-y" value={aiText} onChange={event => setAiText(event.target.value)} aria-label="Rascunho gerado pela IA" /><div className="mt-2 flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-slate-600">Revise antes de salvar — a IA gera um rascunho.</p><button type="button" className="btn" onClick={() => void saveSummaryAsDocument()}>Salvar como documento</button></div></div>}
      </div>}
      <ArtifactsPanel opportunity={detail.id} reloadToken={artifactsToken} onChange={reloadDetailDocs} />
    </Modal>}
  </section>;
}

// Os seis degraus avançam da call gratuita à parceria contínua, e a cor acompanha a escada: os
// dois primeiros são a porta (claros), os dois do meio provam (intermediários), os dois últimos
// são compromisso de produção (escuros). Ler a coluna do pipeline deve dizer, sem legenda, o quão
// fundo cada negociação está. Eram sete até a ADR 0053 tirar o `discovery_assessment`.
const tierBadges: Record<ServiceTier, string> = {
  qualification_call: "state--off",
  discovery_sprint: "state--0",
  feasibility: "state--1",
  prove: "state--1",
  scale: "bg-ink text-white",
  transformation: "bg-ink text-white",
  "": "state--off",
};
function tierBadgeClass(tier: ServiceTier) { return tierBadges[tier] ?? tierBadges[""]; }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="form-label">{label}{children}</label>; }
