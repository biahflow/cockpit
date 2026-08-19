import { ArrowLeft, Briefcase, HeartHandshake, Mail, MessageSquareText, Phone, Plus, Save, Sparkles, Trash2, UserRound } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api, getConfig } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import { HealthBadge, satisfacaoBadgeClass } from "../components/StatusDot";
import { mensagemDeFalha } from "../erros";
import type { Activity, ActivityKind, Client, ClientOverview, ClientStatus, CobrancaSinal, Contact, Invoice, Satisfacao, SatisfacaoFonte, SatisfacaoNivel, Vertical } from "../types";

// `receives_billing` nasce falso, e a falha é fechada de propósito (FDD 036): sem ninguém marcado,
// o degrau da régua **não vira e-mail ao cliente** — vira escalada interna com o motivo escrito. A
// casa cala quando não sabe, em vez de chutar o destinatário de um e-mail sobre dinheiro.
const blankContact = { name: "", email: "", phone: "", job_title: "", receives_billing: false };
// `invoice` é opcional no backend e a classificação funciona sem ela — mas é a fatura que dá ao
// classificador o contexto do que o cliente está respondendo (FDD 036).
const blankActivity = { kind: "call" as ActivityKind, happened_on: new Date().toISOString().slice(0, 10), summary: "", notes: "", invoice: "" };
const activityKindLabels: Record<ActivityKind, string> = { call: "Ligação", meeting: "Reunião", email: "E-mail", note: "Nota" };
// `happened_on` nasce hoje, no molde de `blankActivity` — quem registra corrige a data quando o
// acontecido foi antes.
const blankSatisfacao = { nivel: "satisfeito" as SatisfacaoNivel, fonte: "declarada" as SatisfacaoFonte, happened_on: new Date().toISOString().slice(0, 10), note: "" };
const satisfacaoNivelLabels: Record<SatisfacaoNivel, string> = { promotor: "Promotor", satisfeito: "Satisfeito", neutro: "Neutro", insatisfeito: "Insatisfeito" };
const satisfacaoFonteLabels: Record<SatisfacaoFonte, string> = { declarada: "Declarada pelo cliente", percebida: "Percebida por quem entrega" };

/**
 * O que fazer com cada sinal — e é isto, não o selo, que a tela precisa comunicar.
 *
 * Os três valores da FDD 036 **não são etiquetas de humor**: cada um manda para uma conduta
 * diferente, e a mesma régua estraga os três se tratá-los igual. Mostrar "Insatisfeito" sem dizer
 * que ali insistir piora tudo é entregar a metade que não muda o comportamento de ninguém.
 *
 * A IA **grava o sinal e não age** (ADR 0031): a linha abaixo é leitura, não comando. Renegociar,
 * escalar, suspender e dar desconto seguem sendo atos humanos, com autor e carimbo.
 */
const condutaDoSinal: Record<Exclude<CobrancaSinal, "">, string> = {
  esqueceu: "o lembrete já resolveu — não há o que fazer além de aguardar o pagamento.",
  nao_pode: "pede renegociação, e cedo: tratar agora custa menos do que deixar correr.",
  insatisfeito: "não é problema de cobrança — é problema de relação disfarçado, e é onde insistir piora tudo.",
};

export function ClientDetailPage({ id }: { id: number }) {
  const [client, setClient] = useState<Client>();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [overview, setOverview] = useState<ClientOverview>();
  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [form, setForm] = useState<{ name: string; legal_name: string; tax_id: string; status: ClientStatus; vertical: string }>({ name: "", legal_name: "", tax_id: "", status: "prospect", vertical: "" });
  const [contactDraft, setContactDraft] = useState(blankContact);
  const [activityDraft, setActivityDraft] = useState(blankActivity);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [removingContact, setRemovingContact] = useState<Contact | null>(null);
  const [isArchiving, setArchiving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [iaLigada, setIaLigada] = useState(false);
  const [classificando, setClassificando] = useState<number | null>(null);
  const [satisfacoes, setSatisfacoes] = useState<Satisfacao[]>([]);
  const [satisfacaoDraft, setSatisfacaoDraft] = useState(blankSatisfacao);
  const { user } = useAuth();
  const canArchive = !!user?.is_admin;
  const canWriteActivities = !!user && user.role !== "delivery";

  const load = useCallback(() => Promise.all([
    api<Client>(`/clients/${id}/`),
    api<Contact[]>(`/contacts/?client=${id}`),
    api<Activity[]>(`/activities/?client=${id}`),
    api<ClientOverview>(`/clients/${id}/overview/`),
    api<Vertical[]>("/verticals/"),
    api<Satisfacao[]>(`/satisfacoes/?client=${id}`),
  ]).then(([loadedClient, loadedContacts, loadedActivities, loadedOverview, loadedVerticals, loadedSatisfacoes]) => {
    setClient(loadedClient); setContacts(loadedContacts); setActivities(loadedActivities); setOverview(loadedOverview); setVerticals(loadedVerticals); setSatisfacoes(loadedSatisfacoes);
    setForm({ name: loadedClient.name, legal_name: loadedClient.legal_name, tax_id: loadedClient.tax_id, status: loadedClient.status, vertical: loadedClient.vertical ? String(loadedClient.vertical) : "" });
  }).catch((cause: Error) => setError(cause.message)), [id]);
  useEffect(() => { void load(); }, [load]);
  // A flag `ai` tira o botão de classificar da tela, como tira o de rascunhar na Cobrança
  // (ADR 0031). A Entrega não escreve interação nem alcança fatura, então nem pergunta.
  useEffect(() => {
    if (!canWriteActivities) return;
    void getConfig().then(config => setIaLigada(config.ai_enabled)).catch(() => setIaLigada(false));
    void api<Invoice[]>(`/invoices/?client=${id}`).then(setInvoices).catch(() => setInvoices([]));
  }, [canWriteActivities, id]);

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
  async function createActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { invoice, ...resto } = activityDraft;
    try { await api("/activities/", { method: "POST", body: JSON.stringify({ client: id, ...resto, invoice: invoice ? Number(invoice) : null }) }); setActivityDraft(blankActivity); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  /**
   * Registra a satisfação (FDD 037). `insatisfeito` sem `note` volta 400 com a mensagem no campo
   * (`clean()`/`validate()` do backend) — `mensagemDeFalha` (ADR 0032, FDD 036) é quem traduz o
   * corpo do erro sem uma segunda tabela de orientação nesta tela.
   */
  async function createSatisfacao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try { await api("/satisfacoes/", { method: "POST", body: JSON.stringify({ client: id, ...satisfacaoDraft }) }); setSatisfacaoDraft(blankSatisfacao); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  /**
   * Lê a resposta do cliente a uma cobrança e **grava o sinal** (FDD 036, camada 4).
   *
   * A IA não age aqui e não passa a agir depois: o que ela produz é uma leitura que roteia a
   * conduta de uma pessoa. Renegociar, escalar, suspender e dar desconto seguem humanos (ADR 0006,
   * ADR 0031) — e o `502` é a prova de que o backend prefere não gravar nada a gravar um palpite,
   * porque a coluna roteia conduta e um valor chutado manda alguém insistir com quem está
   * insatisfeito.
   */
  async function classificar(activity: Activity) {
    setError(""); setClassificando(activity.id);
    try { await api(`/activities/${activity.id}/classificar/`, { method: "POST" }); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setClassificando(null); }
  }
  async function archiveActivity(activity: Activity) {
    try { await api(`/activities/${activity.id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
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

    {/* A satisfação do cliente (FDD 037, ADR 0032) — logo depois da saúde da relação porque as
        duas respondem à mesma pergunta por ângulos diferentes: uma é o nosso trabalho, a outra é o
        que o cliente disse (ou o que a Entrega percebeu). **A fonte é a decisão inteira**: só a
        declarada move Health Score e escada de cobrança, e uma tela que mostrasse as duas iguais
        desfaria isso — por isso ela aparece na lista, não só no formulário, num selo próprio ao
        lado do nível. */}
    <section className="panel space-y-4 sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><HeartHandshake className="size-4" /></span><div><h2 className="font-semibold text-ink">Satisfação</h2><p className="text-sm text-slate-600">{satisfacoes.length} {satisfacoes.length === 1 ? "registro" : "registros"}</p></div></div>
      <form className="form-grid" onSubmit={event => void createSatisfacao(event)}>
        <label className="form-label">Nível<select className="field" value={satisfacaoDraft.nivel} onChange={event => setSatisfacaoDraft({ ...satisfacaoDraft, nivel: event.target.value as SatisfacaoNivel })}>{Object.entries(satisfacaoNivelLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="form-label">Fonte<select className="field" value={satisfacaoDraft.fonte} onChange={event => setSatisfacaoDraft({ ...satisfacaoDraft, fonte: event.target.value as SatisfacaoFonte })}>{Object.entries(satisfacaoFonteLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="form-label">Data<input className="field" type="date" value={satisfacaoDraft.happened_on} onChange={event => setSatisfacaoDraft({ ...satisfacaoDraft, happened_on: event.target.value })} required /></label>
        <label className="form-label sm:col-span-2">Nota{satisfacaoDraft.nivel === "insatisfeito" && <span className="text-danger"> — obrigatória para insatisfeito</span>}<textarea className="field min-h-20" value={satisfacaoDraft.note} onChange={event => setSatisfacaoDraft({ ...satisfacaoDraft, note: event.target.value })} placeholder="O que o cliente disse, ou o que foi percebido" /></label>
        <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Registrar satisfação</button>
      </form>
      {satisfacoes.length ? <div className="panel-rows">{satisfacoes.map(registro => <div className="row" key={registro.id}>
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><HeartHandshake className="size-4" /></span>
        <div className="row-main">
          <strong>{new Date(`${registro.happened_on}T12:00:00`).toLocaleDateString("pt-BR")}</strong>
          {registro.note && <span>{registro.note}</span>}
        </div>
        {/* Fora de `.row-main` de propósito: `.row-main span`/`.row-main strong` sobrescrevem
            display/cor de qualquer primitiva aninhada ali dentro (ver o comentário do bloco de
            Interações abaixo) — um `.state` ou `.eyebrow` filho perderia a própria pele em
            silêncio. Como irmãos do `.row-main`, os dois selos ficam com a pele que têm. */}
        <span className={`state ${satisfacaoBadgeClass(registro.nivel)} shrink-0`}>{registro.nivel_display}</span>
        <span className="eyebrow shrink-0">{registro.fonte_display}</span>
      </div>)}</div> : <p className="empty-state">Nenhum registro de satisfação para este cliente.</p>}
    </section>

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
          <label className="flex items-center gap-2 text-sm font-medium text-slate-700 sm:col-span-2">
            <input type="checkbox" className="size-4" checked={contactDraft.receives_billing} onChange={event => setContactDraft({ ...contactDraft, receives_billing: event.target.checked })} />
            Recebe cobrança — sem ninguém marcado, a régua escala internamente em vez de escrever ao cliente
          </label>
          <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Adicionar contato</button>
        </form>
        {contacts.length ? <div className="divide-y">{contacts.map(contact => <div className="flex items-start gap-3 py-3" key={contact.id}><span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><UserRound className="size-4" /></span><div className="min-w-0 flex-1"><p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">{contact.name}{contact.receives_billing && <span className="state state--0">Recebe cobrança</span>}</p>{contact.job_title && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Briefcase className="size-3" />{contact.job_title}</p>}{contact.email && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Mail className="size-3" />{contact.email}</p>}{contact.phone && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Phone className="size-3" />{contact.phone}</p>}</div><button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-danger" aria-label={`Remover ${contact.name}`} onClick={() => setRemovingContact(contact)}><Trash2 className="size-4" /></button></div>)}</div> : <p className="empty-state">Nenhum contato cadastrado.</p>}
      </section>
    </div>

    <section className="panel space-y-4 sm:p-6">
      <p className="eyebrow">Histórico</p>
      <h2 className="font-semibold text-ink">Interações</h2>
      {canWriteActivities && <form className="form-grid" onSubmit={event => void createActivity(event)}>
        <label className="form-label">Tipo<select className="field" value={activityDraft.kind} onChange={event => setActivityDraft({ ...activityDraft, kind: event.target.value as ActivityKind })}>{Object.entries(activityKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="form-label">Data<input className="field" type="date" value={activityDraft.happened_on} onChange={event => setActivityDraft({ ...activityDraft, happened_on: event.target.value })} required /></label>
        <label className="form-label sm:col-span-2">Resumo<input className="field" value={activityDraft.summary} onChange={event => setActivityDraft({ ...activityDraft, summary: event.target.value })} placeholder="Do que se tratou o contato" required /></label>
        <label className="form-label sm:col-span-2">Notas<textarea className="field min-h-20" value={activityDraft.notes} onChange={event => setActivityDraft({ ...activityDraft, notes: event.target.value })} placeholder="Opcional" /></label>
        {/* Opcional, e não some quando não há fatura: é o vínculo que dá ao classificador o
            contexto do que o cliente está respondendo (FDD 036). Sem ele a classificação ainda
            funciona — só chega com menos material. */}
        {invoices.length > 0 && <label className="form-label sm:col-span-2">Responde a uma cobrança?
          <select className="field" value={activityDraft.invoice} onChange={event => setActivityDraft({ ...activityDraft, invoice: event.target.value })}>
            <option value="">Não — interação comum</option>
            {invoices.map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.number || "Sem número"} · {invoice.status_display} · vence {new Date(`${invoice.due_date}T12:00:00`).toLocaleDateString("pt-BR")}</option>)}
          </select>
        </label>}
        <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Registrar interação</button>
      </form>}
      {canWriteActivities && iaLigada && <p className="text-xs text-muted">Classificar lê a resposta do cliente e <strong className="font-semibold text-slate-700">grava o sinal — não age</strong>. Renegociar, escalar, suspender e dar desconto seguem sendo atos de gente, com autor e carimbo.</p>}
      {activities.length ? <div className="panel-rows">{activities.map(activity => <div className="row" key={activity.id}>
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><MessageSquareText className="size-4" /></span>
        <div className="row-main">
          <strong>{activity.summary}</strong>
          <span>{activity.kind_display} · {new Date(`${activity.happened_on}T12:00:00`).toLocaleDateString("pt-BR")}</span>
          {/* O sinal que a IA leu na resposta do cliente a uma cobrança (FDD 036, camada 4). Ela
              **grava e não age** (ADR 0031): renegociar, escalar e suspender seguem humanos. Os três
              valores roteiam condutas diferentes, e é por isso que o rótulo aparece na linha. */}
          {/* Texto e não `.state`: `.row-main span` já define `block`/`text-xs`, e um selo aninhado
              aqui perderia a própria pele para a regra da linha sem nada ficar vermelho. */}
          {activity.cobranca_sinal && <span>Resposta à cobrança: <strong className="font-semibold text-ink">{activity.cobranca_sinal_display}</strong> — {condutaDoSinal[activity.cobranca_sinal]}</span>}
          {activity.notes && <span>{activity.notes}</span>}
        </div>
        {/* Só com a flag `ai` ligada e só enquanto não houver sinal: reclassificar sobrescreveria a
            leitura que alguém já usou para decidir. A régua funciona com a IA desligada — o que
            some daqui é o botão, não um degrau (ADR 0031). */}
        {canWriteActivities && iaLigada && !activity.cobranca_sinal && <button type="button" className="btn btn--secondary shrink-0" disabled={classificando === activity.id} aria-label={`Classificar resposta: ${activity.summary}`} onClick={() => void classificar(activity)}><Sparkles className="size-4" />{classificando === activity.id ? "Lendo…" : "Classificar resposta"}</button>}
        {canWriteActivities && <button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-danger" aria-label={`Arquivar interação: ${activity.summary}`} onClick={() => void archiveActivity(activity)}><Trash2 className="size-4" /></button>}
      </div>)}</div> : <p className="empty-state">Nenhuma interação registrada.</p>}
    </section>
  </section>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="form-label">{label}{children}</label>; }

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-slate-50 px-4 py-3"><p className="text-xs text-slate-600">{label}</p><p className="mt-1 text-sm font-semibold text-ink">{value}</p></div>; }
