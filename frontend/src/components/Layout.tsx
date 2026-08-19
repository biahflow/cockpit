import { BarChart3, Bell, BookMarked, BookOpen, ChevronDown, FileText, FolderKanban, HandCoins, Inbox, LayoutDashboard, LogOut, Menu, Package, Receipt, Route, Settings, Trophy, Users, UsersRound, WalletCards } from "lucide-react";
import { type ComponentType, type ReactNode, useEffect, useRef, useState } from "react";

import { useEscape } from "../a11y";
import { listNotifications, markAllNotificationsRead, markNotificationRead } from "../api";
import { useAuth } from "../auth";
import type { Notification as NotificationT, Role, SessionUser } from "../types";

type NavLink = readonly [string, string, ComponentType<{ className?: string }>, Role[]?];

const links: NavLink[] = [
  ["/", "Visão geral", LayoutDashboard],
  ["/comercial", "Comercial", WalletCards],
  ["/leads", "Leads", Inbox, ["admin", "sales"]],
  ["/clientes", "Clientes", UsersRound],
  ["/projetos", "Projetos", FolderKanban],
  ["/documentos", "Documentos", FileText],
  ["/indicadores", "Indicadores", BarChart3, ["admin", "sales"]],
  // Material comercial: quem revisa e publica é admin, quem usa na proposta é Vendas. A Entrega
  // lê pela API o case dos projetos de que participa, mas não tem o que fazer nesta tela.
  ["/cases", "Cases", Trophy, ["admin", "sales"]],
  // Vendas lê o recebível do próprio cliente; emitir, baixar e cancelar são de admin, e o
  // backend recusa (FDD 028). A Entrega não alcança nem a leitura — nem o link, nem a rota.
  ["/financeiro", "Financeiro", Receipt, ["admin", "sales"]],
  // Mesmo recorte do Financeiro logo acima, e pela mesma razão (FDD 036): `resource = "cobranca"`
  // é só-leitura para Vendas — que acompanha o que a casa disse ao cliente dela, mas não manda
  // cobrança — e fechado para a Entrega, que não alcança o recebível nem para ler.
  ["/cobranca", "Cobrança", HandCoins, ["admin", "sales"]],
  // Sem restrição de papel, de propósito: o dono de uma área pode ser de qualquer papel, e
  // avisá-lo sobre uma peça que ele não consegue abrir seria um laço quebrado (FDD 029).
  ["/conhecimento", "Conhecimento", BookOpen],
  ["/servicos", "Serviços", Package, ["admin"]],
  ["/jornada", "Jornada", Route, ["admin"]],
  ["/biblioteca", "Biblioteca", BookMarked, ["admin"]],
  ["/equipe", "Equipe", Users, ["admin"]],
  ["/configuracoes", "Configurações", Settings, ["admin"]],
];

const roleLabel = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" } as const;

// O rótulo segue o poder, não o campo: um superusuário com `role="delivery"` manda no portal
// inteiro, e chamá-lo de "Entrega" é o rótulo mentindo sobre quem está logado.
const labelFor = (user: SessionUser) => user.is_admin ? roleLabel.admin : roleLabel[user.role];

export function Layout({ children }: { children: ReactNode }) {
  const [isMobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isUserMenuOpen, setUserMenuOpen] = useState(false);
  const [isBellOpen, setBellOpen] = useState(false);
  // Os dois menus fechavam **só por clique** num overlay `fixed inset-0`: quem abriu com `Enter`
  // não tinha como fechar sem mouse. O `Escape` fecha e devolve o foco ao botão que abriu — senão
  // a pessoa é despejada no início da página, que é a metade esquecida do conserto (FDD 022).
  const botaoSino = useRef<HTMLButtonElement>(null);
  const botaoMenu = useRef<HTMLButtonElement>(null);
  useEscape(isBellOpen, () => setBellOpen(false), botaoSino);
  useEscape(isUserMenuOpen, () => setUserMenuOpen(false), botaoMenu);
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
  // `is_admin` antes do papel: a API já trata superusuário como admin, e filtrar só por `role`
  // escondia cinco itens de quem acabou de rodar `createsuperuser` — inclusive Equipe, que é onde
  // se monta a equipe de projeto.
  const visibleLinks = links.filter(([, , , roles]) => user.is_admin || !roles || roles.includes(user.role));
  // Uma pele só para o menu desde a ADR 0025: a barra lateral ficou clara e a `.nav-item--light`
  // da gaveta do celular deixou de ter o que modificar. Continua sendo uma função e não duas
  // cópias — o `visibleLinks` já filtra por papel, e duplicar a marcação faria um item novo
  // aparecer só numa das larguras. `aria-current` marca a rota atual para leitor de tela.
  const nav = () => <nav className="grid gap-1">{visibleLinks.map(([to, label, Icon]) => <a key={to} href={to} aria-current={isActive(to) ? "page" : undefined} className={`nav-item${isActive(to) ? " nav-item--active" : ""}`}><Icon className="size-4 shrink-0" />{label}</a>)}</nav>;
  // O rastro do topo (ADR 0025), no lugar da frase decorativa que ficava aqui. Sai do mesmo
  // `links` que desenha o menu: uma rota nova ganha rastro sem ninguém lembrar de uma segunda
  // lista, que é como um breadcrumb passa a mentir. Sem correspondência (uma rota de detalhe
  // como `/clientes/1`) o casamento por prefixo do `isActive` resolve.
  const currentLabel = visibleLinks.find(([to]) => isActive(to))?.[1];

  return <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[254px_1fr]">
    <aside className="sidebar hidden lg:flex">
      <a href="/" className="brand-row">
        <span className="brand-mark">B</span>
        <span><strong className="block text-[17px] font-bold leading-tight tracking-[-0.03em] text-ink">Biah<span className="text-brand-500">flow</span></strong><small className="text-[11px] text-muted">Portal operacional</small></span>
      </a>
      <p className="nav-label">Operação</p>
      {/* Só a barra lateral rola por dentro. A gaveta do celular recebe o mesmo `nav()` sem o
          container: lá a altura é a do conteúdo, e um `overflow-y-auto` cortaria o menu. */}
      <div className="nav-scroll">{nav()}</div>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><p className="eyebrow">Operação ativa</p><p className="mt-1 text-[13px] leading-relaxed text-muted">Centralize vendas e entregas em um só lugar.</p></div>
      </div>
    </aside>
    <div className="min-w-0">
      <header className="topbar">
        <button className="icon-button lg:hidden" aria-label="Abrir menu" onClick={() => setMobileMenuOpen(!isMobileMenuOpen)}><Menu className="size-5" /></button>
        <p className="breadcrumb">Biahflow{currentLabel && <><b>/</b><strong>{currentLabel}</strong></>}</p>
        <div className="topbar-actions">
          <div className="relative"><button className="icon-button" aria-label="Notificações" aria-expanded={isBellOpen} ref={botaoSino} onClick={() => setBellOpen(open => !open)}><Bell className="size-4" />{unread > 0 && <span className="notification-dot">{unread}</span>}</button>{isBellOpen && <><button className="fixed inset-0 z-30 cursor-default" aria-label="Fechar notificações" onClick={() => setBellOpen(false)} /><div className="absolute right-0 top-full z-40 popover mt-2 w-80"><div className="popover-head"><strong>Notificações</strong>{unread > 0 && <button className="text-xs font-semibold text-brand-600 hover:text-brand-700" onClick={() => void readAll()}>Marcar todas</button>}</div><div className="max-h-80 divide-y divide-line overflow-y-auto">{notifications.length ? notifications.slice(0, 20).map(notification => <button key={notification.id} className={`popover-row ${notification.read ? "text-muted" : "font-medium text-ink"}`} onClick={() => void readOne(notification)}>{!notification.read && <span className="mr-1.5 inline-block size-1.5 rounded-full bg-brand-500 align-middle" />}{notification.message}</button>) : <p className="px-3.5 py-6 text-center text-sm text-muted">Sem notificações.</p>}</div></div></>}</div>
          <div className="relative"><button className="flex items-center gap-2 rounded-xl border border-line bg-white py-1.5 pl-1.5 pr-2.5 transition-colors hover:border-brand-500" aria-haspopup="menu" aria-expanded={isUserMenuOpen} ref={botaoMenu} onClick={() => setUserMenuOpen(open => !open)}><span className="avatar">{displayName.slice(0, 2).toUpperCase()}</span><span className="hidden text-left sm:block"><span className="block text-xs font-semibold text-ink">{displayName}</span><span className="block text-[11px] text-muted">{labelFor(user)}</span></span><ChevronDown className={`size-3 text-muted transition ${isUserMenuOpen ? "rotate-180" : ""}`} /></button>{isUserMenuOpen && <><button className="fixed inset-0 z-30 cursor-default" aria-label="Fechar menu" onClick={() => setUserMenuOpen(false)} /><div className="absolute right-0 top-full z-40 popover popover-menu mt-2 w-56" role="menu"><div className="popover-user"><strong>{displayName}</strong><small>{user.email || labelFor(user)}</small></div><button className="popover-item hover:text-danger" role="menuitem" onClick={() => void handleLogout()}><LogOut className="size-4" />Sair</button></div></>}</div>
        </div>
      </header>
      {isMobileMenuOpen && <div className="border-b border-line bg-white p-4 lg:hidden">{nav()}</div>}
      <main className="mx-auto w-full max-w-7xl px-5 py-8 lg:px-9 lg:py-10">{children}</main>
    </div>
  </div>;
}
