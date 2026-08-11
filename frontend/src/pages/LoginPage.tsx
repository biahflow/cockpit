import { ArrowRight, KeyRound, LoaderCircle, LockKeyhole, UserRound } from "lucide-react";
import { type FormEvent, useState } from "react";

import { useAuth } from "../auth";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    void Promise.resolve()
      .then(() => login(username, password))
      .catch(cause => setError(cause instanceof Error ? cause.message : "Não foi possível entrar."))
      .finally(() => setSubmitting(false));
  }

  return <div className="grid min-h-screen bg-canvas lg:grid-cols-[1.1fr_.9fr]">
    <section className="auth-brand hidden lg:flex lg:flex-col"><div className="absolute -right-16 top-16 size-72 rounded-full bg-brand-500/25 blur-sm" /><div className="absolute -bottom-24 -left-12 size-80 rounded-full border-[32px] border-white/10" /><a href="/" className="relative flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-white text-base font-black text-ink">B</span><span className="text-xl font-semibold tracking-tight">Biah<span className="text-brand-200">flow</span></span></a><div className="relative my-auto max-w-lg"><p className="mb-4 text-sm font-semibold uppercase tracking-[.18em] text-brand-200">Portal operacional</p><p className="text-5xl font-semibold leading-tight tracking-tight">Clareza para vender, entregar e crescer.</p><p className="mt-6 max-w-md text-lg leading-8 text-white/75">A jornada inteira do cliente, do pipeline à execução, em uma visão que movimenta a operação.</p></div><p className="relative text-sm text-white/80">Biahflow · processos que fluem</p></section>
    <main className="grid place-items-center px-5 py-10 sm:px-10"><div className="w-full max-w-md"><div className="mb-10 lg:hidden"><div className="flex items-center gap-3 text-ink"><span className="grid size-10 place-items-center rounded-xl bg-ink font-black text-white">B</span><strong className="text-xl tracking-tight">Biahflow</strong></div></div><div className="rounded-3xl border border-line bg-white p-7 shadow-raised sm:p-9"><div className="page-head"><p className="eyebrow">Bem-vindo de volta</p><h1>Entre na sua operação</h1><p>Use suas credenciais de acesso para continuar.</p></div><form className="grid gap-5" onSubmit={submit}><label className="form-label">Usuário<span className="relative"><UserRound className="pointer-events-none absolute left-3 top-1/2 z-1 size-4 -translate-y-1/2 text-muted" /><input className="field px-10" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} placeholder="Seu usuário" required /></span></label><label className="form-label">Senha<span className="relative"><LockKeyhole className="pointer-events-none absolute left-3 top-1/2 z-1 size-4 -translate-y-1/2 text-muted" /><input className="field px-10" autoComplete="current-password" type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="Sua senha" required /></span></label>{error && <p role="alert" className="alert--error">{error}</p>}<button className="btn mt-1" disabled={isSubmitting} type="submit">{isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : <KeyRound className="size-4" />}{isSubmitting ? "Entrando…" : "Entrar no portal"}<ArrowRight className="size-4" /></button></form></div><p className="mt-6 text-center text-xs leading-5 text-slate-600">Seu acesso é gerenciado pela administração da Biahflow.</p></div></main>
  </div>;
}
