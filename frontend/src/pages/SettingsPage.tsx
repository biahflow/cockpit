import { Power, RefreshCw, Settings } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getConfig, setFlag, syncCalendar } from "../api";
import type { IntegrationFlag } from "../types";

function hint(flag: IntegrationFlag): string {
  // Nomear a variável que falta é o que resolve o problema de quem lê: "faltam credenciais" mandava
  // a pessoa procurar no código quais eram.
  if (!flag.configured) return `Falta no ambiente: ${flag.missing.join(", ")}.`;
  if (!flag.toggleable) return "Controlada por variáveis de ambiente.";
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
    <header className="page-head"><p className="eyebrow">Administração</p><h1>Configurações</h1><p>Ligue ou desligue integrações sem novo deploy. Credenciais continuam no ambiente.</p><a href="/design-system" className="back-link">Design system</a></header>
    {error && <p role="alert" className="alert--error">{error}</p>}
    {syncResult && <p role="status" className="alert--ok">{syncResult}</p>}

    <section className="panel panel--flush">
      <div className="panel-heading panel-heading--icon"><span className="metric-icon"><Settings className="size-4" /></span><div><h2>Integrações</h2><p className="mt-0.5 text-sm text-muted">Estado atual de cada recurso conectável.</p></div></div>
      {flags.length ? <div className="panel-rows">{flags.map(flag => <div className="row" key={flag.key}>
        <div className="row-main"><strong>{flag.label}</strong><span>{hint(flag)}</span></div>
        <div className="row-meta">
          <span className={`state ${flag.enabled ? "state--0" : "state--off"}`}>{flag.enabled ? "Ligada" : "Desligada"}</span>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
            {flag.key === "calendar" && flag.enabled && <button className="btn btn--secondary" disabled={syncing} onClick={() => void runCalendarSync()}><RefreshCw className={`size-4${syncing ? " animate-spin" : ""}`} />{syncing ? "Sincronizando…" : "Sincronizar agora"}</button>}
            {flag.toggleable
              ? <button className="btn btn--secondary" disabled={busy === flag.key || (!flag.enabled && !flag.configured)} onClick={() => void toggle(flag)}><Power className="size-4" />{busy === flag.key ? "Salvando…" : flag.enabled ? "Desligar" : "Ligar"}</button>
              : <span className="text-xs font-medium text-muted">via .env</span>}
          </div>
        </div>
      </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-muted">Carregando integrações…</p>}
    </section>
  </section>;
}
