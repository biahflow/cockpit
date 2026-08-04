import { CheckCircle2, KeyRound } from "lucide-react";
import { type FormEvent, useState } from "react";

import { acceptInvitation } from "../api";

export function AcceptInvitePage() {
  const initialToken = new URLSearchParams(window.location.search).get("token") ?? "";
  const [form, setForm] = useState({ token: initialToken, username: "", password: "", first_name: "", last_name: "" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await acceptInvitation(form); setDone(true); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <div className="grid min-h-screen place-items-center bg-sand px-4 py-10">
    <div className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-sm sm:p-8">
      {done ? <div className="text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-mint text-ocean"><CheckCircle2 className="size-6" /></span>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-ink">Acesso ativado</h1>
        <p className="mt-2 text-sm text-slate-500">Sua conta foi criada. Você já pode entrar no portal.</p>
        <a href="/" className="mt-6 inline-flex items-center justify-center rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink">Ir para o login</a>
      </div> : <>
        <p className="text-sm font-semibold text-ocean">Bem-vindo</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Ative seu acesso</h1>
        <p className="mt-2 text-sm text-slate-500">Defina seu usuário e senha para entrar no Portal Biahflow.</p>
        {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
        <form className="mt-6 grid gap-4" onSubmit={event => void submit(event)}>
          <label className="grid gap-2 text-sm font-medium text-slate-700">Token do convite<input className="field" value={form.token} onChange={event => setForm({ ...form, token: event.target.value })} placeholder="Cole o token recebido por e-mail" required /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium text-slate-700">Nome<input className="field" value={form.first_name} onChange={event => setForm({ ...form, first_name: event.target.value })} /></label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">Sobrenome<input className="field" value={form.last_name} onChange={event => setForm({ ...form, last_name: event.target.value })} /></label>
          </div>
          <label className="grid gap-2 text-sm font-medium text-slate-700">Usuário<input className="field" value={form.username} onChange={event => setForm({ ...form, username: event.target.value })} required /></label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">Senha<input className="field" type="password" value={form.password} onChange={event => setForm({ ...form, password: event.target.value })} required /></label>
          <button className="inline-flex items-center justify-center gap-2 rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><KeyRound className="size-4" />Ativar acesso</button>
        </form>
      </>}
    </div>
  </div>;
}
