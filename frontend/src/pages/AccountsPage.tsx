import { Building2, Plus, RotateCcw, Search } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { LIFECYCLE_BADGE_LABEL, LifecycleOptions, lifecycleBadgeClass } from "../components/AccountLifecycle";
import { StatusDot } from "../components/StatusDot";
import type { Account, AccountLifecycleStatus, AccountOverview } from "../types";

type Filter = "all" | AccountLifecycleStatus | "archived";

// "Todos" traz os **três estados vivos**: inativa é conta que existe, e só o arquivamento a tira
// da lista. As cinco pastilhas são a decisão C1 do DAP `dap-lifecycle-status-r1`.
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "prospect", label: "Prospects" },
  { key: "active", label: "Clientes" },
  { key: "inactive", label: "Inativos" },
  { key: "archived", label: "Arquivados" },
];

// Vazio por filtro, e não um texto só: "cadastre a primeira conta" ao lado de uma base que tem
// contas faz a tela mentir — e manda fazer algo que não encheria o filtro. Cada aba explica a
// regra que a deixa vazia.
const EMPTY: Record<Filter, { title: string; hint: string }> = {
  all: { title: "Sua base começa aqui", hint: "Cadastre a primeira conta ao lado." },
  active: { title: "Nenhum cliente", hint: "Cliente é quem já fechou: um prospect vira cliente quando a oportunidade dele é ganha, ou você marca no cadastro que ele já é cliente." },
  prospect: { title: "Nenhum prospect", hint: "Prospect é quem ainda não fechou — entra pelo cadastro ao lado ou pela conversão de um lead." },
  inactive: { title: "Nenhuma conta inativa", hint: "Inativa é a conta que já foi cliente e hoje não tem trabalho em andamento. Ela continua no histórico e volta a ser cliente quando uma oportunidade for ganha." },
  archived: { title: "Nada arquivado", hint: "Contas arquivadas aparecem aqui e podem voltar para a base a qualquer momento." },
};

export function AccountsPage() {
  const [accounts, setAccounts] = useState<AccountOverview[]>([]);
  const [name, setName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [lifecycleStatus, setLifecycleStatus] = useState<AccountLifecycleStatus>("prospect");
  const [error, setError] = useState("");
  const [isCreating, setCreating] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [archived, setArchived] = useState<Account[]>([]);
  const [restoring, setRestoring] = useState<number | null>(null);
  // A aba Arquivados fala com `/accounts/?archived=1`, não com `/accounts/overview/`: o overview é
  // agregador montado à mão e não passa pelo `get_queryset` do `ArchiveModelViewSet`, então nunca
  // enxergaria o arquivado. Saúde e jornada também não fazem sentido para quem saiu da base.
  const load = useCallback(() => {
    if (filter === "archived") {
      return api<Account[]>("/accounts/?archived=1").then(setArchived).catch((cause: Error) => setError(cause.message));
    }
    return api<{ accounts: AccountOverview[] }>(`/accounts/overview/${filter === "all" ? "" : `?lifecycle_status=${filter}`}`).then(result => setAccounts(result.accounts)).catch((cause: Error) => setError(cause.message));
  }, [filter]);
  useEffect(() => { void load(); }, [load]);
  async function restore(id: number) {
    setError(""); setRestoring(id);
    try { await api(`/accounts/${id}/unarchive/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setRestoring(null); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setCreating(true); try { await api<Account>("/accounts/", { method: "POST", body: JSON.stringify({ name, legal_name: legalName, tax_id: taxId, lifecycle_status: lifecycleStatus }) }); setName(""); setLegalName(""); setTaxId(""); setLifecycleStatus("prospect"); await load(); } catch (cause) { setError((cause as Error).message); } finally { setCreating(false); } }

  return <section className="space-y-7"><header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Relacionamento</p><h1>Contas</h1><p>Mantenha a base que sustenta seus projetos.</p></div><span className="rounded-xl bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-700">{filter === "archived" ? `${archived.length} arquivados` : `${accounts.length} cadastrados`}</span></header>{error && <p role="alert" className="alert--error">{error}</p>}
    <div className="grid gap-5 lg:grid-cols-[.72fr_1.28fr]"><form className="panel sm:p-6" onSubmit={event => void submit(event)}><div className="flex items-center gap-3"><span className="metric-icon size-10"><Plus className="size-5" /></span><div><h2 className="font-semibold text-ink">Nova conta</h2><p className="text-sm text-slate-600">Comece pelo nome principal.</p></div></div><label className="mt-6 form-label">Nome da conta<input className="field" value={name} onChange={event => setName(event.target.value)} placeholder="Ex.: Empresa Exemplo" required /></label><label className="mt-4 form-label">Razão social<input className="field" value={legalName} onChange={event => setLegalName(event.target.value)} placeholder="Opcional" /></label><label className="mt-4 form-label">CNPJ / CPF<input className="field" value={taxId} onChange={event => setTaxId(event.target.value)} placeholder="Opcional" /></label><label className="mt-4 form-label">Situação<select className="field" value={lifecycleStatus} onChange={event => setLifecycleStatus(event.target.value as AccountLifecycleStatus)}><LifecycleOptions /></select></label><button className="btn mt-4 w-full" disabled={isCreating} type="submit"><Plus className="size-4" />{isCreating ? "Cadastrando…" : "Cadastrar conta"}</button></form>
      <section className="panel panel--flush"><div className="flex items-center justify-between border-b px-5 py-5 sm:px-6"><div className="flex items-center gap-2"><span className="grid size-9 place-items-center rounded-xl bg-slate-50 text-slate-600"><Search className="size-4" /></span><h2 className="font-semibold text-ink">Base de contas</h2></div><div className="flex gap-1 rounded-xl bg-slate-50 p-1">{FILTERS.map(option => <button key={option.key} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${filter === option.key ? "bg-white text-accent shadow-sm" : "text-slate-600 hover:text-ink"}`} onClick={() => setFilter(option.key)}>{option.label}</button>)}</div></div>{filter === "archived"
        ? (archived.length ? <div className="divide-y">{archived.map(account => <div className="flex items-center gap-4 px-5 py-4 sm:px-6" key={account.id}><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-500"><Building2 className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-slate-600">{account.name}</p><p className="mt-0.5 text-xs text-slate-500">Arquivado</p></div><button className="btn btn--secondary shrink-0" disabled={restoring === account.id} onClick={() => void restore(account.id)}><RotateCcw className="size-4" />{restoring === account.id ? "Restaurando…" : "Restaurar"}</button></div>)}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-50 text-accent"><Building2 className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">{EMPTY.archived.title}</p><p className="mt-1 max-w-sm text-sm text-slate-600">{EMPTY.archived.hint}</p></div></div>)
        : accounts.length ? <div className="divide-y">{accounts.map(account => <a href={`/contas/${account.account_id}`} className="flex items-center gap-4 px-5 py-4 transition hover:bg-slate-50/70 sm:px-6" key={account.account_id}><StatusDot level={account.health?.level ?? null} /><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-600"><Building2 className="size-4" /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{account.name}</p><p className="mt-0.5 text-xs text-slate-600">{account.phase ? `Jornada · ${account.phase.name}` : "Sem jornada ativa"}</p></div><span className={`state ${lifecycleBadgeClass(account.lifecycle_status)}`}>{LIFECYCLE_BADGE_LABEL[account.lifecycle_status]}</span></a>)}</div> : <div className="grid min-h-56 place-items-center p-6 text-center"><div><span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-50 text-accent"><Building2 className="size-5" /></span><p className="mt-3 text-sm font-semibold text-ink">{EMPTY[filter].title}</p><p className="mt-1 max-w-sm text-sm text-slate-600">{EMPTY[filter].hint}</p></div></div>}</section></div>
  </section>;
}
