import { FileText, Save, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { Artifact, ArtifactStatus } from "../types";

// Espelha ARTIFACT_TRANSITIONS do backend: rascunho e revisão vão e voltam; depois de enviado
// só resta a decisão do cliente, que é terminal.
const NEXT: Record<ArtifactStatus, ArtifactStatus[]> = {
  draft: ["review", "sent"],
  review: ["draft", "sent"],
  sent: ["accepted", "rejected"],
  accepted: [],
  rejected: [],
};
const STATUS_BADGE: Record<ArtifactStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  review: "bg-amber-50 text-amber-700",
  sent: "bg-sky-50 text-sky-700",
  accepted: "bg-emerald-50 text-emerald-700",
  rejected: "bg-red-50 text-danger",
};
const STATUS_LABEL: Record<ArtifactStatus, string> = {
  draft: "Rascunho", review: "Em revisão", sent: "Enviado", accepted: "Aceito", rejected: "Recusado",
};

export function ArtifactsPanel({ opportunity, project, reloadToken, onChange }: {
  opportunity?: number;
  project?: number;
  reloadToken?: number;
  onChange?: () => void;
}) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const query = opportunity ? `opportunity=${opportunity}` : `project=${project}`;

  const load = useCallback(
    () => api<Artifact[]>(`/artifacts/?${query}`).then(setArtifacts).catch((cause: Error) => setError(cause.message)),
    [query],
  );
  useEffect(() => { void load(); }, [load, reloadToken]);

  async function patch(artifact: Artifact, body: Partial<Artifact>) {
    try {
      await api(`/artifacts/${artifact.id}/`, { method: "PATCH", body: JSON.stringify(body) });
      setError("");
      await load();
      onChange?.();
    } catch (cause) { setError((cause as Error).message); }
  }

  async function saveAsDocument(artifact: Artifact) {
    const content = drafts[artifact.id] ?? artifact.content;
    if (!content.trim()) return;
    try {
      const body = new FormData();
      body.append(opportunity ? "opportunity" : "project", String(opportunity ?? project));
      body.append("file", new File([content], `${artifact.kind}-${artifact.title}.txt`, { type: "text/plain" }));
      const document = await api<{ id: number }>("/documents/", { method: "POST", body });
      await patch(artifact, { document: document.id });
    } catch (cause) { setError((cause as Error).message); }
  }

  if (!artifacts.length && !error) return null;

  return <div className="mt-6 border-t pt-5">
    <h3 className="flex items-center gap-2 text-sm font-semibold text-ink"><Sparkles className="size-4 text-accent" />Artefatos da jornada</h3>
    <p className="mt-1 text-xs text-slate-600">Rascunhos gerados pela IA ficam registrados aqui até a revisão humana e a decisão do cliente.</p>
    {error && <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-danger">{error}</p>}
    <div className="mt-3 grid gap-3">{artifacts.map(artifact => {
      const content = drafts[artifact.id] ?? artifact.content;
      const dirty = content !== artifact.content;
      // `min-w-0`: item de grade não encolhe abaixo do próprio conteúdo, e o `cols` padrão do
      // `<textarea>` abaixo dá a este cartão um min-content de ~525px — largo demais para a
      // coluna no celular, o que fazia a página inteira rolar na horizontal.
      return <article className="min-w-0 rounded-xl border bg-white p-4" key={artifact.id}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-accent-50 px-2 py-0.5 text-[11px] font-semibold text-accent">{artifact.kind_display}</span>
          <span className={`rounded-lg px-2 py-0.5 text-[11px] font-semibold ${STATUS_BADGE[artifact.status]}`}>{artifact.status_display}</span>
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">{artifact.title}</p>
          {artifact.document && <span className="inline-flex items-center gap-1 text-xs text-slate-600"><FileText className="size-3.5" />Documento salvo</span>}
        </div>
        {/* 128px não davam conta de uma proposta ou contrato inteiro: o texto nascia num campo do
            tamanho de um comentário e só se lia rolando. `resize-y` deixa quem revisa esticar. */}
        <textarea
          className="field mt-3 min-h-64 resize-y"
          value={content}
          onChange={event => setDrafts({ ...drafts, [artifact.id]: event.target.value })}
          aria-label={`Conteúdo de ${artifact.title}`}
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-3 py-1.5 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60"
            disabled={!dirty}
            onClick={() => void patch(artifact, { content })}
          ><Save className="size-3.5" />Salvar texto</button>
          {!artifact.document && <button
            type="button"
            className="rounded-xl border px-3 py-1.5 text-sm font-semibold text-ink hover:border-accent"
            onClick={() => void saveAsDocument(artifact)}
          >Salvar como documento</button>}
          <div className="ml-auto flex flex-wrap gap-2">{NEXT[artifact.status].map(next => <button
            key={next}
            type="button"
            className="rounded-xl border px-3 py-1.5 text-sm font-semibold text-ink hover:border-accent"
            onClick={() => void patch(artifact, { status: next })}
          >Marcar como {STATUS_LABEL[next].toLowerCase()}</button>)}</div>
        </div>
      </article>;
    })}</div>
  </div>;
}
