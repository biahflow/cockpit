import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectsPage } from "./ProjectsPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  auth: { user: { role: "admin", is_admin: true }, aiEnabled: false } as {
    user: { role: string; is_admin: boolean } | null;
    aiEnabled: boolean;
  },
}));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

const ACME = { id: 7, name: "Implantação Acme", due_date: "2026-09-30", status: "active", is_overdue: false };

beforeEach(() => {
  mocks.auth.user = { role: "admin", is_admin: true };
  mocks.api.mockImplementation((path: string) => Promise.resolve(path.includes("archived=1") ? [] : [ACME]));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("a aba de arquivados pede a lista arquivada e oferece restaurar", async () => {
  // As duas abas são a mesma rota com um parâmetro, e o botão Restaurar só existe numa delas: sem
  // isto, trocar o `?archived=1` por engano deixaria a tela mostrando ativos sob o título
  // "Arquivados" — verde no teste de rota, errado na tela.
  mocks.api.mockImplementation((path: string) => Promise.resolve(path.includes("archived=1") ? [ACME] : []));
  const user = userEvent.setup();
  render(<ProjectsPage />);

  await user.click(screen.getByRole("button", { name: "Arquivados" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/?archived=1"));
  expect(await screen.findByRole("button", { name: "Restaurar" })).toBeInTheDocument();
});

test("restaurar chama unarchive e recarrega a lista", async () => {
  // `unarchive` resolve o objeto pelo queryset cru, e a lista precisa ser relida depois — senão o
  // projeto restaurado continua aparecendo entre os arquivados até alguém apertar F5.
  mocks.api.mockImplementation((path: string) => Promise.resolve(path.includes("archived=1") ? [ACME] : []));
  const user = userEvent.setup();
  render(<ProjectsPage />);
  await user.click(screen.getByRole("button", { name: "Arquivados" }));

  await user.click(await screen.findByRole("button", { name: "Restaurar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/7/unarchive/", { method: "POST" }));
  // Duas leituras da lista arquivada: a da troca de aba e a de depois do restore.
  expect(mocks.api.mock.calls.filter(([path]) => path === "/projects/?archived=1")).toHaveLength(2);
});

test("Entrega restrita não recebe o convite para converter oportunidade", async () => {
  // RFC 0003: entrega não converte oportunidade. Oferecer o atalho a quem a API vai recusar é
  // prometer uma ação que não existe.
  mocks.auth.user = { role: "delivery", is_admin: false };
  render(<ProjectsPage />);
  await screen.findByText("Implantação Acme");

  expect(screen.queryByRole("link", { name: /Converter oportunidade/ })).not.toBeInTheDocument();
});

test("um superusuário com papel de entrega não é Entrega restrita", async () => {
  // "Entrega" no sentido do papel e "Entrega restrita" no sentido do escopo são coisas
  // diferentes, e a distinção é `is_admin`. Sem ela, um administrador que por acaso tem papel
  // `delivery` seria mandado "pedir a um administrador" — isto é, pedir a si mesmo.
  mocks.auth.user = { role: "delivery", is_admin: true };
  render(<ProjectsPage />);
  await screen.findByText("Implantação Acme");

  expect(screen.getByRole("link", { name: /Converter oportunidade/ })).toBeInTheDocument();
});

test("lista vazia diz coisas diferentes para quem pode criar projeto e para quem não pode", async () => {
  // A lista vazia da entrega significa "ninguém te pôs numa equipe", não "não há projetos" — e a
  // saída de cada um é outra: uma é esperar alguém, a outra é ir ao Comercial.
  mocks.api.mockImplementation(() => Promise.resolve([]));
  mocks.auth.user = { role: "delivery", is_admin: false };
  const { unmount } = render(<ProjectsPage />);
  expect(await screen.findByText("Você ainda não participa de nenhum projeto")).toBeInTheDocument();
  unmount();

  mocks.auth.user = { role: "admin", is_admin: true };
  render(<ProjectsPage />);
  expect(await screen.findByText("Nenhum projeto em andamento")).toBeInTheDocument();
});

test("prazo vencido usa o token de perigo, e hoje é só isso que o distingue", async () => {
  // `is_overdue` vem da API e a linha inteira depende dele: sem a marca, uma data no passado lê
  // igual a uma no futuro.
  //
  // O que este teste **não** prova, e vale dizer: a distinção é só visual. O `AlertTriangle` que
  // acompanha o vermelho não tem rótulo acessível, então quem não distingue a cor lê a data e não
  // sabe que ela passou (WCAG 1.4.1). O axe não pega — ele mede contraste, não significado
  // carregado por cor. Fica nomeado aqui porque é onde alguém vai olhar quando for consertar.
  mocks.api.mockImplementation((path: string) => Promise.resolve(
    path.includes("archived=1") ? [] : [{ ...ACME, is_overdue: true }],
  ));
  render(<ProjectsPage />);

  const prazo = await screen.findByText("30/09/2026");
  expect(prazo.closest("td")).toHaveClass("text-danger");
});

test("erro da API aparece como alerta e não como lista vazia", async () => {
  // Uma falha de carga que renderiza o estado vazio diz "não há projetos" quando o certo é "não
  // consegui saber" — e o estado vazio ainda manda tomar uma ação a partir de uma premissa falsa.
  mocks.api.mockImplementation(() => Promise.reject(new Error("Falha ao carregar projetos")));
  render(<ProjectsPage />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Falha ao carregar projetos");
});
