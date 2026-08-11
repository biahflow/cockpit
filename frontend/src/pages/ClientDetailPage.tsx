import { ArrowLeft, Briefcase, Mail, Phone, Plus, Save, Trash2, UserRound } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import { HealthBadge } from "../components/StatusDot";
import type { Client, ClientOverview, ClientStatus, Contact, Vertical } from "../types";

const blankContact = { name: "", email: "", phone: "", job_title: "" };

export function ClientDetailPage({ id }: { id: number }) {
  const [client, setClient] = useState<Client>();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [overview, setOverview] = useState<ClientOverview>();
  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [form, setForm] = useState<{ name: string; legal_name: string; tax_id: string; status: ClientStatus; vertical: string }>({ name: "", legal_name: "", tax_id: "", status: "prospect", vertical: "" });
  const [contactDraft, setContactDraft] = useState(blankContact);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [removingContact, setRemovingContact] = useState<Contact | null>(null);
  const [isArchiving, setArchiving] = useState(false);
  const [busy, setBusy] = useState(false);
  const { user } = useAuth();
  const canArchive = !!user?.is_admin;

  const load = useCallback(() => Promise.all([
    api<Client>(`/clients/${id}/`),
    api<Contact[]>(`/contacts/?client=${id}`),
    api<ClientOverview>(`/clients/${id}/overview/`),
    api<Vertical[]>("/verticals/"),
  ]).then(([loadedClient, loadedContacts, loadedOverview, loadedVerticals]) => {
    setClient(loadedClient); setContacts(loadedContacts); setOverview(loadedOverview); setVerticals(loadedVerticals);
    setForm({ name: loadedClient.name, legal_name: loadedClient.legal_name, tax_id: loadedClient.tax_id, status: loadedClient.status, vertical: loadedClient.vertical ? String(loadedClient.vertical) : "" });
  }).catch((cause: Error) => setError(cause.message)), [id]);
  useEffect(() => { void load(); }, [load]);

  async function saveClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaved(false);
    try { await api(`/clients/${id}/`, { method: "PATCH", body: JSON.stringify({ ...form, vertical: form.vertical ? Number(form.vertical) : null }) }); setSaved(true); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/contacts/", { method: "POST", body: JSON.stringify({ client: id, ...contactDraft }) }); setContactDraft(blankContact); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function removeContact() {
    if (!removingContact) return;
    setBusy(true);
    try { await api(`/contacts/${removingContact.id}/`, { method: "DELETE" }); setRemovingContact(null); await load(); }
    catch (cause) { setRemovingContact(null); setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function archiveClient() {
    setBusy(true);
    try {
      await api(`/clients/${id}/`, { method: "DELETE" });
      window.location.assign("/clientes");
    } catch (cause) {
      // O 409 das guardas de integridade chega aqui com o motivo ("ainda tem 2 projeto(s)…"),
      // que é exatamente o que quem tentou precisa ler para saber o que fazer antes.
      setArchiving(false); setError((cause as Error).message); setBusy(false);
    }
  }

  if (error && !client) return <div role="alert" className="alert--error">{error}</div>;
  if (!client) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  return <section className="space-y-7">
    <a href="/clientes" className="back-link"><ArrowLeft className="size-4" />Voltar para clientes</a>
    {removingContact && <ConfirmDialog
      title="Remover contato"
      message={<>Remover <strong className="text-ink">{removingContact.name}</strong> da lista de contatos deste cliente?</>}
      confirmLabel="Remover" busy={busy}
      onCancel={() => setRemovingContact(null)} onConfirm={() => void removeContact()}
    />}
    {isArchiving && <ConfirmDialog
      title="Arquivar cliente"
      message={<>O cliente <strong className="text-ink">{client.name}</strong> e os contatos dele saem das listagens ativas. Nada é apagado — dá para restaurar depois pela aba Arquivados.</>}
      confirmLabel="Arquivar" busy={busy}
      onCancel={() => setArchiving(false)} onConfirm={() => void archiveClient()}
    />}
    <header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="eyebrow">Relacionamento</p><h1>{client.name}</h1><p>Dados cadastrais e contatos do cliente.</p></div>
      {canArchive && <button type="button" className="btn btn--secondary btn--secondary-danger shrink-0 self-start sm:self-auto" onClick={() => setArchiving(true)}><Trash2 className="size-4" />Arquivar cliente</button>}
    </header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    {overview && (overview.health
      ? <section className="panel sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2"><h2 className="font-semibold text-ink">Saúde da relação</h2><HealthBadge level={overview.health.level} score={overview.health.score} /></div>
            {overview.phase && <span className="text-xs font-semibold uppercase tracking-wide text-accent">Você está aqui · {overview.phase.name}</span>}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Metric label="Risco de atraso" value={overview.risk_level ?? "—"} />
            <Metric label="ROI acumulado" value={overview.roi.roi != null ? `${Math.round(overview.roi.roi * 100)}%` : "—"} />
            <Metric label="Próxima reunião" value={overview.next_meeting ? `${overview.next_meeting.title} · ${overview.next_meeting.date}` : "A agendar"} />
          </div>
          {overview.ai_score && <div className="mt-3 grid gap-3 border-t pt-3 sm:grid-cols-2">
            <Metric label="Maturidade de IA" value={overview.ai_score.maturity != null ? `${overview.ai_score.maturity}/100` : "—"} />
            <Metric label="Oportunidade de IA" value={overview.ai_score.opportunity != null ? `${overview.ai_score.opportunity}/100` : "—"} />
          </div>}
        </section>
      : <p className="empty-state">Sem projeto ativo — a saúde da relação aparece quando houver uma jornada em andamento.</p>
    )}

    <div className="grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
      <form className="panel space-y-4 sm:p-6" onSubmit={event => void saveClient(event)}>
        <h2 className="font-semibold text-ink">Dados do cliente</h2>
        <Field label="Nome"><input className="field" value={form.name} onChange={event => { setForm({ ...form, name: event.target.value }); setSaved(false); }} required /></Field>
        <Field label="Razão social"><input className="field" value={form.legal_name} onChange={event => { setForm({ ...form, legal_name: event.target.value }); setSaved(false); }} placeholder="Opcional" /></Field>
        <Field label="CNPJ / CPF"><input className="field" value={form.tax_id} onChange={event => { setForm({ ...form, tax_id: event.target.value }); setSaved(false); }} placeholder="Opcional" /></Field>
        {/* Corrige o que foi digitado errado no cadastro. Voltar para prospect é recusado pela API
            quando o cliente já tem oportunidade ganha — o que o sistema observou não se desdiz. */}
        {/* A vertical escolhe a variante do blueprint quando a entrega instancia um Funcionário
            Digital (FDD 026). Sem ela nada quebra: o catálogo inteiro segue disponível, com os
            valores genéricos. */}
        <Field label="Vertical"><select className="field" value={form.vertical} onChange={event => { setForm({ ...form, vertical: event.target.value }); setSaved(false); }}><option value="">Sem vertical definida</option>{verticals.filter(vertical => vertical.active || String(vertical.id) === form.vertical).map(vertical => <option key={vertical.id} value={vertical.id}>{vertical.name}</option>)}</select></Field>
        <Field label="Situação"><select className="field" value={form.status} onChange={event => { setForm({ ...form, status: event.target.value as ClientStatus }); setSaved(false); }}><option value="prospect">Prospect — ainda não fechou</option><option value="active">Cliente ativo — já fechou</option></select></Field>
        <button className="btn" type="submit"><Save className="size-4" />Salvar alterações</button>
        {saved && <p className="text-sm font-medium text-emerald-700">Dados atualizados.</p>}
      </form>

      <section className="panel space-y-4 sm:p-6">
        <div className="flex items-center gap-3"><span className="metric-icon"><UserRound className="size-4" /></span><div><h2 className="font-semibold text-ink">Contatos</h2><p className="text-sm text-slate-600">{contacts.length} {contacts.length === 1 ? "contato" : "contatos"}</p></div></div>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={event => void createContact(event)}>
          <input className="field" placeholder="Nome" value={contactDraft.name} onChange={event => setContactDraft({ ...contactDraft, name: event.target.value })} required />
          <input className="field" type="email" placeholder="E-mail" value={contactDraft.email} onChange={event => setContactDraft({ ...contactDraft, email: event.target.value })} />
          <input className="field" placeholder="Telefone" value={contactDraft.phone} onChange={event => setContactDraft({ ...contactDraft, phone: event.target.value })} />
          <input className="field" placeholder="Cargo" value={contactDraft.job_title} onChange={event => setContactDraft({ ...contactDraft, job_title: event.target.value })} />
          <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Adicionar contato</button>
        </form>
        {contacts.length ? <div className="divide-y">{contacts.map(contact => <div className="flex items-start gap-3 py-3" key={contact.id}><span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><UserRound className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{contact.name}</p>{contact.job_title && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Briefcase className="size-3" />{contact.job_title}</p>}{contact.email && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Mail className="size-3" />{contact.email}</p>}{contact.phone && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Phone className="size-3" />{contact.phone}</p>}</div><button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-danger" aria-label={`Remover ${contact.name}`} onClick={() => setRemovingContact(contact)}><Trash2 className="size-4" /></button></div>)}</div> : <p className="empty-state">Nenhum contato cadastrado.</p>}
      </section>
    </div>
  </section>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="form-label">{label}{children}</label>; }

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-slate-50 px-4 py-3"><p className="text-xs text-slate-600">{label}</p><p className="mt-1 text-sm font-semibold text-ink">{value}</p></div>; }
