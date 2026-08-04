import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";

const mocks = vi.hoisted(() => ({ getConfig: vi.fn(), setFlag: vi.fn(), syncCalendar: vi.fn() }));
vi.mock("../api", () => ({ getConfig: mocks.getConfig, setFlag: mocks.setFlag, syncCalendar: mocks.syncCalendar }));

beforeEach(() => {
  mocks.getConfig.mockResolvedValue({
    ai_enabled: false, calendar_enabled: true, esign_enabled: false,
    integrations: [
      { key: "ai", label: "Assistente de IA", enabled: false, configured: true, toggleable: true },
      { key: "esign", label: "Assinatura eletrônica", enabled: false, configured: false, toggleable: true },
      { key: "calendar", label: "Calendário (Google)", enabled: true, configured: true, toggleable: true },
      { key: "portal", label: "Portal do cliente", enabled: true, configured: true, toggleable: false },
    ],
  });
  mocks.setFlag.mockResolvedValue({ key: "ai", label: "Assistente de IA", enabled: true, configured: true, toggleable: true });
  mocks.syncCalendar.mockResolvedValue({ created: 2, skipped: 1 });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("liga uma integração configurada", async () => {
  const user = userEvent.setup();
  render(<SettingsPage />);
  expect(await screen.findByText("Assistente de IA")).toBeInTheDocument();
  const ligarButtons = screen.getAllByRole("button", { name: /Ligar/ });
  await user.click(ligarButtons[0]); // IA (configurada)
  await waitFor(() => expect(mocks.setFlag).toHaveBeenCalledWith("ai", true));
});

test("bloqueia ligar sem credenciais e mostra flag read-only", async () => {
  render(<SettingsPage />);
  await screen.findByText("Assinatura eletrônica");
  const ligarButtons = screen.getAllByRole("button", { name: /Ligar/ });
  expect(ligarButtons[1]).toBeDisabled(); // esign não configurada
  expect(screen.getByText("via .env")).toBeInTheDocument(); // portal não é alternável
});

test("sincroniza o calendário e mostra o resultado", async () => {
  const user = userEvent.setup();
  render(<SettingsPage />);
  const syncButton = await screen.findByRole("button", { name: /Sincronizar agora/ });
  await user.click(syncButton);
  await waitFor(() => expect(mocks.syncCalendar).toHaveBeenCalled());
  expect(await screen.findByText(/2 tarefa\(s\) criada\(s\), 1 ignorada/)).toBeInTheDocument();
});
