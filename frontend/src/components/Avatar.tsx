import { avatarUrl } from "../api";
import type { SessionUser } from "../types";

/** Iniciais ou foto — **o mesmo componente nos dois casos**, não dois (DAP perfil-e-contato r1).
 *
 * A alternativa seria cada tela decidir entre `<span class="avatar">` e `<img>`, e ela é pior por
 * um motivo concreto: a regra de quando há foto, o recorte e a URL autenticada passariam a viver
 * em dois lugares — o topbar e o perfil — e divergiriam sem nada ficar vermelho.
 *
 * `alt` carrega o nome de propósito. No celular a legenda do botão do topbar é `hidden`, então
 * com `alt=""` o botão ficaria **sem nome acessível** e o axe reprovaria — a foto é o único
 * conteúdo dele naquela largura. */
export function Avatar({ user, name, size = "sm" }: { user: SessionUser; name: string; size?: "sm" | "lg" }) {
  const base = size === "lg" ? "photo" : "avatar";
  if (user.has_avatar) {
    return <img className={base} src={avatarUrl(user)} alt={size === "lg" ? "Foto de perfil" : name} />;
  }
  return <span className={size === "lg" ? "photo photo--initials" : base}>{name.slice(0, 2).toUpperCase()}</span>;
}
