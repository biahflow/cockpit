import { ArrowLeft, Briefcase, Mail, Phone, Plus, Save, Trash2, UserRound } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { HealthBadge } from "../components/StatusDot";
import type { Client, ClientOverview, ClientStatus, Contact } from "../types";

const blankContact = { name: "", email: "", phone: "", job_title: "" };

export function ClientDetailPage({ id }: { id: number }) {
  const [client, setClient] = useState<Client>();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [overview, setOverview] = useState<ClientOverview>();
  const [form, setForm] = useState<{ name: string; legal_name: string; tax_id: string; status: ClientStatus }>({ name: "", legal_name: "", tax_id: "", status: "prospect" });
  const [contactDraft, setContactDraft] = useState(blankContact);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => Promise.all([
    api<Client>(`/clients/${id}/`),
    api<Contact[]>(`/contacts/?client=${id}`),
    api<ClientOverview>(`/clients/${id}/overview/`),
  ]).then(([loadedClient, loadedContacts, loadedOverview]) => {
    setClient(loadedClient); setContacts(loadedContacts); setOverview(loadedOverview);
    setForm({ name: loadedClient.name, legal_name: loadedClient.legal_name, tax_id: loadedClient.tax_id, status: loadedClient.status });
  }).catch((cause: Error) => setError(cause.message)), [id]);
  useEffect(() => { void load(); }, [load]);

  async function saveClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaved(false);
    try { await api(`/clients/${id}/`, { method: "PATCH", body: JSON.stringify(form) }); setSaved(true); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/contacts/", { method: "POST", body: JSON.stringify({ client: id, ...contactDraft }) }); setContactDraft(blankContact); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function removeContact(contactId: number) {
    try { await api(`/contacts/${contactId}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  if (error && !client) return <div role="alert" className="rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-signal">{error}</div>;
  if (!client) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  return <section className="space-y-7">
    <a href="/clientes" className="inline-flex items-center gap-2 text-sm font-semibold text-ocean hover:text-ink"><ArrowLeft className="size-4" />Voltar para clientes</a>
    <header><p className="text-sm font-semibold text-ocean">Relacionamento</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">{client.name}</h1><p className="mt-2 text-sm text-slate-600">Dados cadastrais e contatos do cliente.</p></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}

    {overview && (overview.health
      ? <section className="rounded-2xl border bg-white p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2"><h2 className="font-semibold text-ink">Saúde da relação</h2><HealthBadge level={overview.health.level} score={overview.health.score} /></div>
            {overview.phase && <span className="text-xs font-semibold uppercase tracking-wide text-ocean">Você está aqui · {overview.phase.name}</span>}
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
      : <p className="rounded-2xl border border-dashed bg-slate-50/60 px-4 py-4 text-sm text-slate-600">Sem projeto ativo — a saúde da relação aparece quando houver uma jornada em andamento.</p>
    )}

    <div className="grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
      <form className="space-y-4 rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void saveClient(event)}>
        <h2 className="font-semibold text-ink">Dados do cliente</h2>
        <Field label="Nome"><input className="field" value={form.name} onChange={event => { setForm({ ...form, name: event.target.value }); setSaved(false); }} required /></Field>
        <Field label="Razão social"><input className="field" value={form.legal_name} onChange={event => { setForm({ ...form, legal_name: event.target.value }); setSaved(false); }} placeholder="Opcional" /></Field>
        <Field label="CNPJ / CPF"><input className="field" value={form.tax_id} onChange={event => { setForm({ ...form, tax_id: event.target.value }); setSaved(false); }} placeholder="Opcional" /></Field>
        {/* Corrige o que foi digitado errado no cadastro. Voltar para prospect é recusado pela API
            quando o cliente já tem oportunidade ganha — o que o sistema observou não se desdiz. */}
        <Field label="Situação"><select className="field" value={form.status} onChange={event => { setForm({ ...form, status: event.target.value as ClientStatus }); setSaved(false); }}><option value="prospect">Prospect — ainda não fechou</option><option value="active">Cliente ativo — já fechou</option></select></Field>
        <button className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><Save className="size-4" />Salvar alterações</button>
        {saved && <p className="text-sm font-medium text-emerald-700">Dados atualizados.</p>}
      </form>

      <section className="space-y-4 rounded-2xl border bg-white p-5 sm:p-6">
        <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><UserRound className="size-4" /></span><div><h2 className="font-semibold text-ink">Contatos</h2><p className="text-sm text-slate-600">{contacts.length} {contacts.length === 1 ? "contato" : "contatos"}</p></div></div>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={event => void createContact(event)}>
          <input className="field" placeholder="Nome" value={contactDraft.name} onChange={event => setContactDraft({ ...contactDraft, name: event.target.value })} required />
          <input className="field" type="email" placeholder="E-mail" value={contactDraft.email} onChange={event => setContactDraft({ ...contactDraft, email: event.target.value })} />
          <input className="field" placeholder="Telefone" value={contactDraft.phone} onChange={event => setContactDraft({ ...contactDraft, phone: event.target.value })} />
          <input className="field" placeholder="Cargo" value={contactDraft.job_title} onChange={event => setContactDraft({ ...contactDraft, job_title: event.target.value })} />
          <button className="inline-flex items-center justify-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink sm:col-span-2" type="submit"><Plus className="size-4" />Adicionar contato</button>
        </form>
        {contacts.length ? <div className="divide-y">{contacts.map(contact => <div className="flex items-start gap-3 py-3" key={contact.id}><span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><UserRound className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{contact.name}</p>{contact.job_title && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Briefcase className="size-3" />{contact.job_title}</p>}{contact.email && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Mail className="size-3" />{contact.email}</p>}{contact.phone && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Phone className="size-3" />{contact.phone}</p>}</div><button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-signal" aria-label={`Remover ${contact.name}`} onClick={() => void removeContact(contact.id)}><Trash2 className="size-4" /></button></div>)}</div> : <p className="rounded-xl border border-dashed bg-slate-50/60 px-4 py-6 text-center text-sm text-slate-600">Nenhum contato cadastrado.</p>}
      </section>
    </div>
  </section>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="grid gap-2 text-sm font-medium text-slate-700">{label}{children}</label>; }

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-slate-50 px-4 py-3"><p className="text-xs text-slate-600">{label}</p><p className="mt-1 text-sm font-semibold text-ink">{value}</p></div>; }
