import { BarChart3, Bell, ChevronDown, FileText, FolderKanban, Inbox, LayoutDashboard, LogOut, Menu, Route, Settings, Users, UsersRound, WalletCards } from "lucide-react";
import { type ComponentType, type ReactNode, useEffect, useState } from "react";

import { listNotifications, markAllNotificationsRead, markNotificationRead } from "../api";
import { useAuth } from "../auth";
import type { Notification as NotificationT, Role } from "../types";

type NavLink = readonly [string, string, ComponentType<{ className?: string }>, Role[]?];

const links: NavLink[] = [
  ["/", "Visão geral", LayoutDashboard],
  ["/comercial", "Comercial", WalletCards],
  ["/leads", "Leads", Inbox, ["admin", "sales"]],
  ["/clientes", "Clientes", UsersRound],
  ["/projetos", "Projetos", FolderKanban],
  ["/documentos", "Documentos", FileText],
  ["/indicadores", "Indicadores", BarChart3, ["admin", "sales"]],
  ["/jornada", "Jornada", Route, ["admin"]],
  ["/equipe", "Equipe", Users, ["admin"]],
  ["/configuracoes", "Configurações", Settings, ["admin"]],
];

const roleLabel = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" } as const;

export function Layout({ children }: { children: ReactNode }) {
  const [isMobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isUserMenuOpen, setUserMenuOpen] = useState(false);
  const [isBellOpen, setBellOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationT[]>([]);
  const { logout, user } = useAuth();
  const path = window.location.pathname;
  useEffect(() => { void listNotifications().then(setNotifications).catch(() => undefined); }, []);
  if (!user) return null;
  const displayName = user.first_name || user.username;
  const unread = notifications.filter(notification => !notification.read).length;

  async function handleLogout() {
    await logout();
    window.location.assign("/");
  }
  async function readOne(item: NotificationT) {
    if (!item.read) {
      await markNotificationRead(item.id).catch(() => undefined);
      setNotifications(prev => prev.map(n => n.id === item.id ? { ...n, read: true } : n));
    }
    if (item.url) window.location.assign(item.url);
  }
  async function readAll() {
    await markAllNotificationsRead().catch(() => undefined);
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }

  const isActive = (to: string) => to === "/" ? path === "/" : path === to || path.startsWith(`${to}/`);
  const visibleLinks = links.filter(([, , , roles]) => !roles || roles.includes(user.role));
  const nav = <nav className="grid gap-1">{visibleLinks.map(([to, label, Icon]) => <a key={to} href={to} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive(to) ? "bg-white text-ocean shadow-sm" : "text-slate-500 hover:bg-white/70 hover:text-ink"}`}><Icon className="size-4" />{label}</a>)}</nav>;

  return <div className="min-h-screen bg-sand lg:grid lg:grid-cols-[248px_1fr]">
    <aside className="hidden border-r border-slate-200 bg-mint/50 px-5 py-6 lg:flex lg:flex-col">
      <a href="/" className="mb-10 flex items-center gap-3 px-2"><span className="grid size-9 place-items-center rounded-xl bg-ocean text-sm font-black text-white">B</span><span><strong className="block text-lg tracking-tight text-ink">Biahflow</strong><small className="text-xs text-slate-500">Portal operacional</small></span></a>
      {nav}
      <div className="mt-auto rounded-2xl border border-white bg-white/70 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-ocean">Operação ativa</p><p className="mt-1 text-sm text-slate-600">Centralize vendas e entregas em um só lugar.</p></div>
    </aside>
    <div className="min-w-0">
      <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b bg-sand/85 px-5 backdrop-blur lg:px-9">
        <button className="grid size-10 place-items-center rounded-xl border bg-white text-slate-600 lg:hidden" aria-label="Abrir menu" onClick={() => setMobileMenuOpen(!isMobileMenuOpen)}><Menu className="size-5" /></button>
        <p className="hidden text-sm text-slate-500 sm:block">Acompanhe o que importa para a Biahflow.</p>
        <div className="flex items-center gap-3">
          <div className="relative"><button className="relative grid size-10 place-items-center rounded-xl border bg-white text-slate-500 hover:text-ocean" aria-label="Notificações" onClick={() => setBellOpen(open => !open)}><Bell className="size-4" />{unread > 0 && <span className="absolute -right-1 -top-1 grid min-w-[16px] place-items-center rounded-full bg-signal px-1 text-[10px] font-bold text-white">{unread}</span>}</button>{isBellOpen && <><button className="fixed inset-0 z-30 cursor-default" aria-label="Fechar notificações" onClick={() => setBellOpen(false)} /><div className="absolute right-0 top-full z-40 mt-2 w-80 rounded-xl border bg-white p-2 shadow-lg"><div className="flex items-center justify-between px-2 py-1"><span className="text-sm font-semibold text-ink">Notificações</span>{unread > 0 && <button className="text-xs font-semibold text-ocean hover:text-ink" onClick={() => void readAll()}>Marcar todas</button>}</div><div className="max-h-80 divide-y overflow-y-auto">{notifications.length ? notifications.slice(0, 20).map(notification => <button key={notification.id} className={`block w-full px-2 py-2 text-left text-sm hover:bg-slate-50 ${notification.read ? "text-slate-400" : "font-medium text-ink"}`} onClick={() => void readOne(notification)}>{!notification.read && <span className="mr-1.5 inline-block size-1.5 rounded-full bg-ocean align-middle" />}{notification.message}</button>) : <p className="px-2 py-6 text-center text-sm text-slate-400">Sem notificações.</p>}</div></div></>}</div>
          <div className="relative"><button className="flex items-center gap-2 rounded-xl border bg-white py-1.5 pl-2 pr-3 hover:border-ocean" aria-haspopup="menu" aria-expanded={isUserMenuOpen} onClick={() => setUserMenuOpen(open => !open)}><span className="grid size-8 place-items-center rounded-lg bg-mint text-xs font-bold text-ocean">{displayName.slice(0, 2).toUpperCase()}</span><span className="hidden text-left sm:block"><span className="block text-xs font-semibold text-ink">{displayName}</span><span className="block text-[11px] text-slate-500">{roleLabel[user.role]}</span></span><ChevronDown className={`size-3 text-slate-400 transition ${isUserMenuOpen ? "rotate-180" : ""}`} /></button>{isUserMenuOpen && <><button className="fixed inset-0 z-30 cursor-default" aria-label="Fechar menu" onClick={() => setUserMenuOpen(false)} /><div className="absolute right-0 top-full z-40 mt-2 w-56 rounded-xl border bg-white p-2 shadow-lg" role="menu"><div className="border-b px-3 py-2"><p className="text-sm font-semibold text-ink">{displayName}</p><p className="truncate text-xs text-slate-500">{user.email || roleLabel[user.role]}</p></div><button className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-signal" role="menuitem" onClick={() => void handleLogout()}><LogOut className="size-4" />Sair</button></div></>}</div>
        </div>
      </header>
      {isMobileMenuOpen && <div className="border-b bg-mint/70 p-4 lg:hidden">{nav}</div>}
      <main className="mx-auto w-full max-w-7xl px-5 py-8 lg:px-9 lg:py-10">{children}</main>
    </div>
  </div>;
}
