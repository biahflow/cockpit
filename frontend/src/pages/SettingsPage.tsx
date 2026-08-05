import { Power, RefreshCw, Settings } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getConfig, setFlag, syncCalendar } from "../api";
import type { IntegrationFlag } from "../types";

function hint(flag: IntegrationFlag): string {
  if (!flag.toggleable) return "Controlada por variáveis de ambiente.";
  if (!flag.configured) return "Faltam credenciais no ambiente para ligar.";
  return flag.enabled ? "Ativa." : "Desligada.";
}

export function SettingsPage() {
  const [flags, setFlags] = useState<IntegrationFlag[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState("");

  const load = useCallback(
    () => getConfig().then(config => setFlags(config.integrations)).catch((cause: Error) => setError(cause.message)),
    [],
  );
  useEffect(() => { void load(); }, [load]);

  async function toggle(flag: IntegrationFlag) {
    setError(""); setBusy(flag.key);
    try { await setFlag(flag.key, !flag.enabled); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(null); }
  }

  async function runCalendarSync() {
    setError(""); setSyncResult(""); setSyncing(true);
    try {
      const { created, skipped } = await syncCalendar();
      setSyncResult(`Sincronização concluída: ${created} tarefa(s) criada(s), ${skipped} ignorada(s).`);
    } catch (cause) { setError((cause as Error).message); }
    finally { setSyncing(false); }
  }

  return <section className="space-y-7">
    <header><p className="text-sm font-semibold text-ocean">Administração</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Configurações</h1><p className="mt-2 text-sm text-slate-600">Ligue ou desligue integrações sem novo deploy. Credenciais continuam no ambiente.</p></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    {syncResult && <p role="status" className="rounded-xl bg-mint/60 p-3 text-sm text-ocean">{syncResult}</p>}

    <section className="overflow-hidden rounded-2xl border bg-white">
      <div className="flex items-center gap-3 border-b px-5 py-4 sm:px-6"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><Settings className="size-4" /></span><div><h2 className="font-semibold text-ink">Integrações</h2><p className="mt-0.5 text-sm text-slate-600">Estado atual de cada recurso conectável.</p></div></div>
      {flags.length ? <div className="divide-y">{flags.map(flag => <div className="flex flex-wrap items-center gap-4 px-5 py-4 sm:px-6" key={flag.key}>
        <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">{flag.label}</p><p className="mt-0.5 text-xs text-slate-600">{hint(flag)}</p></div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${flag.enabled ? "bg-mint text-ocean" : "bg-slate-100 text-slate-600"}`}>{flag.enabled ? "Ligada" : "Desligada"}</span>
        {flag.key === "calendar" && flag.enabled && <button className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold text-slate-600 hover:border-ocean hover:text-ocean disabled:cursor-not-allowed disabled:opacity-50" disabled={syncing} onClick={() => void runCalendarSync()}><RefreshCw className={`size-4${syncing ? " animate-spin" : ""}`} />{syncing ? "Sincronizando…" : "Sincronizar agora"}</button>}
        {flag.toggleable
          ? <button className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold text-slate-600 hover:border-ocean hover:text-ocean disabled:cursor-not-allowed disabled:opacity-50" disabled={busy === flag.key || (!flag.enabled && !flag.configured)} onClick={() => void toggle(flag)}><Power className="size-4" />{busy === flag.key ? "Salvando…" : flag.enabled ? "Desligar" : "Ligar"}</button>
          : <span className="text-xs font-medium text-slate-600">via .env</span>}
      </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Carregando integrações…</p>}
    </section>
  </section>;
}
