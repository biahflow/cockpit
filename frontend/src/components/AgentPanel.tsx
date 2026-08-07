import { Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { type FormEvent, useState } from "react";

import { askAgent, rateInteraction } from "../api";
import { useAuth } from "../auth";
import type { AgentSource, Role } from "../types";

export function AgentPanel({ agentKey, title, roles, placeholder }: { agentKey: string; title: string; roles: Role[]; placeholder?: string }) {
  const { aiEnabled, user } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [interaction, setInteraction] = useState<number | null>(null);
  const [sources, setSources] = useState<AgentSource[]>([]);
  const [rated, setRated] = useState<1 | -1 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Espelha `agents.py:117` (`user.is_admin_role or user.role in agent.roles`): sem `is_admin`, um
  // superusuário via só o agente do próprio papel, embora a API liberasse os três.
  if (!aiEnabled || !user || !(user.is_admin || roles.includes(user.role))) return null;

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    setLoading(true); setAnswer(""); setInteraction(null); setSources([]); setRated(null); setError("");
    try { const reply = await askAgent(agentKey, question); setAnswer(reply.text); setInteraction(reply.interaction); setSources(reply.sources ?? []); }
    catch (cause) { setError((cause as Error).message); }
    finally { setLoading(false); }
  }
  async function rate(value: 1 | -1) {
    if (interaction === null) return;
    try { await rateInteraction(interaction, value); setRated(value); }
    catch (cause) { setError((cause as Error).message); }
  }

  return <section className="rounded-2xl border bg-white p-5 sm:p-6">
    <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><Sparkles className="size-4" /></span><div><h2 className="font-semibold text-ink">{title}</h2><p className="text-sm text-slate-600">Sugestões para revisão humana — nada é executado automaticamente.</p></div></div>
    <form className="mt-4 flex gap-2" onSubmit={event => void ask(event)}>
      <input className="field" value={question} onChange={event => setQuestion(event.target.value)} placeholder={placeholder || "Pergunte sobre esta área"} aria-label={`Pergunta ao ${title}`} />
      <button className="shrink-0 rounded-xl bg-ocean px-4 py-2 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60" type="submit" disabled={loading}>{loading ? "…" : "Perguntar"}</button>
    </form>
    {error && <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    {answer && <div className="mt-4"><p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{answer}</p>
      {/* A citação é o que separa resposta ancorada de resposta plausível (FDD 029). Vencida vai
          marcada: citar sem avisar legitimaria material velho. */}
      {sources.length > 0 && <ul className="mt-2 grid gap-1">{sources.map(source => <li key={source.ref} className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        <span className="rounded bg-mint px-1.5 py-0.5 font-semibold text-ocean">{source.ref}</span>
        <span>{source.title} › {source.section}</span>
        {source.stale && <span className="rounded bg-red-50 px-1.5 py-0.5 font-semibold text-signal">Vencido</span>}
      </li>)}</ul>}
      <div className="mt-2 flex items-center gap-2 text-slate-600"><span className="text-xs">Esta resposta ajudou?</span>
        <button className={`rounded-lg p-1.5 hover:text-ocean ${rated === 1 ? "text-ocean" : ""}`} aria-label="Resposta útil" onClick={() => void rate(1)}><ThumbsUp className="size-4" /></button>
        <button className={`rounded-lg p-1.5 hover:text-signal ${rated === -1 ? "text-signal" : ""}`} aria-label="Resposta ruim" onClick={() => void rate(-1)}><ThumbsDown className="size-4" /></button>
      </div>
    </div>}
  </section>;
}
