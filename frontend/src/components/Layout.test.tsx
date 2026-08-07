import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { Layout } from "./Layout";

const mocks = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock("../api", () => ({
  listNotifications: mocks.listNotifications,
  markNotificationRead: mocks.markNotificationRead,
  markAllNotificationsRead: mocks.markAllNotificationsRead,
}));
vi.mock("../auth", () => ({ useAuth: mocks.useAuth }));

// Na prática: "invisível para a Entrega". Leads, Indicadores e Financeiro são admin+Vendas.
const ADMIN_ONLY = ["Leads", "Indicadores", "Financeiro", "Jornada", "Equipe", "Configurações"];

function renderComo(user: { role: string; is_admin: boolean }) {
  mocks.useAuth.mockReturnValue({ logout: vi.fn(), user: { id: 1, username: "u", first_name: "Bia", last_name: "", email: "b@x.test", ...user } });
  return render(<Layout><p>conteúdo</p></Layout>);
}

// O menu aparece duas vezes no DOM (barra lateral e gaveta do celular), então conta-se por
// `getAllByRole` em vez de assumir um só.
const temLink = (nome: string) => screen.queryAllByRole("link", { name: nome }).length > 0;

beforeEach(() => { mocks.listNotifications.mockResolvedValue([]); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("Entrega não vê os itens de administração", () => {
  renderComo({ role: "delivery", is_admin: false });
  for (const item of ADMIN_ONLY) expect(temLink(item), item).toBe(false);
  expect(temLink("Projetos")).toBe(true);
});

test("superusuário de papel Entrega vê o menu inteiro", () => {
  // O defeito: `createsuperuser` deixa `role` em `delivery` e a API já trata a pessoa como admin
  // (`is_admin_role`). Filtrando só por `role`, o SPA escondia estes cinco itens — inclusive
  // Equipe, que é onde se monta a equipe de projeto (FDD 017).
  renderComo({ role: "delivery", is_admin: true });
  for (const item of ADMIN_ONLY) expect(temLink(item), item).toBe(true);
});

test("admin por papel vê o menu inteiro", () => {
  renderComo({ role: "admin", is_admin: true });
  for (const item of ADMIN_ONLY) expect(temLink(item), item).toBe(true);
});

test("Vendas vê o que é seu e não o resto", () => {
  renderComo({ role: "sales", is_admin: false });
  expect(temLink("Leads")).toBe(true);
  expect(temLink("Indicadores")).toBe(true);
  expect(temLink("Financeiro")).toBe(true);
  expect(temLink("Configurações")).toBe(false);
  expect(temLink("Equipe")).toBe(false);
});

test("o rótulo segue o poder, não o campo", () => {
  // Chamar de "Entrega" alguém que manda no portal inteiro é o rótulo mentindo sobre quem está
  // logado — e foi o que mais confundiu quem seguiu o roteiro de instalação.
  renderComo({ role: "delivery", is_admin: true });
  expect(screen.getAllByText("Administrador").length).toBeGreaterThan(0);
  expect(screen.queryByText("Entrega")).toBeNull();
});

test("quem é Entrega de verdade continua rotulado como Entrega", () => {
  renderComo({ role: "delivery", is_admin: false });
  expect(screen.getAllByText("Entrega").length).toBeGreaterThan(0);
});
