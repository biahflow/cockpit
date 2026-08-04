import { Download, FileText, Paperclip, PenLine, Trash2, UploadCloud } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { api, documentDownloadUrl } from "../api";
import { useAuth } from "../auth";
import type { Client, DocumentEntry, Opportunity, Project } from "../types";

type LinkType = "client" | "opportunity" | "project";
const linkLabel: Record<LinkType, string> = { client: "Cliente", opportunity: "Oportunidade", project: "Projeto" };

export function DocumentsPage() {
  const { esignEnabled } = useAuth();
  const [documents, setDocuments] = useState<DocumentEntry[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [linkType, setLinkType] = useState<LinkType>("client");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [isUploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => Promise.all([
    api<DocumentEntry[]>("/documents/"),
    api<Client[]>("/clients/"),
    api<Opportunity[]>("/opportunities/"),
    api<Project[]>("/projects/"),
  ]).then(([loadedDocuments, loadedClients, loadedOpportunities, loadedProjects]) => {
    setDocuments(loadedDocuments); setClients(loadedClients); setOpportunities(loadedOpportunities); setProjects(loadedProjects);
  }).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);

  const targets: { id: number; label: string }[] = linkType === "client"
    ? clients.map(item => ({ id: item.id, label: item.name }))
    : linkType === "opportunity"
      ? opportunities.map(item => ({ id: item.id, label: item.title }))
      : projects.map(item => ({ id: item.id, label: item.name }));

  function labelFor(document: DocumentEntry): string {
    if (document.client) return `${linkLabel.client}: ${clients.find(item => item.id === document.client)?.name ?? document.client}`;
    if (document.opportunity) return `${linkLabel.opportunity}: ${opportunities.find(item => item.id === document.opportunity)?.title ?? document.opportunity}`;
    if (document.project) return `${linkLabel.project}: ${projects.find(item => item.id === document.project)?.name ?? document.project}`;
    return "Sem vínculo";
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file || !target) { setError("Selecione um vínculo e um arquivo."); return; }
    setUploading(true); setError("");
    try {
      const body = new FormData();
      body.append(linkType, target);
      body.append("file", file);
      await api("/documents/", { method: "POST", body });
      setTarget(""); if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (cause) { setError((cause as Error).message); } finally { setUploading(false); }
  }
  async function archive(id: number) {
    try { await api(`/documents/${id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function requestSignature(id: number) {
    const email = window.prompt("E-mail do signatário:");
    if (!email) return;
    try { await api(`/documents/${id}/request-signature/`, { method: "POST", body: JSON.stringify({ signer_email: email }) }); setError(""); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function remindSignatures(id: number) {
    try { await api(`/documents/${id}/remind-signature/`, { method: "POST" }); setError(""); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function markSigned(id: number, signature: number) {
    try { await api(`/documents/${id}/mark-signed/`, { method: "POST", body: JSON.stringify({ signature }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="space-y-7">
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Documentos</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Arquivos do portal</h1><p className="mt-2 text-sm text-slate-500">Documentos privados vinculados a clientes, oportunidades ou projetos.</p></div><span className="self-start rounded-xl bg-mint px-3 py-2 text-sm font-semibold text-ocean sm:self-auto">{documents.length} arquivos</span></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}

    <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <form className="space-y-4 rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void upload(event)}>
        <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-mint text-ocean"><UploadCloud className="size-5" /></span><div><h2 className="font-semibold text-ink">Enviar documento</h2><p className="text-sm text-slate-500">Vincule a exatamente um recurso.</p></div></div>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Vincular a<select className="field" value={linkType} onChange={event => { setLinkType(event.target.value as LinkType); setTarget(""); }}><option value="client">Cliente</option><option value="opportunity">Oportunidade</option><option value="project">Projeto</option></select></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">{linkLabel[linkType]}<select className="field" value={target} onChange={event => setTarget(event.target.value)} required><option value="">Selecione</option>{targets.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Arquivo<input className="field file:mr-3 file:rounded-lg file:border-0 file:bg-mint file:px-3 file:py-1 file:text-ocean" type="file" ref={fileInput} /></label>
        <button className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60" type="submit" disabled={isUploading}><UploadCloud className="size-4" />{isUploading ? "Enviando…" : "Enviar documento"}</button>
      </form>

      <section className="overflow-hidden rounded-2xl border bg-white">
        <div className="border-b px-5 py-5 sm:px-6"><h2 className="font-semibold text-ink">Documentos enviados</h2><p className="mt-1 text-sm text-slate-500">Baixe ou arquive quando necessário.</p></div>
        {documents.length ? <div className="divide-y">{documents.map(document => { const pending = document.signature_requests.filter(request => request.status === "pending"); return <div className="px-5 py-4 sm:px-6" key={document.id}>
          <div className="flex items-center gap-4"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><FileText className="size-4" /></span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{document.original_name}</p><p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500"><Paperclip className="size-3" />{labelFor(document)}</p></div>{document.drive_link && <a className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-400 hover:text-ocean" href={document.drive_link} target="_blank" rel="noreferrer" aria-label={`Abrir ${document.original_name} no Drive`}>Drive</a>}{esignEnabled && pending.length > 0 && <button className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-400 hover:text-ocean" aria-label={`Lembrar assinantes de ${document.original_name}`} onClick={() => void remindSignatures(document.id)}>Lembrar</button>}{esignEnabled && <button className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-mint hover:text-ocean" aria-label={`Enviar ${document.original_name} para assinatura`} onClick={() => void requestSignature(document.id)}><PenLine className="size-4" /></button>}<a className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-mint hover:text-ocean" href={documentDownloadUrl(document.id)} aria-label={`Baixar ${document.original_name}`}><Download className="size-4" /></a><button className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-signal" aria-label={`Arquivar ${document.original_name}`} onClick={() => void archive(document.id)}><Trash2 className="size-4" /></button></div>
          {document.signature_requests.length > 0 && <ul className="mt-2 space-y-1 pl-14">{document.signature_requests.map(request => <li className="flex items-center gap-2 text-xs" key={request.id}><span className={`rounded-full px-2 py-0.5 font-semibold ${request.status === "signed" ? "bg-emerald-50 text-emerald-700" : request.status === "declined" ? "bg-red-50 text-signal" : "bg-amber-50 text-amber-700"}`}>{request.status === "signed" ? "Assinado" : request.status === "declined" ? "Recusado" : "Pendente"}</span><span className="min-w-0 flex-1 truncate text-slate-500">{request.signer_email}</span>{request.status === "pending" && <button className="shrink-0 font-semibold text-ocean hover:text-ink" onClick={() => void markSigned(document.id, request.id)}>Marcar assinado</button>}</li>)}</ul>}
        </div>; })}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-mint text-ocean"><FileText className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">Nenhum documento ainda</p><p className="mt-1 text-sm text-slate-500">Envie o primeiro arquivo ao lado.</p></div></div>}
      </section>
    </div>
  </section>;
}
