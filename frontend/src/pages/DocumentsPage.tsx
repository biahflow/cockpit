import { Download, FileText, Paperclip, PenLine, RotateCcw, Trash2, UploadCloud } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { api, documentDownloadUrl } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import type { Account, CommercialOpportunity, DocumentEntry, Project } from "../types";

// A chave **é** o nome do campo no corpo do `POST /documents/`, então ela é a canônica: a SPA
// não escreve o alias que a `/api/v1/` mantém para quem integrou antes do renome (#67).
type LinkType = "account" | "commercial_opportunity" | "project";
const linkLabel: Record<LinkType, string> = { account: "Cliente", commercial_opportunity: "Oportunidade", project: "Projeto" };

export function DocumentsPage() {
  const { esignEnabled, user } = useAuth();
  // Entrega só enxerga o documento do projeto em que atua (FDD 017): oferecer cliente ou
  // oportunidade aqui produziria um upload que o backend recusa com 403.
  // Idem: restrição, não papel. Sem isto o superusuário não anexava documento a cliente nem a
  // oportunidade — e, porque o fetch de oportunidades era pulado, os já existentes apareciam
  // como id cru ("Oportunidade: 17").
  const isDelivery = user?.role === "delivery" && !user.is_admin;
  const [documents, setDocuments] = useState<DocumentEntry[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [opportunities, setOpportunities] = useState<CommercialOpportunity[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [linkType, setLinkType] = useState<LinkType>(isDelivery ? "project" : "account");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [isUploading, setUploading] = useState(false);
  const [archiving, setArchiving] = useState<DocumentEntry | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => Promise.all([
    api<DocumentEntry[]>(`/documents/${showArchived ? "?archived=1" : ""}`),
    api<Account[]>("/clients/"),
    isDelivery ? Promise.resolve<CommercialOpportunity[]>([]) : api<CommercialOpportunity[]>("/opportunities/"),
    api<Project[]>("/projects/"),
  ]).then(([loadedDocuments, loadedAccounts, loadedOpportunities, loadedProjects]) => {
    setDocuments(loadedDocuments); setAccounts(loadedAccounts); setOpportunities(loadedOpportunities); setProjects(loadedProjects);
  }).catch((cause: Error) => setError(cause.message)), [isDelivery, showArchived]);
  useEffect(() => { void load(); }, [load]);

  const targets: { id: number; label: string }[] = linkType === "account"
    ? accounts.map(item => ({ id: item.id, label: item.name }))
    : linkType === "commercial_opportunity"
      ? opportunities.map(item => ({ id: item.id, label: item.title }))
      : projects.map(item => ({ id: item.id, label: item.name }));

  function labelFor(document: DocumentEntry): string {
    if (document.account) return `${linkLabel.account}: ${accounts.find(item => item.id === document.account)?.name ?? document.account}`;
    if (document.commercial_opportunity) return `${linkLabel.commercial_opportunity}: ${opportunities.find(item => item.id === document.commercial_opportunity)?.title ?? document.commercial_opportunity}`;
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
  async function restore(id: number) {
    setError(""); setRestoring(id);
    try { await api(`/documents/${id}/unarchive/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setRestoring(null); }
  }
  async function archive() {
    if (!archiving) return;
    setArchiveBusy(true);
    try { await api(`/documents/${archiving.id}/`, { method: "DELETE" }); setArchiving(null); await load(); }
    catch (cause) { setArchiving(null); setError((cause as Error).message); }
    finally { setArchiveBusy(false); }
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
    {archiving && <ConfirmDialog
      title="Arquivar documento"
      message={<>O arquivo <strong className="text-ink">{archiving.original_name}</strong> sai da listagem. Ele continua guardado e pode ser restaurado.</>}
      confirmLabel="Arquivar" busy={archiveBusy}
      onCancel={() => setArchiving(null)} onConfirm={() => void archive()}
    />}
    <header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Documentos</p><h1>Arquivos do portal</h1><p>Documentos privados vinculados a clientes, oportunidades ou projetos.</p></div><span className="self-start rounded-xl bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-700 sm:self-auto">{documents.length} arquivos</span></header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <form className="panel space-y-4 sm:p-6" onSubmit={event => void upload(event)}>
        <div className="flex items-center gap-3"><span className="metric-icon size-10"><UploadCloud className="size-5" /></span><div><h2 className="font-semibold text-ink">Enviar documento</h2><p className="text-sm text-slate-600">Vincule a exatamente um recurso.</p></div></div>
        <label className="form-label">Vincular a<select className="field" value={linkType} onChange={event => { setLinkType(event.target.value as LinkType); setTarget(""); }}>{!isDelivery && <option value="account">Cliente</option>}{!isDelivery && <option value="commercial_opportunity">Oportunidade</option>}<option value="project">Projeto</option></select></label>
        <label className="form-label">{linkLabel[linkType]}<select className="field" value={target} onChange={event => setTarget(event.target.value)} required><option value="">Selecione</option>{targets.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="form-label">Arquivo<input className="field file:mr-3 file:rounded-lg file:border-0 file:bg-accent-50 file:px-3 file:py-1 file:text-accent" type="file" ref={fileInput} /></label>
        <button className="btn w-full" type="submit" disabled={isUploading}><UploadCloud className="size-4" />{isUploading ? "Enviando…" : "Enviar documento"}</button>
      </form>

      <section className="panel panel--flush">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-5 sm:px-6"><div><h2 className="font-semibold text-ink">{showArchived ? "Arquivados" : "Documentos enviados"}</h2><p className="mt-1 text-sm text-slate-600">{showArchived ? "Fora da listagem ativa. Restaurar devolve o arquivo." : "Baixe ou arquive quando necessário."}</p></div><div className="flex gap-1 rounded-xl bg-slate-50 p-1"><button className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${showArchived ? "text-slate-600 hover:text-ink" : "bg-white text-accent shadow-sm"}`} onClick={() => setShowArchived(false)}>Ativos</button><button className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${showArchived ? "bg-white text-accent shadow-sm" : "text-slate-600 hover:text-ink"}`} onClick={() => setShowArchived(true)}>Arquivados</button></div></div>
        {documents.length ? <div className="divide-y">{documents.map(document => { const pending = document.signature_requests.filter(request => request.status === "pending"); return <div className="px-5 py-4 sm:px-6" key={document.id}>
          <div className="flex items-center gap-4"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><FileText className="size-4" /></span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{document.original_name}</p><p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-600"><Paperclip className="size-3" />{labelFor(document)}</p></div>{showArchived ? <button className="btn btn--secondary shrink-0" disabled={restoring === document.id} onClick={() => void restore(document.id)}><RotateCcw className="size-4" />{restoring === document.id ? "Restaurando…" : "Restaurar"}</button> : <>{document.drive_link && <a className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 hover:text-accent" href={document.drive_link} target="_blank" rel="noreferrer" aria-label={`Abrir ${document.original_name} no Drive`}>Drive</a>}{esignEnabled && pending.length > 0 && <button className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 hover:text-accent" aria-label={`Lembrar assinantes de ${document.original_name}`} onClick={() => void remindSignatures(document.id)}>Lembrar</button>}{esignEnabled && <button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-accent-50 hover:text-accent" aria-label={`Enviar ${document.original_name} para assinatura`} onClick={() => void requestSignature(document.id)}><PenLine className="size-4" /></button>}<a className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-accent-50 hover:text-accent" href={documentDownloadUrl(document.id)} aria-label={`Baixar ${document.original_name}`}><Download className="size-4" /></a><button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-danger" aria-label={`Arquivar ${document.original_name}`} onClick={() => setArchiving(document)}><Trash2 className="size-4" /></button></>}</div>
          {document.signature_requests.length > 0 && <ul className="mt-2 space-y-1 pl-14">{document.signature_requests.map(request => <li className="flex items-center gap-2 text-xs" key={request.id}><span className={`state ${request.status === "signed" ? "state--1" : request.status === "declined" ? "state--3" : "state--2"}`}>{request.status === "signed" ? "Assinado" : request.status === "declined" ? "Recusado" : "Pendente"}</span><span className="min-w-0 flex-1 truncate text-slate-600">{request.signer_email}</span>{request.status === "pending" && request.sign_url && <a className="shrink-0 font-semibold text-accent hover:text-ink" href={request.sign_url} target="_blank" rel="noreferrer" aria-label={`Abrir link de assinatura de ${request.signer_email}`}>Assinar</a>}{request.status === "pending" && <button className="shrink-0 font-semibold text-accent hover:text-ink" onClick={() => void markSigned(document.id, request.id)}>Marcar assinado</button>}</li>)}</ul>}
        </div>; })}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-50 text-accent"><FileText className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">{showArchived ? "Nada arquivado" : "Nenhum documento ainda"}</p><p className="mt-1 text-sm text-slate-600">{showArchived ? "Documentos arquivados aparecem aqui e podem voltar." : "Envie o primeiro arquivo ao lado."}</p></div></div>}
      </section>
    </div>
  </section>;
}
