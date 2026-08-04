import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { LeadsPage } from "./LeadsPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

const lead = { id: 1, name: "Fulano", email: "f@x.com", company: "ACME", phone: "", message: "quero ajuda", source: "site", status: "new", client: null, opportunity: null, created_at: "2026-08-01" };

beforeEach(() => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/leads/" && (options?.method ?? "GET") === "GET") return Promise.resolve([lead]);
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista leads recebidos", async () => {
  render(<LeadsPage />);
  expect(await screen.findByText("Fulano")).toBeInTheDocument();
  expect(screen.getByText("ACME")).toBeInTheDocument();
  expect(screen.getByText("quero ajuda")).toBeInTheDocument();
});

test("converte um lead em oportunidade", async () => {
  const user = userEvent.setup();
  render(<LeadsPage />);
  await screen.findByText("Fulano");
  await user.click(screen.getByRole("button", { name: /Converter em oportunidade/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/leads/1/convert/", expect.objectContaining({ method: "POST" })));
});
