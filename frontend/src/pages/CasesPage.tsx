import { ArrowRight, BadgeCheck, Save, ShieldCheck, Trophy } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import type { Case, CaseMetric, CaseStatus, KpiUnit, Vertical } from "../types";

const statusLabel: Record<CaseStatus, string> = { draft: "Rascunho", review: "Em revisão", published: "Publicado" };
const areas = ["Comercial", "Financeiro", "RH", "Jurídico", "Atendimento"];

/** `"48"` + `"hours"` vira `"48h"`. Sem unidade, o número sai sozinho. */
function numero(valor: string | null, unidade: KpiUnit): string {
  if (valor === null) return "—";
  const limpo = valor.replace(/\.00$/, "");
  if (unidade === "currency") return `R$ ${limpo}`;
  const sufixo = { percent: "%", hours: "h", minutes: "min", count: "", "": "" }[unidade] ?? "";
  return `${limpo}${sufixo}`;
}

function healthTone(level: string): string {
  if (level === "saudável") return "state--1";
  if (level === "atenção") return "state--2";
  return "state--3";
}

export function CasesPage() {
  const { user } = useAuth();
  const isAdmin = Boolean(user?.is_admin);
  const [cases, setCases] = useState<Case[]>([]);
  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [verticalFilter, setVerticalFilter] = useState("");
  const [areaFilter, setAreaFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [edit, setEdit] = useState<Record<number, { title: string; summary: string }>>({});
  const [consenting, setConsenting] = useState<Case | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setLoading] = useState(true);

  // A vertical filtra no servidor (`?vertical=`), porque é chave estrangeira e a lista pode
  // crescer. Área e blueprint filtram aqui: eles vivem dentro de `metrics`, que já veio junto —
  // pedir ao backend para consultar dentro do JSON custaria uma rota especial para poupar um
  // `filter` sobre dados que a tela tem na mão.
  const load = useCallback(() => {
    const query = verticalFilter ? `?vertical=${verticalFilter}` : "";
    return api<Case[]>(`/cases/${query}`)
      .then(setCases)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, [verticalFilter]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void api<Vertical[]>("/verticals/").then(setVerticals).catch(() => setVerticals([])); }, []);

  const visible = cases.filter(item =>
    (!statusFilter || item.status === statusFilter)
    && (!areaFilter || item.metrics.some(metric => metric.area === areaFilter)));

  function draftFor(item: Case) {
    return edit[item.id] ?? { title: item.title, summary: item.summary };
  }
  function setDraft(item: Case, patch: Partial<{ title: string; summary: string }>) {
    setEdit(prev => ({ ...prev, [item.id]: { ...draftFor(item), ...patch } }));
  }

  async function saveCase(event: FormEvent<HTMLFormElement>, item: Case) {
    event.preventDefault(); setError("");
    try { await api(`/cases/${item.id}/`, { method: "PATCH", body: JSON.stringify(draftFor(item)) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function setAnonymized(item: Case, anonymized: boolean) {
    setError("");
    try { await api(`/cases/${item.id}/`, { method: "PATCH", body: JSON.stringify({ anonymized }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function recordConsent() {
    if (!consenting) return;
    setError(""); setBusy(true);
    try { await api(`/cases/${consenting.id}/record-consent/`, { method: "POST" }); setConsenting(null); await load(); }
    catch (cause) { setConsenting(null); setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function moveTo(item: Case, status: CaseStatus) {
    setError("");
    try { await api(`/cases/${item.id}/`, { method: "PATCH", body: JSON.stringify({ status }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }

  if (isLoading) return <p className="text-sm text-slate-600">Carregando cases…</p>;

  return <section className="space-y-7">
    {consenting && <ConfirmDialog
      title="Registrar consentimento do cliente"
      message={<>Confirme que <strong className="text-ink">{consenting.account_name || "o cliente"}</strong> autorizou o uso deste resultado como case. O registro guarda quem confirmou e quando — é o que sustenta a publicação depois. Para usar o número sem citar a marca, marque também <strong className="text-ink">Anonimizar</strong>: são duas autorizações diferentes.</>}
      confirmLabel="Registrar consentimento" busy={busy}
      onCancel={() => setConsenting(null)} onConfirm={() => void recordConsent()}
    />}

    <header className="page-head">
      <p className="eyebrow">Metodologia</p>
      <h1>Cases</h1>
      <p>O que cada entrega provou, com número congelado na data da conclusão. É daqui que a proposta gerada pela IA tira prova em vez de promessa.</p>
    </header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <div className="toolbar">
      <label className="form-label">Vertical<select className="field w-48" value={verticalFilter} onChange={event => setVerticalFilter(event.target.value)}><option value="">Todas</option>{verticals.map(vertical => <option key={vertical.id} value={vertical.id}>{vertical.name}</option>)}</select></label>
      <label className="form-label">Área<select className="field w-44" value={areaFilter} onChange={event => setAreaFilter(event.target.value)}><option value="">Todas</option>{areas.map(area => <option key={area} value={area}>{area}</option>)}</select></label>
      <label className="form-label">Estado<select className="field w-44" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">Todos</option>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>

    {visible.length ? <div className="grid gap-5">{visible.map(item => <article className="panel panel--flush" key={item.id}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-slate-50/60 px-5 py-4 sm:px-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="metric-icon"><Trophy className="size-4" /></span>
            <h2 className="font-semibold text-ink">{item.title}</h2>
            <span className="state state--off">{item.status_display}</span>
            {item.anonymized && <span className="state state--0">Anonimizado</span>}
          </div>
          <p className="mt-1 text-sm text-slate-600">{item.vertical_name || "Sem vertical"} · concluído em {new Date(item.created_at).toLocaleDateString("pt-BR")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`state ${healthTone(item.health_snapshot.level)}`}>Saúde {item.health_snapshot.score}/100</span>
          {/* O ROI é interno: aparece para quem opera o portal e nunca no texto que vai ao cliente. */}
          {item.roi_snapshot.roi !== null && <span className="state state--off">ROI {(item.roi_snapshot.roi * 100).toFixed(0)}%</span>}
        </div>
      </div>

      <div className="px-5 py-4 sm:px-6">
        {item.metrics.length ? <table className="w-full text-sm">
          <caption className="sr-only">Resultados congelados de {item.title}</caption>
          <thead><tr className="section-label text-left">
            <th scope="col" className="pb-2">Funcionário Digital</th><th scope="col" className="pb-2">KPI</th>
            <th scope="col" className="pb-2">Antes</th><th scope="col" className="pb-2">Depois</th>
          </tr></thead>
          <tbody className="divide-y">{item.metrics.map((metric: CaseMetric) => <tr key={metric.employee_id}>
            <td className="py-2 pr-3 font-medium text-ink">{metric.name}<span className="block text-xs font-normal text-slate-600">{metric.area}</span></td>
            <td className="py-2 pr-3 text-slate-700">{metric.kpi_label || "—"}<span className="block text-xs text-slate-600">{metric.kpi_direction === "down" ? "menor é melhor" : "maior é melhor"}</span></td>
            {/* Sem base registrada a célula **diz isso**. Um "0" ali seria um número que ninguém
                mediu, apresentado como se tivesse sido. */}
            <td className="py-2 pr-3 text-slate-700">{metric.has_baseline ? numero(metric.baseline, metric.kpi_unit) : <em className="text-slate-600">sem base registrada</em>}</td>
            <td className="py-2 font-semibold text-ink"><span className="inline-flex items-center gap-1.5"><ArrowRight className="size-3.5 text-accent" aria-hidden />{numero(metric.current, metric.kpi_unit)}</span></td>
          </tr>)}</tbody>
        </table> : <p className="empty-state">Este projeto foi concluído sem Funcionário Digital no roster, então o case não tem antes e depois — só saúde e ROI.</p>}

        {isAdmin ? <form className="mt-5 grid gap-3 border-t pt-4" onSubmit={event => void saveCase(event, item)}>
          <label className="form-label">Título<input className="field" value={draftFor(item).title} onChange={event => setDraft(item, { title: event.target.value })} aria-label={`Título do case ${item.id}`} /></label>
          <label className="form-label">Resumo<textarea className="field min-h-20" value={draftFor(item).summary} onChange={event => setDraft(item, { summary: event.target.value })} aria-label={`Resumo do case ${item.id}`} placeholder="O que esta entrega provou, em uma ou duas frases. Vai para a proposta." /></label>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="size-4 rounded border-slate-300 text-accent" checked={item.anonymized} onChange={event => void setAnonymized(item, event.target.checked)} aria-label={`Anonimizar o case ${item.id}`} />Anonimizar (publicar sem citar a marca)</label>
            <button className="btn" type="submit"><Save className="size-4" />Salvar texto</button>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3 rounded-xl bg-slate-50/60 p-3">
            {item.account_consent
              ? <span className="back-link"><BadgeCheck className="size-4" />Consentimento registrado</span>
              : <button type="button" className="btn btn--secondary" onClick={() => setConsenting(item)}><ShieldCheck className="size-4" />Registrar consentimento</button>}
            {item.status !== "published" && <>
              {item.status === "draft" && <button type="button" className="btn btn--secondary" onClick={() => void moveTo(item, "review")}>Enviar para revisão</button>}
              {item.status === "review" && <button type="button" className="btn btn--secondary" onClick={() => void moveTo(item, "draft")}>Voltar para rascunho</button>}
              {/* Desabilitado **com o motivo à vista**: um botão que some deixa quem revisa
                  procurando o que falta, e o que falta é uma conversa com o cliente. */}
              <button type="button" className="btn" disabled={!item.account_consent} onClick={() => void moveTo(item, "published")}>Publicar</button>
              {!item.account_consent && <span className="text-xs text-slate-600">Publicar exige o consentimento do cliente — anonimizar não substitui.</span>}
            </>}
          </div>
        </form> : item.summary && <p className="mt-4 border-t pt-4 text-sm text-slate-600">{item.summary}</p>}
      </div>
    </article>)}</div> : <p className="empty-state">Nenhum case ainda. Eles nascem sozinhos quando um projeto é marcado como concluído — com a saúde e o ROI congelados naquele instante.</p>}
  </section>;
}
