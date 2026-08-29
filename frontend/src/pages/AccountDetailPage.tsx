import { ArrowLeft, Briefcase, Coins, HeartHandshake, Mail, MessageSquareText, Pencil, Phone, Plus, Save, Sparkles, Target, Trash2, UserRound, Workflow } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api, getConfig } from "../api";
import { useAuth } from "../auth";
import { LifecycleOptions } from "../components/AccountLifecycle";
import { ConfirmDialog } from "../components/Modal";
import { HealthBadge, SUSTENTACAO_LABEL, satisfacaoBadgeClass, sustentacaoBadgeClass } from "../components/StatusDot";
import { moeda } from "../dinheiro";
import { mensagemDeFalha } from "../erros";
import type { Account, AccountLifecycleStatus, AccountOverview, Activity, ActivityKind, CobrancaSinal, Contact, Engagement, EngagementCommercialModel, EngagementStatus, Invoice, Process, Satisfacao, SatisfacaoFonte, SatisfacaoNivel, Vertical } from "../types";

// `receives_billing` nasce falso, e a falha é fechada de propósito (FDD 036): sem ninguém marcado,
// o degrau da régua **não vira e-mail ao cliente** — vira escalada interna com o motivo escrito. A
// casa cala quando não sabe, em vez de chutar o destinatário de um e-mail sobre dinheiro.
const blankContact = { first_name: "", last_name: "", email: "", phone: "", job_title: "", receives_billing: false };
// `invoice` é opcional no backend e a classificação funciona sem ela — mas é a fatura que dá ao
// classificador o contexto do que o cliente está respondendo (FDD 036).
const blankActivity = { kind: "call" as ActivityKind, happened_on: new Date().toISOString().slice(0, 10), summary: "", notes: "", invoice: "" };
const activityKindLabels: Record<ActivityKind, string> = { call: "Ligação", meeting: "Reunião", email: "E-mail", note: "Nota" };
// `happened_on` nasce hoje, no molde de `blankActivity` — quem registra corrige a data quando o
// acontecido foi antes.
const blankSatisfacao = { nivel: "satisfeito" as SatisfacaoNivel, fonte: "declarada" as SatisfacaoFonte, happened_on: new Date().toISOString().slice(0, 10), note: "" };
const satisfacaoNivelLabels: Record<SatisfacaoNivel, string> = { promotor: "Promotor", satisfeito: "Satisfeito", neutro: "Neutro", insatisfeito: "Insatisfeito" };
const satisfacaoFonteLabels: Record<SatisfacaoFonte, string> = { declarada: "Declarada pelo cliente", percebida: "Percebida por quem entrega" };

/* -------------------------------------------------------------------------------------------
   O mandato de transformação da conta (ADR 0050, FDD 046), desenhado no DAP
   `docs/design/dap-engagement-r1/` — revisão 1, decisões **A1** e **B1**.

   `owner` não está no rascunho de propósito: o formulário aprovado não pergunta quem é o
   responsável, porque quem cria o mandato aqui dentro é quem está logado, e é
   `EngagementViewSet.perform_create` que o grava.
   ------------------------------------------------------------------------------------------- */
const blankEngagement = {
  name: "", commercial_model: "paid" as EngagementCommercialModel, status: "active" as EngagementStatus,
  sponsor: "", started_at: "", ended_at: "", mandate: "", success_definition: "",
};
const engagementStatusLabels: Record<EngagementStatus, string> = { active: "Ativo", paused: "Pausado", closed: "Encerrado" };
const engagementCommercialModelLabels: Record<EngagementCommercialModel, string> = { paid: "Pago", design_partner: "Design partner" };
// Mapas de **variante**, nunca de cor (ADR 0026): `"state--1"`, jamais `"bg-emerald-50 …"`. Uma
// segunda definição de "ativo" diverge da primeira em silêncio.
//
// `closed` é `state--off`, o neutro, e não `state--3`: um mandato encerrado é um mandato que
// terminou, muitas vezes bem — pintá-lo de perigo faria a conta de melhor histórico parecer a mais
// problemática. `paused` é o único dos três que pede alguém, e por isso é o único em âmbar.
const engagementStatusBadge: Record<EngagementStatus, string> = { active: "state--1", paused: "state--2", closed: "state--off" };
// Decisão **B1**: as duas pílulas sempre visíveis. `paid` no neutro e `design_partner` no azul de
// informação — o mesmo selo que "Recebe cobrança" usa nesta página, e pelo mesmo motivo: é um fato
// sobre o registro, não um aviso. Mostrar só a exceção faria "sem selo" significar duas coisas para
// quem lê: conta paga, ou campo que ninguém preencheu.
const engagementCommercialModelBadge: Record<EngagementCommercialModel, string> = { paid: "state--off", design_partner: "state--0" };

/**
 * Período com precisão de **mês** ("Desde 03/2026", "02/2026 → 05/2026") — decisão 6 do DAP: o
 * mandato se mede em meses, e o dia exato vira ruído numa linha que já carrega quatro informações.
 *
 * Fatia a string ISO em vez de passar por `Date`: `new Date("2026-03-01")` é meia-noite **UTC** e
 * volta como 28/02 em fuso negativo — o mês exibido seria o anterior. É o mesmo defeito que os
 * vizinhos contornam com `T12:00:00`, e aqui não há por que abrir a data para fechá-la de novo.
 */
function mesEAno(iso: string): string {
  const [ano, mes] = iso.split("-");
  return `${mes}/${ano}`;
}

/** Nunca um travessão de preenchimento nem uma seta solta: sem `started_at`, não há período. */
function periodoDoEngagement(engagement: Engagement): string {
  if (!engagement.started_at) return "";
  const inicio = mesEAno(engagement.started_at);
  return engagement.ended_at ? `${inicio} → ${mesEAno(engagement.ended_at)}` : `Desde ${inicio}`;
}

/**
 * A contagem é a que **quem está lendo alcança** — o backend a recorta por `project_scope_q`, e
 * dois usuários veem números diferentes para o mesmo mandato (FDD 046).
 */
function projetosDoEngagement(quantos: number): string {
  return `${quantos} ${quantos === 1 ? "projeto" : "projetos"}`;
}

/** O subtítulo do cabeçalho. Conta os **ativos**, que é o que a copy aprovada diz. */
function resumoDeEngagements(engagements: Engagement[]): string {
  if (!engagements.length) return "Nenhum engagement";
  const ativos = engagements.filter(engagement => engagement.status === "active").length;
  return `${ativos} ${ativos === 1 ? "engagement ativo" : "engagements ativos"} nesta conta`;
}

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

export function AccountDetailPage({ id }: { id: number }) {
  const [client, setClient] = useState<Account>();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [overview, setOverview] = useState<AccountOverview>();
  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [form, setForm] = useState<{ name: string; legal_name: string; tax_id: string; lifecycle_status: AccountLifecycleStatus; vertical: string }>({ name: "", legal_name: "", tax_id: "", lifecycle_status: "prospect", vertical: "" });
  const [contactDraft, setContactDraft] = useState(blankContact);
  const [editingContact, setEditingContact] = useState<Contact | null>(null);
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
  const [processos, setProcessos] = useState<Process[]>([]);
  const [satisfacaoDraft, setSatisfacaoDraft] = useState(blankSatisfacao);
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [engagementDraft, setEngagementDraft] = useState(blankEngagement);
  const [editingEngagement, setEditingEngagement] = useState<Engagement | null>(null);
  // O formulário de engagement abre por ação, ao contrário do de Contatos, que fica sempre à
  // vista: é o que o board desenha (a lista renderiza sem formulário até "Novo engagement"), e é
  // o que mantém a seção legível numa página que já empilha seis painéis.
  const [engagementFormOpen, setEngagementFormOpen] = useState(false);
  const [removingEngagement, setRemovingEngagement] = useState<Engagement | null>(null);
  const { user } = useAuth();
  const canArchive = !!user?.is_admin;
  const canWriteActivities = !!user && user.role !== "delivery";
  // Mesma regra de `canWriteActivities` — a Entrega só lê `contact` (RolePermission,
  // `permissions.py`) —, com nome próprio porque é o painel de Contatos que ela gate-ia aqui.
  const canWriteContacts = !!user && user.role !== "delivery";
  // A mesma leitura de papel outra vez, e pelo mesmo motivo dos dois acima: a Entrega só lê
  // `engagement` (`permissions.py`, e a assimetria é a decisão da FDD 046 — quem entrega precisa
  // saber a que mandato o projeto pertence sem poder redefinir o que foi contratado). O desenho
  // não inventa permissão: ele deixa de mostrar o que a API recusaria.
  const canWriteEngagements = !!user && user.role !== "delivery";

  const load = useCallback(() => Promise.all([
    api<Account>(`/clients/${id}/`),
    api<Contact[]>(`/contacts/?account=${id}`),
    api<Activity[]>(`/activities/?account=${id}`),
    api<AccountOverview>(`/clients/${id}/overview/`),
    api<Vertical[]>("/verticals/"),
    api<Satisfacao[]>(`/satisfacoes/?account=${id}`),
    api<Process[]>(`/processos/?account=${id}`),
    // Na **mesma** chamada que o resto da página, e não num `useEffect` próprio: a seção não tem
    // estado de carregamento seu (decisão do DAP), e uma segunda chamada criaria um — a tela
    // mostraria a seção vazia antes de mostrá-la cheia.
    api<Engagement[]>(`/engagements/?account=${id}`),
  ]).then(([loadedClient, loadedContacts, loadedActivities, loadedOverview, loadedVerticals, loadedSatisfacoes, loadedProcessos, loadedEngagements]) => {
    setClient(loadedClient); setContacts(loadedContacts); setActivities(loadedActivities); setOverview(loadedOverview); setVerticals(loadedVerticals); setSatisfacoes(loadedSatisfacoes); setProcessos(loadedProcessos); setEngagements(loadedEngagements);
    setForm({ name: loadedClient.name, legal_name: loadedClient.legal_name, tax_id: loadedClient.tax_id, lifecycle_status: loadedClient.lifecycle_status, vertical: loadedClient.vertical ? String(loadedClient.vertical) : "" });
  }).catch((cause: Error) => setError(cause.message)), [id]);
  useEffect(() => { void load(); }, [load]);
  // A flag `ai` tira o botão de classificar da tela, como tira o de rascunhar na Cobrança
  // (ADR 0031). A Entrega não escreve interação nem alcança fatura, então nem pergunta.
  useEffect(() => {
    if (!canWriteActivities) return;
    void getConfig().then(config => setIaLigada(config.ai_enabled)).catch(() => setIaLigada(false));
    void api<Invoice[]>(`/invoices/?account=${id}`).then(setInvoices).catch(() => setInvoices([]));
  }, [canWriteActivities, id]);

  async function saveClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaved(false);
    try { await api(`/clients/${id}/`, { method: "PATCH", body: JSON.stringify({ ...form, vertical: form.vertical ? Number(form.vertical) : null }) }); setSaved(true); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  /**
   * Cria ou edita um contato, conforme `editingContact` (issue #55). No erro, o rascunho e o modo
   * de edição ficam como estavam: o que foi digitado não se perde e a edição não é abandonada.
   */
  async function saveContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      if (editingContact) await api(`/contacts/${editingContact.id}/`, { method: "PATCH", body: JSON.stringify(contactDraft) });
      else await api("/contacts/", { method: "POST", body: JSON.stringify({ account: id, ...contactDraft }) });
      setContactDraft(blankContact); setEditingContact(null); await load();
    } catch (cause) { setError((cause as Error).message); }
  }
  function startContactEdit(contact: Contact) {
    setEditingContact(contact);
    setContactDraft({ first_name: contact.first_name, last_name: contact.last_name, email: contact.email, phone: contact.phone, job_title: contact.job_title, receives_billing: contact.receives_billing });
  }
  function cancelContactEdit() { setEditingContact(null); setContactDraft(blankContact); }
  async function removeContact() {
    if (!removingContact) return;
    setBusy(true);
    // Arquivar quem está em edição precisa sair do modo de edição junto: o formulário seguiria
    // apontando para uma linha que `ArchiveModelViewSet` já não devolve, e o "Salvar alterações"
    // viraria um 404 sem explicação.
    try { await api(`/contacts/${removingContact.id}/`, { method: "DELETE" }); if (editingContact?.id === removingContact.id) cancelContactEdit(); setRemovingContact(null); await load(); }
    catch (cause) { setRemovingContact(null); setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  /**
   * Cria ou edita o mandato, conforme `editingEngagement` — o padrão de Contatos, sem modal
   * (decisão 3 do DAP). No erro, o rascunho e o modo de edição ficam como estavam.
   *
   * As datas e o patrocinador vão como `null` quando vazios, e não como `""`: os três campos são
   * opcionais no modelo, e uma string vazia num `DateField` volta 400.
   */
  async function saveEngagement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const corpo = {
      ...engagementDraft,
      sponsor: engagementDraft.sponsor ? Number(engagementDraft.sponsor) : null,
      started_at: engagementDraft.started_at || null,
      ended_at: engagementDraft.ended_at || null,
    };
    try {
      if (editingEngagement) await api(`/engagements/${editingEngagement.id}/`, { method: "PATCH", body: JSON.stringify(corpo) });
      else await api("/engagements/", { method: "POST", body: JSON.stringify({ account: id, ...corpo }) });
      closeEngagementForm(); await load();
    } catch (cause) { setError((cause as Error).message); }
  }
  function startEngagementEdit(engagement: Engagement) {
    setEditingEngagement(engagement);
    setEngagementFormOpen(true);
    setEngagementDraft({
      name: engagement.name, commercial_model: engagement.commercial_model, status: engagement.status,
      sponsor: engagement.sponsor ? String(engagement.sponsor) : "",
      started_at: engagement.started_at ?? "", ended_at: engagement.ended_at ?? "",
      mandate: engagement.mandate, success_definition: engagement.success_definition,
    });
  }
  function closeEngagementForm() { setEditingEngagement(null); setEngagementFormOpen(false); setEngagementDraft(blankEngagement); }
  async function removeEngagement() {
    if (!removingEngagement) return;
    setBusy(true);
    // Arquivar quem está em edição sai do modo de edição junto, pela razão escrita no bloco de
    // Contatos: o formulário seguiria apontando para uma linha que `ArchiveModelViewSet` já não
    // devolve, e o "Salvar alterações" viraria um 404 sem explicação.
    //
    // O erro **não** passa por `mensagemDeFalha`: o 409 daqui é a recusa de arquivar mandato com
    // projeto vivo, e o `detail` do backend já diz quantos projetos e o que fazer antes. A
    // orientação genérica de 409 ("o estado mudou — recarregue") seria falsa: nada mudou, e
    // recarregar não resolve.
    try { await api(`/engagements/${removingEngagement.id}/`, { method: "DELETE" }); if (editingEngagement?.id === removingEngagement.id) closeEngagementForm(); setRemovingEngagement(null); await load(); }
    catch (cause) { setRemovingEngagement(null); setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function createActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { invoice, ...resto } = activityDraft;
    try { await api("/activities/", { method: "POST", body: JSON.stringify({ account: id, ...resto, invoice: invoice ? Number(invoice) : null }) }); setActivityDraft(blankActivity); await load(); }
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
    try { await api("/satisfacoes/", { method: "POST", body: JSON.stringify({ account: id, ...satisfacaoDraft }) }); setSatisfacaoDraft(blankSatisfacao); await load(); }
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
      window.location.assign("/contas");
    } catch (cause) {
      // O 409 das guardas de integridade chega aqui com o motivo ("ainda tem 2 projeto(s)…"),
      // que é exatamente o que quem tentou precisa ler para saber o que fazer antes.
      setArchiving(false); setError((cause as Error).message); setBusy(false);
    }
  }

  if (error && !client) return <div role="alert" className="alert--error">{error}</div>;
  if (!client) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  return <section className="space-y-7">
    <a href="/contas" className="back-link"><ArrowLeft className="size-4" />Voltar para contas</a>
    {removingContact && <ConfirmDialog
      title="Remover contato"
      message={<>Remover <strong className="text-ink">{removingContact.name}</strong> da lista de contatos deste cliente?</>}
      confirmLabel="Remover" busy={busy}
      onCancel={() => setRemovingContact(null)} onConfirm={() => void removeContact()}
    />}
    {removingEngagement && <ConfirmDialog
      title="Arquivar engagement"
      message={<>O engagement <strong className="text-ink">{removingEngagement.name}</strong> sai das listagens ativas. Nada é apagado — dá para restaurar depois.</>}
      confirmLabel="Arquivar" busy={busy}
      onCancel={() => setRemovingEngagement(null)} onConfirm={() => void removeEngagement()}
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

    {/* Os mandatos de transformação da conta (ADR 0050, FDD 046), governados pelo DAP
        `docs/design/dap-engagement-r1/` — revisão 1, decisões **A1** e **B1**.

        **Entre Saúde da relação e Satisfação, e a ordem é a decisão 1 do pacote**: a saúde é o
        relance de *como estamos indo*, o engajamento é *o que estamos fazendo*, e estrutura vem
        antes de histórico. Quem abre a conta precisa saber qual é o mandato antes de ler o que
        aconteceu dentro dele. Esta é a primeira superfície do produto onde a espinha
        `Account → Engagement → Project` fica visível.

        O título fica em **inglês** (decisão A1) com a copy em volta em pt-BR: é o termo canônico
        do `docs/ontology/language-map.md` §1, que não se traduz — traduz-se o texto em volta dele.

        O ícone é o `Target` e não um aperto de mão: o `HeartHandshake` já desenha a Satisfação,
        logo abaixo, e dois glifos de mãos colados um no outro é a diferença que ninguém enxerga.
        O alvo diz a outra metade do conceito — o mandato tem `success_definition`. */}
    <section className="panel sm:p-6" data-testid="engagements-panel">
      <div className="panel-heading">
        <div className="flex items-center gap-3">
          <span className="metric-icon"><Target className="size-4" /></span>
          <div>
            <h2 className="font-semibold text-ink">{editingEngagement ? `Editando ${editingEngagement.name}` : "Engagements"}</h2>
            <p className="text-sm text-slate-600">{resumoDeEngagements(engagements)}</p>
          </div>
        </div>
        {canWriteEngagements && (engagementFormOpen
          ? <button type="button" className="btn btn--secondary shrink-0" onClick={closeEngagementForm}>Cancelar</button>
          : <button type="button" className="btn shrink-0" onClick={() => setEngagementFormOpen(true)}><Plus className="size-4" />Novo engagement</button>)}
      </div>
      {canWriteEngagements && engagementFormOpen && <form className="mb-4 space-y-4" onSubmit={event => void saveEngagement(event)}>
        <label className="form-label">Nome<input className="field" value={engagementDraft.name} onChange={event => setEngagementDraft({ ...engagementDraft, name: event.target.value })} placeholder="Como a casa chama este mandato" required /></label>
        <div className="form-grid">
          <label className="form-label">Modelo comercial<select className="field" value={engagementDraft.commercial_model} onChange={event => setEngagementDraft({ ...engagementDraft, commercial_model: event.target.value as EngagementCommercialModel })}>{Object.entries(engagementCommercialModelLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="form-label">Status<select className="field" value={engagementDraft.status} onChange={event => setEngagementDraft({ ...engagementDraft, status: event.target.value as EngagementStatus })}>{Object.entries(engagementStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {/* Só os contatos **desta conta**, e não é conveniência: `Engagement.clean()` e
              `EngagementSerializer.validate()` recusam patrocinador de outra organização. Um
              select com o catálogo inteiro ofereceria justamente as opções que voltam 400. */}
          <label className="form-label">Patrocinador<select className="field" value={engagementDraft.sponsor} onChange={event => setEngagementDraft({ ...engagementDraft, sponsor: event.target.value })}><option value="">Sem patrocinador definido</option>{contacts.map(contact => <option key={contact.id} value={contact.id}>{contact.name}</option>)}</select></label>
          <label className="form-label">Início<input className="field" type="date" value={engagementDraft.started_at} onChange={event => setEngagementDraft({ ...engagementDraft, started_at: event.target.value })} /></label>
          <label className="form-label">Fim<input className="field" type="date" value={engagementDraft.ended_at} onChange={event => setEngagementDraft({ ...engagementDraft, ended_at: event.target.value })} /></label>
        </div>
        <label className="form-label">Mandato<textarea className="field min-h-20" value={engagementDraft.mandate} onChange={event => setEngagementDraft({ ...engagementDraft, mandate: event.target.value })} placeholder="O que a casa foi contratada para transformar" /></label>
        <label className="form-label">Definição de sucesso<textarea className="field min-h-20" value={engagementDraft.success_definition} onChange={event => setEngagementDraft({ ...engagementDraft, success_definition: event.target.value })} placeholder="Como saberemos que deu certo" /></label>
        <div className="flex gap-2">
          <button className="btn" type="submit">{editingEngagement ? <><Save className="size-4" />Salvar alterações</> : <><Plus className="size-4" />Adicionar engagement</>}</button>
          {editingEngagement && <button type="button" className="btn btn--secondary" onClick={closeEngagementForm}>Cancelar</button>}
        </div>
      </form>}
      {engagements.length ? <div className="panel-rows">{engagements.map(engagement => <div className={`row ${editingEngagement?.id === engagement.id ? "opacity-50" : ""}`} key={engagement.id}>
        <span className="metric-icon"><Target className="size-4" /></span>
        <div className="row-main">
          <strong>{engagement.name}</strong>
          {engagement.sponsor_name && <span>Patrocínio de {engagement.sponsor_name}</span>}
          <span>{[periodoDoEngagement(engagement), projetosDoEngagement(engagement.projects_count)].filter(Boolean).join(" · ")}</span>
        </div>
        {/* As duas pílulas são **irmãs** de `.row-main`, nunca filhas, pela razão escrita nos
            blocos de Satisfação e Interações: `.row-main span` declara `block text-xs text-muted`
            e um `.state` aninhado ali perderia a própria pele sem nada ficar vermelho.

            E são **duas, sempre** (decisão B1): mostrar só o `design_partner` faria "sem selo"
            significar duas coisas para quem lê — conta paga, ou campo que ninguém preencheu. */}
        <span className={`state ${engagementStatusBadge[engagement.status]} shrink-0`}>{engagement.status_display}</span>
        <span className={`state ${engagementCommercialModelBadge[engagement.commercial_model]} shrink-0`}>{engagement.commercial_model_display}</span>
        {canWriteEngagements && <div className="flex shrink-0 gap-1.5">
          <button type="button" className="btn btn--icon btn--secondary" aria-label={`Editar ${engagement.name}`} onClick={() => startEngagementEdit(engagement)}><Pencil className="size-4" /></button>
          <button type="button" className="btn btn--icon btn--secondary btn--secondary-danger" aria-label={`Arquivar ${engagement.name}`} onClick={() => setRemovingEngagement(engagement)}><Trash2 className="size-4" /></button>
        </div>}
      </div>)}</div> : <p className="empty-state">Nenhum engagement nesta conta. Crie o mandato antes de converter uma oportunidade — é ele que agrupa as vendas e os projetos que são o mesmo trabalho.</p>}
    </section>

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

    {/* Os processos mapeados no Discovery estruturado (FDD 039, ADR 0034) — logo depois da
        Satisfação porque as duas dizem o que a casa sabe sobre este cliente: uma sobre a relação,
        a outra sobre a operação. Aqui é índice e porta de entrada; o mapa inteiro mora na tela do
        processo. O que a linha precisa responder é **quanto custa** e **se aquilo se sustenta** —
        e é por isso que o total nunca aparece sem a marca de parcial: um custo apresentado inteiro
        quando metade dos insumos não foi apurada é a casa afirmando ao cliente o oposto do que ela
        sabe.

        A contagem de etapas ficou de fora, e o motivo é o payload: `ProcessSerializer` não expõe
        `steps` nem um contador, e `/processo-etapas/` só filtra por `?process=` — mostrá-la aqui
        custaria uma requisição por processo a cada `load()`, que esta tela dispara a cada contato,
        interação ou satisfação criados. */}
    <section className="panel space-y-4 sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><Workflow className="size-4" /></span><div><h2 className="font-semibold text-ink">Processos mapeados</h2><p className="text-sm text-slate-600">{processos.length} {processos.length === 1 ? "processo" : "processos"}</p></div></div>
      {processos.length ? <div className="panel-rows">{processos.map(processo => <div className="row" key={processo.id}>
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Workflow className="size-4" /></span>
        <div className="row-main">
          <strong>{processo.name}</strong>
          <span>{moeda(processo.custo.total)} por mês{processo.custo.nao_apurado.length > 0 && ` · total parcial, ${processo.custo.nao_apurado.length} sem apuração`}</span>
        </div>
        {/* Selo e link como irmãos do `.row-main`, pela razão escrita no bloco de Satisfação acima:
            `.row-main span`/`strong` sobrescrevem display e cor de qualquer primitiva aninhada. */}
        <span className={`state ${sustentacaoBadgeClass(processo.custo.sustentacao)} shrink-0`}>{SUSTENTACAO_LABEL[processo.custo.sustentacao]}</span>
        <a className="btn btn--secondary shrink-0" href={`/contas/${id}/processos/${processo.id}`}>Abrir o mapa</a>
      </div>)}</div> : <p className="empty-state">Nenhum processo mapeado para este cliente.</p>}
    </section>

    {/* A porta da priorização (DAP priorização r1, decisão **A1**) — logo depois dos processos,
        que é de onde as dores vêm. Fica **fora** de qualquer painel de propósito: as oito seções
        desta página não são tocadas por esta entrega, e o pacote é explícito quanto a isso. E não
        entra no menu lateral: a priorização é sempre de uma conta, e um item de menu que abre
        pedindo "qual conta?" é um beco. */}
    <div className="flex flex-wrap gap-2">
      <a className="btn btn--secondary" href={`/contas/${id}/priorizacao`}><Target className="size-4" />Abrir a priorização</a>
      {/* A porta do Value Ledger (DAP `dap-prove-e-valor-r1`, decisão **D1**) — ao lado da
          priorização, pelo mesmo motivo: valor é sempre de uma conta, e nenhum dos dois entra no
          menu lateral. */}
      <a className="btn btn--secondary" href={`/contas/${id}/valor`}><Coins className="size-4" />Abrir o valor gerado</a>
    </div>

    <div className="grid gap-5 lg:grid-cols-[.9fr_1.1fr]">
      <form className="panel space-y-4 sm:p-6" onSubmit={event => void saveClient(event)} data-testid="client-form">
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
        <Field label="Situação"><select className="field" value={form.lifecycle_status} onChange={event => { setForm({ ...form, lifecycle_status: event.target.value as AccountLifecycleStatus }); setSaved(false); }}><LifecycleOptions /></select></Field>
        <button className="btn" type="submit"><Save className="size-4" />Salvar alterações</button>
        {saved && <p className="text-sm font-medium text-emerald-700">Dados atualizados.</p>}
      </form>

      <section className="panel space-y-4 sm:p-6" data-testid="contacts-panel">
        <div className="flex items-center gap-3"><span className="metric-icon"><UserRound className="size-4" /></span><div><h2 className="font-semibold text-ink">{editingContact ? `Editando ${editingContact.name}` : "Contatos"}</h2><p className="text-sm text-slate-600">{contacts.length} {contacts.length === 1 ? "contato" : "contatos"}</p></div></div>
        {canWriteContacts && <form className="space-y-3" onSubmit={event => void saveContact(event)}>
          <div className="form-grid">
            <label className="form-label">Nome<input className="field" value={contactDraft.first_name} onChange={event => setContactDraft({ ...contactDraft, first_name: event.target.value })} required /></label>
            <label className="form-label">Sobrenome<input className="field" value={contactDraft.last_name} onChange={event => setContactDraft({ ...contactDraft, last_name: event.target.value })} /></label>
            <label className="form-label">E-mail<input className="field" type="email" value={contactDraft.email} onChange={event => setContactDraft({ ...contactDraft, email: event.target.value })} /></label>
            <label className="form-label">Telefone<input className="field" value={contactDraft.phone} onChange={event => setContactDraft({ ...contactDraft, phone: event.target.value })} /></label>
          </div>
          <label className="form-label">Cargo<input className="field" value={contactDraft.job_title} onChange={event => setContactDraft({ ...contactDraft, job_title: event.target.value })} /></label>
          <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="checkbox" className="size-4" checked={contactDraft.receives_billing} onChange={event => setContactDraft({ ...contactDraft, receives_billing: event.target.checked })} />
            Recebe cobrança — sem ninguém marcado, a régua escala internamente em vez de escrever ao cliente
          </label>
          <div className="flex gap-2">
            <button className="btn" type="submit">{editingContact ? <><Save className="size-4" />Salvar alterações</> : <><Plus className="size-4" />Adicionar contato</>}</button>
            {editingContact && <button type="button" className="btn btn--secondary" onClick={cancelContactEdit}>Cancelar</button>}
          </div>
        </form>}
        {contacts.length ? <div className="divide-y">{contacts.map(contact => <div className={`flex items-start gap-3 py-3 ${editingContact?.id === contact.id ? "opacity-50" : ""}`} key={contact.id}>
          <span className="avatar mt-0.5">{contactInitials(contact)}</span>
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">{contact.name}{contact.receives_billing && <span className="state state--0">Recebe cobrança</span>}</p>
            {contact.job_title && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Briefcase className="size-3" />{contact.job_title}</p>}
            {contact.email && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Mail className="size-3" />{contact.email}</p>}
            {contact.phone && <p className="flex items-center gap-1.5 text-xs text-slate-600"><Phone className="size-3" />{contact.phone}</p>}
          </div>
          {canWriteContacts && <div className="flex shrink-0 gap-1.5">
            <button type="button" className="btn btn--icon btn--secondary" aria-label={`Editar ${contact.name}`} onClick={() => startContactEdit(contact)}><Pencil className="size-4" /></button>
            <button type="button" className="btn btn--icon btn--secondary btn--secondary-danger" aria-label={`Remover ${contact.name}`} onClick={() => setRemovingContact(contact)}><Trash2 className="size-4" /></button>
          </div>}
        </div>)}</div> : <p className="empty-state">Nenhum contato cadastrado.</p>}
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

// Duas letras quando há sobrenome, uma quando não há — a mesma regra do nome composto: nunca
// inventa o que não foi cadastrado.
function contactInitials(contact: Contact): string {
  const first = contact.first_name.slice(0, 1).toUpperCase();
  const last = contact.last_name.trim() ? contact.last_name.slice(0, 1).toUpperCase() : "";
  return `${first}${last}`;
}
