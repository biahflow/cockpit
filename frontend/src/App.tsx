import { LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AcceptInvitePage } from "./pages/AcceptInvitePage";
import { BibliotecaPage } from "./pages/BibliotecaPage";
import { CasesPage } from "./pages/CasesPage";
import { ClientDetailPage } from "./pages/ClientDetailPage";
import { ClientsPage } from "./pages/ClientsPage";
import { CommercialPage } from "./pages/CommercialPage";
import { ConhecimentoPage } from "./pages/ConhecimentoPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { FinanceiroPage } from "./pages/FinanceiroPage";
import { IndicadoresPage } from "./pages/IndicadoresPage";
import { JourneyConfigPage } from "./pages/JourneyConfigPage";
import { LeadsPage } from "./pages/LeadsPage";
import { LoginPage } from "./pages/LoginPage";
import { PipelinePage } from "./pages/PipelinePage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ServicesPage } from "./pages/ServicesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TeamPage } from "./pages/TeamPage";

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
  if (path === "/servicos") return <ServicesPage />;
  if (path === "/documentos") return <DocumentsPage />;
  if (path === "/equipe") return <TeamPage />;
  if (path === "/configuracoes") return <SettingsPage />;
  const projectDetail = path.match(/^\/projetos\/(\d+)$/);
  if (projectDetail) return <ProjectDetailPage id={Number(projectDetail[1])} />;
  if (path === "/projetos") return <ProjectsPage />;
  const clientDetail = path.match(/^\/clientes\/(\d+)$/);
  if (clientDetail) return <ClientDetailPage id={Number(clientDetail[1])} />;
  if (path === "/clientes") return <ClientsPage />;
  return <DashboardPage />;
}

export function App() {
  const { isLoading, user } = useAuth();
  if (window.location.pathname === "/aceitar-convite") return <AcceptInvitePage />;
  if (isLoading) return <div className="grid min-h-screen place-items-center bg-canvas"><LoaderCircle className="size-7 animate-spin text-accent" aria-label="Carregando sessão" /></div>;
  if (!user) return <LoginPage />;
  return <Layout>{resolvePage(window.location.pathname)}</Layout>;
}
