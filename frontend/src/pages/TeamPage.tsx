import { MailPlus, ShieldCheck, UserRound } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { createInvitation, listInvitations, listUsers } from "../api";
import type { Invitation, Role, SessionUser } from "../types";

const roleLabel: Record<Role, string> = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" };

function invitationStatus(invitation: Invitation): { label: string; cls: string } {
  if (invitation.accepted_at) return { label: "Aceito", cls: "bg-emerald-50 text-emerald-700" };
  if (new Date(invitation.expires_at) < new Date()) return { label: "Expirado", cls: "bg-slate-100 text-slate-500" };
  return { label: "Pendente", cls: "bg-amber-50 text-amber-700" };
}

export function TeamPage() {
  const [users, setUsers] = useState<SessionUser[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("delivery");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(() => Promise.all([listUsers(), listInvitations()]).then(([loadedUsers, loadedInvitations]) => {
    setUsers(loadedUsers); setInvitations(loadedInvitations);
  }).catch((cause: Error) => setError(cause.message)), []);
  useEffect(() => { void load(); }, [load]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setNotice("");
    try { await createInvitation(email, role); setNotice(`Convite enviado para ${email}.`); setEmail(""); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="space-y-7">
    <header><p className="text-sm font-semibold text-ocean">Administração</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Equipe</h1><p className="mt-2 text-sm text-slate-500">Convide pessoas e acompanhe os acessos ao portal.</p></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    {notice && <p className="rounded-xl bg-emerald-50 p-3 text-sm font-medium text-emerald-700">{notice}</p>}

    <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <form className="space-y-4 rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void invite(event)}>
        <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-mint text-ocean"><MailPlus className="size-5" /></span><div><h2 className="font-semibold text-ink">Convidar pessoa</h2><p className="text-sm text-slate-500">Um e-mail com o link de ativação será enviado.</p></div></div>
        <label className="grid gap-2 text-sm font-medium text-slate-700">E-mail<input className="field" type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="pessoa@empresa.com" required /></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Função<select className="field" value={role} onChange={event => setRole(event.target.value as Role)}>{(Object.keys(roleLabel) as Role[]).map(value => <option key={value} value={value}>{roleLabel[value]}</option>)}</select></label>
        <button className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><MailPlus className="size-4" />Enviar convite</button>
      </form>

      <div className="space-y-5">
        <section className="overflow-hidden rounded-2xl border bg-white">
          <div className="border-b px-5 py-4 sm:px-6"><h2 className="font-semibold text-ink">Convites</h2></div>
          {invitations.length ? <div className="divide-y">{invitations.map(invitation => { const status = invitationStatus(invitation); return <div className="flex items-center gap-3 px-5 py-3 sm:px-6" key={invitation.id}><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><MailPlus className="size-4" /></span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{invitation.email}</p><p className="text-xs text-slate-500">{roleLabel[invitation.role]}</p></div><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${status.cls}`}>{status.label}</span></div>; })}</div> : <p className="px-6 py-6 text-center text-sm text-slate-400">Nenhum convite ainda.</p>}
        </section>
        <section className="overflow-hidden rounded-2xl border bg-white">
          <div className="border-b px-5 py-4 sm:px-6"><h2 className="font-semibold text-ink">Usuários ativos</h2></div>
          {users.length ? <div className="divide-y">{users.map(user => <div className="flex items-center gap-3 px-5 py-3 sm:px-6" key={user.id}><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-mint text-ocean">{user.role === "admin" ? <ShieldCheck className="size-4" /> : <UserRound className="size-4" />}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{user.first_name || user.username}</p><p className="truncate text-xs text-slate-500">{user.email || user.username}</p></div><span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{roleLabel[user.role]}</span></div>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-400">Nenhum usuário.</p>}
        </section>
      </div>
    </div>
  </section>;
}
