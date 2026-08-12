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

  return <section className="panel sm:p-6">
    <div className="panel-heading panel-heading--icon"><span className="metric-icon"><Sparkles className="size-4" /></span><div><h2>{title}</h2><p className="text-sm text-muted">Sugestões para revisão humana — nada é executado automaticamente.</p></div></div>
    <form className="flex gap-2" onSubmit={event => void ask(event)}>
      <input className="field" value={question} onChange={event => setQuestion(event.target.value)} placeholder={placeholder || "Pergunte sobre esta área"} aria-label={`Pergunta ao ${title}`} />
      <button className="btn shrink-0" type="submit" disabled={loading}>{loading ? "…" : "Perguntar"}</button>
    </form>
    {error && <p role="alert" className="alert--error mt-3">{error}</p>}
    {answer && <div className="mt-4"><p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{answer}</p>
      {/* A citação é o que separa resposta ancorada de resposta plausível (FDD 029). Vencida vai
          marcada: citar sem avisar legitimaria material velho. */}
      {sources.length > 0 && <ul className="mt-2 grid gap-1">{sources.map(source => <li key={source.ref} className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        <span className="rounded bg-accent-50 px-1.5 py-0.5 font-semibold text-accent">{source.ref}</span>
        <span>{source.title} › {source.section}</span>
        {source.stale && <span className="rounded bg-red-50 px-1.5 py-0.5 font-semibold text-danger">Vencido</span>}
      </li>)}</ul>}
      <div className="mt-2 flex items-center gap-2 text-slate-600"><span className="text-xs">Esta resposta ajudou?</span>
        <button className={`rounded-lg p-1.5 hover:text-accent ${rated === 1 ? "text-accent" : ""}`} aria-label="Resposta útil" onClick={() => void rate(1)}><ThumbsUp className="size-4" /></button>
        <button className={`rounded-lg p-1.5 hover:text-danger ${rated === -1 ? "text-danger" : ""}`} aria-label="Resposta ruim" onClick={() => void rate(-1)}><ThumbsDown className="size-4" /></button>
      </div>
    </div>}
  </section>;
}
