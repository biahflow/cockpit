import { MailPlus, ShieldCheck, UserRound } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { createInvitation, listInvitations, listUsers } from "../api";
import type { Invitation, Role, SessionUser } from "../types";

const roleLabel: Record<Role, string> = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" };

// Devolve a **variante** do selo e não as cores dela: um `bg-emerald-50` escrito aqui é uma
// segunda definição de "concluído", e ela diverge da primeira sem nada ficar vermelho.
function invitationStatus(invitation: Invitation): { label: string; cls: string } {
  if (invitation.accepted_at) return { label: "Aceito", cls: "state--1" };
  // Expirado é ausência de estado, não aviso: quem expirou já não pede ação sobre si.
  if (new Date(invitation.expires_at) < new Date()) return { label: "Expirado", cls: "state--off" };
  return { label: "Pendente", cls: "state--2" };
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
    <header className="page-head"><p className="eyebrow">Administração</p><h1>Equipe</h1><p>Convide pessoas e acompanhe os acessos ao portal.</p></header>
    {error && <p role="alert" className="alert--error">{error}</p>}
    {notice && <p className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm font-medium text-emerald-700">{notice}</p>}

    <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <form className="panel space-y-4 sm:p-6" onSubmit={event => void invite(event)}>
        <div className="flex items-center gap-3"><span className="metric-icon size-10"><MailPlus className="size-5" /></span><div><h2 className="font-semibold text-ink">Convidar pessoa</h2><p className="text-sm text-muted">Um e-mail com o link de ativação será enviado.</p></div></div>
        <label className="form-label">E-mail<input className="field" type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="pessoa@empresa.com" required /></label>
        <label className="form-label">Função<select className="field" value={role} onChange={event => setRole(event.target.value as Role)}>{(Object.keys(roleLabel) as Role[]).map(value => <option key={value} value={value}>{roleLabel[value]}</option>)}</select></label>
        <button className="btn w-full" type="submit"><MailPlus className="size-4" />Enviar convite</button>
      </form>

      <div className="space-y-5">
        <section className="panel panel--flush">
          <div className="panel-heading"><h2>Convites</h2></div>
          {invitations.length ? <div className="panel-rows">{invitations.map(invitation => { const status = invitationStatus(invitation); return <div className="row gap-3 py-3" key={invitation.id}><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-muted"><MailPlus className="size-4" /></span><div className="row-main"><strong className="truncate">{invitation.email}</strong><span>{roleLabel[invitation.role]}</span></div><span className={`state shrink-0 ${status.cls}`}>{status.label}</span></div>; })}</div> : <p className="px-6 py-6 text-center text-sm text-muted">Nenhum convite ainda.</p>}
        </section>
        <section className="panel panel--flush">
          <div className="panel-heading"><h2>Usuários ativos</h2></div>
          {users.length ? <div className="panel-rows">{users.map(user => <div className="row gap-3 py-3" key={user.id}><span className="metric-icon">{user.is_admin ? <ShieldCheck className="size-4" /> : <UserRound className="size-4" />}</span><div className="row-main"><strong className="truncate">{user.first_name || user.username}</strong><span className="truncate">{user.email || user.username}</span></div><span className="state state--off shrink-0">{user.is_admin ? roleLabel.admin : roleLabel[user.role]}</span></div>)}</div> : <p className="px-6 py-6 text-center text-sm text-muted">Nenhum usuário.</p>}
        </section>
      </div>
    </div>
  </section>;
}
