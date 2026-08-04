import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { TeamPage } from "./TeamPage";

const mocks = vi.hoisted(() => ({ listUsers: vi.fn(), listInvitations: vi.fn(), createInvitation: vi.fn() }));
vi.mock("../api", () => ({ listUsers: mocks.listUsers, listInvitations: mocks.listInvitations, createInvitation: mocks.createInvitation }));

beforeEach(() => {
  mocks.listUsers.mockResolvedValue([{ id: 1, username: "bia", first_name: "Bia", last_name: "", email: "bia@x.com", role: "admin" }]);
  mocks.listInvitations.mockResolvedValue([{ id: 1, email: "novo@x.com", role: "delivery", expires_at: "2030-01-01T00:00:00Z", accepted_at: null, created_at: "2026-08-01T00:00:00Z" }]);
  mocks.createInvitation.mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista usuários e convites", async () => {
  render(<TeamPage />);
  expect(await screen.findByText("Bia")).toBeInTheDocument();
  expect(screen.getByText("novo@x.com")).toBeInTheDocument();
  expect(screen.getByText("Pendente")).toBeInTheDocument();
});

test("envia um convite", async () => {
  const user = userEvent.setup();
  render(<TeamPage />);
  await screen.findByText("Bia");
  await user.type(screen.getByLabelText("E-mail"), "pessoa@x.com");
  await user.click(screen.getByRole("button", { name: "Enviar convite" }));
  await waitFor(() => expect(mocks.createInvitation).toHaveBeenCalledWith("pessoa@x.com", "delivery"));
});
