import { LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AcceptInvitePage } from "./pages/AcceptInvitePage";
import { AgendarDiscoveryPage } from "./pages/AgendarDiscoveryPage";
import { BibliotecaPage } from "./pages/BibliotecaPage";
import { CasesPage } from "./pages/CasesPage";
import { AccountDetailPage } from "./pages/AccountDetailPage";
import { AccountsPage } from "./pages/AccountsPage";
import { CobrancaPage } from "./pages/CobrancaPage";
import { CommercialPage } from "./pages/CommercialPage";
import { ConhecimentoPage } from "./pages/ConhecimentoPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DesignSystemPage } from "./pages/DesignSystemPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { FinanceiroPage } from "./pages/FinanceiroPage";
import { IndicadoresPage } from "./pages/IndicadoresPage";
import { JourneyConfigPage } from "./pages/JourneyConfigPage";
import { LeadsPage } from "./pages/LeadsPage";
import { LoginPage } from "./pages/LoginPage";
import { PipelinePage } from "./pages/PipelinePage";
import { PriorizacaoPage } from "./pages/PriorizacaoPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ProcessDetailPage } from "./pages/ProcessDetailPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { PublicacaoPage } from "./pages/PublicacaoPage";
import { ServicesPage } from "./pages/ServicesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TeamPage } from "./pages/TeamPage";
import { ValorPage } from "./pages/ValorPage";

function resolvePage(path: string): ReactNode {
  if (path === "/comercial") return <CommercialPage />;
  if (path === "/pipeline") return <PipelinePage />;
  if (path === "/jornada") return <JourneyConfigPage />;
  if (path === "/biblioteca") return <BibliotecaPage />;
  if (path === "/cases") return <CasesPage />;
  if (path === "/conhecimento") return <ConhecimentoPage />;
  if (path === "/leads") return <LeadsPage />;
  if (path === "/indicadores") return <IndicadoresPage />;
  if (path === "/financeiro") return <FinanceiroPage />;
  if (path === "/cobranca") return <CobrancaPage />;
  if (path === "/servicos") return <ServicesPage />;
  if (path === "/documentos") return <DocumentsPage />;
  if (path === "/equipe") return <TeamPage />;
  // Rota própria e **fora do menu lateral**: perfil é dado pessoal, não navegação de operação —
  // a porta é o popover do usuário (DAP perfil-e-contato r1).
  if (path === "/perfil") return <ProfilePage />;
  if (path === "/configuracoes") return <SettingsPage />;
  if (path === "/design-system") return <DesignSystemPage />;
  const projectDetail = path.match(/^\/projetos\/(\d+)$/);
  if (projectDetail) return <ProjectDetailPage id={Number(projectDetail[1])} />;
  if (path === "/projetos") return <ProjectsPage />;
  // A rota mais específica vem **antes** da da conta. As duas são ancoradas, então hoje a ordem
  // não decide nada — ela é o que impede que afrouxar o `$` do `accountDetail` amanhã torne esta
  // aqui inalcançável em silêncio. Nada muda no menu: o `isActive` do `Layout` casa por prefixo,
  // então "Contas" já acende e o rastro do topo já mostra o rótulo do pai.
  // A fatia 4 da issue #67 renomeou o componente (`ProcessoDetailPage` → `ProcessDetailPage`)
  // e **não** a rota: `/contas/:id/processos/:pid` é copy visível na barra de endereço, e
  // trocá-la seria mudança de superfície sem DAP — além de matar link de favorito, que é o
  // mesmo defeito que o redirecionamento `/clientes*` → `/contas*` existe para evitar.
  const processoDetail = path.match(/^\/contas\/(\d+)\/processos\/(\d+)$/);
  if (processoDetail) return <ProcessDetailPage clientId={Number(processoDetail[1])} id={Number(processoDetail[2])} />;
  // A priorização é sempre **de uma conta**, e por isso pende dela em vez de virar item de menu:
  // um item que abre pedindo "qual conta?" é um beco (DAP priorização r1, decisão A1). A rota fica
  // acima da da conta pela razão escrita no bloco do processo — ordem por especificidade.
  const priorizacao = path.match(/^\/contas\/(\d+)\/priorizacao$/);
  if (priorizacao) return <PriorizacaoPage accountId={Number(priorizacao[1])} />;
  // O Value Ledger é simétrico à priorização, e pela mesma razão: valor é sempre **de uma conta**,
  // então a tela pende dela em vez de virar item de menu (DAP `dap-prove-e-valor-r1`, decisão D1).
  const valor = path.match(/^\/contas\/(\d+)\/valor$/);
  if (valor) return <ValorPage accountId={Number(valor[1])} />;
  // A publicação do Discovery é a terceira tela que pende da conta, e pelo mesmo motivo das duas
  // de cima: **o que o cliente vê** é sempre de uma conta, e um item de menu que abre perguntando
  // "qual conta?" é um beco (DAP `dap-publicacao-discovery-r1`, decisão A1). Fica acima da rota da
  // conta por especificidade, como as anteriores — as três são ancoradas, então a ordem não decide
  // nada hoje; ela é o que impede que afrouxar o `$` do `accountDetail` amanhã torne esta
  // inalcançável em silêncio.
  const publicacao = path.match(/^\/contas\/(\d+)\/publicacao$/);
  if (publicacao) return <PublicacaoPage accountId={Number(publicacao[1])} />;
  const accountDetail = path.match(/^\/contas\/(\d+)$/);
  if (accountDetail) return <AccountDetailPage id={Number(accountDetail[1])} />;
  if (path === "/contas") return <AccountsPage />;
  return <DashboardPage />;
}

// `/clientes*` → `/contas*`. **Alias com data**, no espírito da `docs/ontology/aliases.md`: o link
// antigo está no favorito de quem usa o produto, e link que morre é o mesmo defeito que a
// `aliases.md` descreve para rota de API. Some na `/api/v2/`, junto da rota `/clients/`.
function rotaLegada(path: string): string | null {
  if (path !== "/clientes" && !path.startsWith("/clientes/")) return null;
  return `/contas${path.slice("/clientes".length)}`;
}

export function App() {
  const { isLoading, user } = useAuth();
  if (window.location.pathname === "/aceitar-convite") return <AcceptInvitePage />;
  // Pública e movida a token, como a de cima — mas fala com um cliente que nunca vai ter login
  // (DAP `dap-agendamento-discovery-r1`), então resolve antes do portão de sessão do mesmo jeito.
  const agendar = window.location.pathname.match(/^\/agendar\/([^/]+)$/);
  if (agendar) return <AgendarDiscoveryPage token={decodeURIComponent(agendar[1])} />;
  const destino = rotaLegada(window.location.pathname);
  if (destino) {
    window.location.replace(`${destino}${window.location.search}${window.location.hash}`);
    return null;
  }
  if (isLoading) return <div className="grid min-h-screen place-items-center bg-canvas"><LoaderCircle className="size-7 animate-spin text-accent" aria-label="Carregando sessão" /></div>;
  if (!user) return <LoginPage />;
  return <Layout>{resolvePage(window.location.pathname)}</Layout>;
}
