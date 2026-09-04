import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { SessionUser } from "../types";

import { ProfilePage } from "./ProfilePage";

const mocks = vi.hoisted(() => ({
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
  removeAvatar: vi.fn(),
  changePassword: vi.fn(),
  refreshUser: vi.fn(),
  user: {
    id: 7, username: "daniel", first_name: "Daniel", last_name: "Campos",
    email: "daniel@biahflow.ai", role: "delivery", is_admin: false,
    has_avatar: false, avatar_updated_at: null,
  } as SessionUser,
}));

vi.mock("../api", () => ({
  updateProfile: mocks.updateProfile,
  uploadAvatar: mocks.uploadAvatar,
  removeAvatar: mocks.removeAvatar,
  changePassword: mocks.changePassword,
  avatarUrl: (user: { id: number }) => `/api/v2/users/${user.id}/avatar/`,
}));
vi.mock("../auth", () => ({ useAuth: () => ({ user: mocks.user, refreshUser: mocks.refreshUser }) }));

// Cada cartão é um `<form>` com nome acessível — `role="form"`, e não `region`. O nome vem do
// `<h2>` do cartão, que é o que amarra a mensagem ao cartão certo nas asserções abaixo.
const cartaoSenha = () => screen.getByRole("form", { name: "Senha" });
const cartaoFoto = () => screen.getByRole("form", { name: "Foto e nome" });

beforeEach(() => {
  mocks.user = { ...mocks.user, first_name: "Daniel", last_name: "Campos", has_avatar: false, avatar_updated_at: null };
  mocks.updateProfile.mockResolvedValue(mocks.user);
  mocks.uploadAvatar.mockResolvedValue(mocks.user);
  mocks.removeAvatar.mockResolvedValue(mocks.user);
  mocks.changePassword.mockResolvedValue(undefined);
  mocks.refreshUser.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("mostra o nome, o sobrenome e o e-mail somente leitura", () => {
  render(<ProfilePage />);

  expect(screen.getByRole("heading", { name: "Meu perfil", level: 1 })).toBeInTheDocument();
  expect(screen.getByLabelText("Nome")).toHaveValue("Daniel");
  expect(screen.getByLabelText("Sobrenome")).toHaveValue("Campos");
  const email = screen.getByLabelText("E-mail");
  expect(email).toHaveValue("daniel@biahflow.ai");
  // O e-mail é a credencial de login: a tela não o edita, e só um admin o troca.
  expect(email).toBeDisabled();
  expect(screen.getByText("O e-mail é a sua identidade de acesso e só um administrador pode alterá-lo.")).toBeInTheDocument();
});

test("sem foto, o avatar mostra as iniciais e o Remover fica desligado", () => {
  render(<ProfilePage />);

  expect(within(cartaoFoto()).getByText("DA")).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "Foto de perfil" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remover" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Enviar foto" })).toBeEnabled();
});

test("com foto, mostra a miniatura e libera Trocar foto e Remover", () => {
  mocks.user = { ...mocks.user, has_avatar: true, avatar_updated_at: "2026-08-27T12:00:00Z" };
  render(<ProfilePage />);

  expect(screen.getByRole("img", { name: "Foto de perfil" })).toHaveAttribute("src", "/api/v2/users/7/avatar/");
  expect(screen.getByRole("button", { name: "Trocar foto" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Remover" })).toBeEnabled();
});

test("salvar o nome emite a requisição certa e recarrega a sessão", async () => {
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.clear(screen.getByLabelText("Nome"));
  await user.type(screen.getByLabelText("Nome"), "Daniela");
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.updateProfile).toHaveBeenCalledWith({ first_name: "Daniela", last_name: "Campos" }));
  // Sem o `refreshUser` o topbar continuaria com o nome antigo até a pessoa recarregar a página.
  expect(mocks.refreshUser).toHaveBeenCalled();
  expect(await within(cartaoFoto()).findByRole("status")).toHaveTextContent("Alterações salvas.");
});

test("o erro de salvar o nome fica dentro do cartão de foto e nome", async () => {
  mocks.updateProfile.mockRejectedValue(new Error("Não foi possível concluir a operação."));
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.click(screen.getByRole("button", { name: "Salvar" }));

  expect(await within(cartaoFoto()).findByRole("alert")).toHaveTextContent("Não foi possível concluir a operação.");
  expect(within(cartaoSenha()).queryByRole("alert")).not.toBeInTheDocument();
});

test("envia a foto escolhida", async () => {
  const user = userEvent.setup();
  render(<ProfilePage />);
  const arquivo = new File(["retrato"], "retrato.png", { type: "image/png" });

  await user.upload(screen.getByLabelText("Arquivo da foto"), arquivo);

  await waitFor(() => expect(mocks.uploadAvatar).toHaveBeenCalledWith(arquivo));
  expect(mocks.refreshUser).toHaveBeenCalled();
});

test("o arquivo recusado pelo servidor vira erro dentro do cartão da foto", async () => {
  mocks.uploadAvatar.mockRejectedValue(new Error("A imagem excede o limite de 2 MB."));
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.upload(screen.getByLabelText("Arquivo da foto"), new File(["x"], "grande.png", { type: "image/png" }));

  expect(await within(cartaoFoto()).findByRole("alert")).toHaveTextContent("A imagem excede o limite de 2 MB.");
});

test("remove a foto", async () => {
  mocks.user = { ...mocks.user, has_avatar: true, avatar_updated_at: "2026-08-27T12:00:00Z" };
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.click(screen.getByRole("button", { name: "Remover" }));

  await waitFor(() => expect(mocks.removeAvatar).toHaveBeenCalled());
  expect(mocks.refreshUser).toHaveBeenCalled();
});

test("troca a senha e limpa os três campos", async () => {
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.type(screen.getByLabelText("Senha atual"), "SenhaAtual1!");
  await user.type(screen.getByLabelText("Nova senha"), "SenhaNova987!");
  await user.type(screen.getByLabelText("Confirmar nova senha"), "SenhaNova987!");
  await user.click(screen.getByRole("button", { name: "Trocar senha" }));

  await waitFor(() => expect(mocks.changePassword).toHaveBeenCalledWith({
    current_password: "SenhaAtual1!",
    new_password: "SenhaNova987!",
    new_password_confirm: "SenhaNova987!",
  }));
  expect(await within(cartaoSenha()).findByRole("status")).toHaveTextContent("Senha alterada.");
  expect(screen.getByLabelText("Senha atual")).toHaveValue("");
  expect(screen.getByLabelText("Nova senha")).toHaveValue("");
  expect(screen.getByLabelText("Confirmar nova senha")).toHaveValue("");
});

test("o erro de senha atual aparece dentro do cartão de senha, e o de foto e nome fica intacto", async () => {
  mocks.changePassword.mockRejectedValue(new Error("A senha atual está incorreta."));
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.type(screen.getByLabelText("Nome"), "x");
  await user.type(screen.getByLabelText("Senha atual"), "errada");
  await user.type(screen.getByLabelText("Nova senha"), "SenhaNova987!");
  await user.type(screen.getByLabelText("Confirmar nova senha"), "SenhaNova987!");
  await user.click(screen.getByRole("button", { name: "Trocar senha" }));

  // `within(cartão)` e não `screen`: com `screen` o teste passaria mesmo com a mensagem no topo
  // da página, que é exatamente o que o DAP recusou.
  expect(await within(cartaoSenha()).findByRole("alert")).toHaveTextContent("A senha atual está incorreta.");
  expect(within(cartaoFoto()).queryByRole("alert")).not.toBeInTheDocument();
  // O cartão de cima não perde o que estava digitado.
  expect(screen.getByLabelText("Nome")).toHaveValue("Danielx");
  // Nada foi enviado no cartão de cima.
  expect(mocks.updateProfile).not.toHaveBeenCalled();
});

test("a senha só é enviada com os três campos preenchidos", async () => {
  const user = userEvent.setup();
  render(<ProfilePage />);

  await user.click(screen.getByRole("button", { name: "Trocar senha" }));

  expect(mocks.changePassword).not.toHaveBeenCalled();
});
