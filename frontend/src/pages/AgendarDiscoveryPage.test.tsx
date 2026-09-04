import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ApiError } from "../api";
import { AgendarDiscoveryPage } from "./AgendarDiscoveryPage";

const mocks = vi.hoisted(() => ({
  getDiscoveryBookingSlots: vi.fn(),
  bookDiscovery: vi.fn(),
}));
vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, getDiscoveryBookingSlots: mocks.getDiscoveryBookingSlots, bookDiscovery: mocks.bookDiscovery };
});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("caminho feliz: escolhe um horário, confirma, e a tela passa a mostrar o marcado", async () => {
  const user = userEvent.setup();
  mocks.getDiscoveryBookingSlots
    .mockResolvedValueOnce({
      account: "Rio Home Care",
      slots: ["2026-09-10T13:00:00Z", "2026-09-10T15:00:00Z", "2026-09-11T13:00:00Z"],
      scheduled_at: null,
    })
    .mockResolvedValueOnce({ account: "Rio Home Care", slots: [], scheduled_at: "2026-09-10T13:00:00Z" });
  mocks.bookDiscovery.mockResolvedValue({ starts_at: "2026-09-10T13:00:00Z", link: "https://calendar.example/x" });

  render(<AgendarDiscoveryPage token="tok-1" />);

  expect(await screen.findByRole("heading", { name: "Vamos marcar seu Discovery" })).toBeInTheDocument();
  expect(screen.getByText("Rio Home Care")).toBeInTheDocument();

  // O botão de confirmar começa desabilitado: nada foi escolhido ainda.
  expect(screen.getByRole("button", { name: "Escolha um horário" })).toBeDisabled();

  const horarios = screen.getAllByRole("button", { pressed: false });
  await user.click(horarios[0]);

  const confirmar = screen.getByRole("button", { name: /^Confirmar/ });
  expect(confirmar).toBeEnabled();
  await user.click(confirmar);

  await waitFor(() => expect(mocks.bookDiscovery).toHaveBeenCalledWith({ token: "tok-1", slot_start: "2026-09-10T13:00:00Z" }));
  expect(await screen.findByRole("heading", { name: "Está marcado" })).toBeInTheDocument();
  expect(screen.getByText(/O convite foi para o seu e-mail\./)).toBeInTheDocument();
  expect(screen.getByText("Discovery agendado")).toBeInTheDocument();
});

test("já agendado: mostra o horário marcado direto, sem oferecer escolha", async () => {
  mocks.getDiscoveryBookingSlots.mockResolvedValue({
    account: "Rio Home Care",
    slots: [],
    scheduled_at: "2026-09-10T13:00:00Z",
  });

  render(<AgendarDiscoveryPage token="tok-2" />);

  expect(await screen.findByRole("heading", { name: "Está marcado" })).toBeInTheDocument();
  expect(screen.getByText(/Precisa mudar\? Responda ao e-mail que enviamos\./)).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("estado de exceção: link expirado", async () => {
  mocks.getDiscoveryBookingSlots.mockRejectedValue(new ApiError("Este link expirou.", 400, "", "token_expired"));

  render(<AgendarDiscoveryPage token="tok-3" />);

  expect(await screen.findByRole("heading", { name: "Seu link expirou" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Responda ao e-mail que enviamos e mandamos outro.");
});

test("estado de exceção: link inválido, sem dizer por quê", async () => {
  mocks.getDiscoveryBookingSlots.mockRejectedValue(new ApiError("Link não reconhecido.", 400, "", "token_invalid"));

  render(<AgendarDiscoveryPage token="tok-4" />);

  expect(await screen.findByRole("heading", { name: "Link não reconhecido" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Confira se copiou o endereço inteiro.");
});

test("estado de exceção: nenhum horário livre na janela", async () => {
  mocks.getDiscoveryBookingSlots.mockResolvedValue({ account: "Rio Home Care", slots: [], scheduled_at: null });

  render(<AgendarDiscoveryPage token="tok-5" />);

  expect(await screen.findByText("Nenhum horário livre nos próximos 14 dias")).toBeInTheDocument();
  expect(screen.getByText(/Responda ao e-mail que enviamos e achamos uma data juntos\./)).toBeInTheDocument();
});

test("estado de exceção: agenda indisponível", async () => {
  mocks.getDiscoveryBookingSlots.mockRejectedValue(
    new ApiError("Não foi possível consultar a agenda.", 503, "", "calendar_unavailable"),
  );

  render(<AgendarDiscoveryPage token="tok-6" />);

  expect(await screen.findByRole("heading", { name: "Não foi possível carregar os horários" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Tente de novo em alguns minutos.");
});

// O quinto estado, que não está no board: a flag `discovery_booking`/`calendar_sync` desligada.
// Governança (spec da tarefa): mesma mensagem de `calendar_unavailable`, porque para quem está do
// outro lado do link as duas são a mesma coisa — não dá para escolher agora, e a culpa não é dele.
test("estado de exceção: agendamento desligado (booking_disabled) usa a mesma mensagem de agenda indisponível", async () => {
  mocks.getDiscoveryBookingSlots.mockRejectedValue(
    new ApiError("Agendamento indisponível.", 503, "", "booking_disabled"),
  );

  render(<AgendarDiscoveryPage token="tok-7" />);

  expect(await screen.findByRole("heading", { name: "Não foi possível carregar os horários" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Tente de novo em alguns minutos.");
});

test("corrida no clique: horário some entre o carregamento e a confirmação, e a tela recarrega em vez de deixar o cliente no escuro", async () => {
  const user = userEvent.setup();
  mocks.getDiscoveryBookingSlots
    .mockResolvedValueOnce({ account: "Rio Home Care", slots: ["2026-09-10T13:00:00Z"], scheduled_at: null })
    .mockResolvedValueOnce({ account: "Rio Home Care", slots: ["2026-09-11T13:00:00Z"], scheduled_at: null });
  mocks.bookDiscovery.mockRejectedValue(new ApiError("Horário indisponível.", 409, "", "slot_unavailable"));

  render(<AgendarDiscoveryPage token="tok-8" />);

  const primeiroHorario = await screen.findAllByRole("button", { pressed: false });
  await user.click(primeiroHorario[0]);
  await user.click(screen.getByRole("button", { name: /^Confirmar/ }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Esse horário acabou de ser preenchido. Escolha outro.");
  expect(mocks.getDiscoveryBookingSlots).toHaveBeenCalledTimes(2);
  // O horário novo (recarregado) volta a aparecer, e o botão de confirmar volta a pedir escolha.
  expect(screen.getByRole("button", { name: "Escolha um horário" })).toBeInTheDocument();
});
