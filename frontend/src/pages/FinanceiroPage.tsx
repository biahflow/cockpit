import { AlertTriangle, Ban, CheckCircle2, ExternalLink, HandCoins, Receipt, Send, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import type { Account, Invoice, InvoiceStatus, InvoiceSummary } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const statusLabel: Record<InvoiceStatus, string> = {
  draft: "Rascunho", issued: "Emitida", paid: "Paga",
  overdue: "Vencida", renegotiated: "Renegociada", cancelled: "Cancelada",
};

// O `T12:00:00` não é enfeite: uma data pura vira meia-noite UTC e volta um dia atrás em
// `America/Sao_Paulo`. Num vencimento, um dia é a diferença entre "vence amanhã" e "venceu".
const formatDate = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR");

function statusTone(invoice: Invoice): string {
  if (invoice.status === "paid") return "state--1";
  if (invoice.status === "overdue" || invoice.is_overdue) return "state--3";
  if (invoice.status === "cancelled" || invoice.status === "renegotiated") return "state--off";
  if (invoice.status === "issued") return "state--2";
  return "state--off";
}

/** Por que o botão Emitir está desabilitado — ou `""` quando não está. */
function porQueNaoEmite(invoice: Invoice): string {
  if (invoice.status !== "draft") return "Só rascunho se emite.";
  if (Number(invoice.amount) <= 0) return "Uma fatura de valor zero não se emite.";
  return "";
}

const vazio = { account: "", amount: "", due_date: "", description: "" };

export function FinanceiroPage() {
  const { user } = useAuth();
  const isAdmin = Boolean(user?.is_admin);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<InvoiceSummary | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [form, setForm] = useState(vazio);
  const [cancelling, setCancelling] = useState<Invoice | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [discarding, setDiscarding] = useState<Invoice | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setLoading] = useState(true);

  const load = useCallback(() => {
    const query = statusFilter ? `?status=${statusFilter}` : "";
    return Promise.all([
      api<Invoice[]>(`/invoices/${query}`).then(setInvoices),
      api<InvoiceSummary>("/invoices/summary/").then(setSummary),
    ])
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void api<Account[]>("/accounts/").then(setAccounts).catch(() => setAccounts([])); }, []);

  async function acao(invoice: Invoice, rota: string, body?: unknown) {
    setError(""); setNotice(""); setBusy(true);
    try {
      await api(`/invoices/${invoice.id}/${rota}/`, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      await load();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  async function criar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setNotice(""); setBusy(true);
    try {
      await api("/invoices/", { method: "POST", body: JSON.stringify(form) });
      setForm(vazio); setNotice("Fatura criada em rascunho. Emitir é um passo à parte.");
      await load();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  async function cancelar() {
    if (!cancelling) return;
    const alvo = cancelling;
    setCancelling(null);
    await acao(alvo, "cancel", { reason: cancelReason });
    setCancelReason("");
  }

  async function descartar() {
    if (!discarding) return;
    const alvo = discarding;
    setDiscarding(null); setError(""); setBusy(true);
    try { await api(`/invoices/${alvo.id}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  if (isLoading) return <p className="text-sm text-slate-600">Carregando faturas…</p>;

  const faixas = [
    { key: "open", label: "Em aberto", value: summary?.open, count: summary?.open_count, tone: "text-ink" },
    { key: "overdue", label: "Vencido", value: summary?.overdue, count: summary?.overdue_count, tone: "text-danger" },
    { key: "paid", label: "Recebido", value: summary?.paid, count: summary?.paid_count, tone: "text-emerald-800" },
  ];

  return <section className="space-y-7">
    {cancelling && <ConfirmDialog
      title="Cancelar fatura"
      message={<>A fatura <strong className="text-ink">{cancelling.number || "sem número"}</strong> não será apagada — cancelar é a saída, e o registro fica. Diga por quê: recuar sem motivo registrado é como um recebível estraga sem ninguém ver.<textarea className="field mt-3" rows={3} aria-label="Motivo do cancelamento" value={cancelReason} onChange={event => setCancelReason(event.target.value)} /></>}
      confirmLabel="Cancelar fatura" busy={busy}
      onCancel={() => { setCancelling(null); setCancelReason(""); }} onConfirm={() => void cancelar()}
    />}
    {discarding && <ConfirmDialog
      title="Descartar rascunho"
      message={<>Este rascunho nunca foi cobrado e será apagado de vez. Fatura <strong className="text-ink">emitida</strong> não tem este caminho — só cancelamento.</>}
      confirmLabel="Descartar" busy={busy}
      onCancel={() => setDiscarding(null)} onConfirm={() => void descartar()}
    />}

    <header className="page-head">
      <p className="eyebrow">Financeiro</p>
      <h1>Contas a receber</h1>
      <p>Quem deve o quê, e desde quando. Antes desta tela a inadimplência era imensurável — não havia data de vencimento nem de pagamento em lugar nenhum do portal.</p>
    </header>

    {/* O razão aponta para a decisão (FDD 036). Aqui está quem deve o quê; o que dizer a quem, e
        se dizer, é outro trabalho — e por isso é outra tela. */}
    <a href="/cobranca" className="btn btn--secondary"><HandCoins className="size-4" />Decidir o próximo passo em Cobrança</a>

    {error && <p role="alert" className="alert--error">{error}</p>}
    {notice && <p role="status" className="rounded-xl bg-accent-50/60 p-3 text-sm text-accent">{notice}</p>}

    <div className="grid gap-4 sm:grid-cols-3">
      {faixas.map(faixa => <article key={faixa.key} className="panel">
        <p className="text-sm font-medium text-slate-600">{faixa.label}</p>
        <p className={`mt-1 text-2xl font-semibold ${faixa.tone}`}>{money.format(Number(faixa.value ?? 0))}</p>
        <p className="mt-1 text-xs text-slate-600">{faixa.count ?? 0} fatura(s)</p>
      </article>)}
    </div>

    {isAdmin && <form onSubmit={event => void criar(event)} className="panel grid gap-4 sm:p-6">
      <h2 className="font-semibold text-ink">Nova fatura</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="form-label">Conta
          <select required className="field" value={form.account} onChange={event => setForm({ ...form, account: event.target.value })}>
            <option value="">Selecione</option>
            {accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select>
        </label>
        <label className="form-label">Valor (R$)
          <input required type="number" step="0.01" min="0" className="field" value={form.amount} onChange={event => setForm({ ...form, amount: event.target.value })} />
        </label>
        <label className="form-label">Vencimento
          <input required type="date" className="field" value={form.due_date} onChange={event => setForm({ ...form, due_date: event.target.value })} />
        </label>
        <label className="form-label">Descrição
          <input className="field" value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} />
        </label>
      </div>
      <div>
        <button type="submit" disabled={busy} className="btn">
          <Receipt className="size-4" />{busy ? "Salvando…" : "Criar rascunho"}
        </button>
      </div>
    </form>}

    <div className="toolbar">
      <label className="form-label">Estado
        <select className="field w-48" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
          <option value="">Todos</option>
          {Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
    </div>

    {invoices.length ? <div className="grid gap-4">{invoices.map(invoice => {
      const motivo = porQueNaoEmite(invoice);
      return <article key={invoice.id} className="panel panel--flush">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-slate-50/60 px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="metric-icon"><Receipt className="size-4" /></span>
              <h2 className="font-semibold text-ink">{invoice.number || "Rascunho"}</h2>
              <span className={`state ${statusTone(invoice)}`}>{invoice.status_display}</span>
              {invoice.is_overdue && invoice.status !== "overdue" && <span className="state state--3"><AlertTriangle className="size-3" />Venceu</span>}
            </div>
            <p className="mt-1 text-sm text-slate-600">{invoice.account_name}{invoice.description && ` — ${invoice.description}`}</p>
          </div>
          <div className="text-right">
            <p className="text-lg font-semibold text-ink">{money.format(Number(invoice.amount))}</p>
            <p className="text-xs text-slate-600">Vence {formatDate(invoice.due_date)}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 px-5 py-4 sm:px-6">
          {invoice.paid_at && <p className="mr-auto text-sm text-emerald-800">Recebida em {new Date(invoice.paid_at).toLocaleDateString("pt-BR")}{invoice.method_display && ` · ${invoice.method_display}`}</p>}
          {invoice.cancel_reason && <p className="mr-auto text-sm text-slate-600">Cancelada: {invoice.cancel_reason}</p>}
          {invoice.payment_url && <a href={invoice.payment_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold text-accent hover:bg-canvas">
            <ExternalLink className="size-4" />Link de pagamento
          </a>}

          {isAdmin && invoice.status === "draft" && <>
            {/* Desabilitado **com o motivo à vista**, e não escondido: botão que some deixa quem
                usa procurando o que falta. Mesma escolha da tela de Cases (FDD 027). */}
            <button type="button" disabled={busy || Boolean(motivo)} title={motivo} onClick={() => void acao(invoice, "issue")}
              className="btn">
              <Send className="size-4" />Emitir
            </button>
            {motivo && <span className="text-xs text-slate-600">{motivo}</span>}
            <button type="button" onClick={() => setDiscarding(invoice)} className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-canvas">
              <Trash2 className="size-4" />Descartar
            </button>
          </>}

          {isAdmin && (invoice.status === "issued" || invoice.status === "overdue") && <>
            <button type="button" disabled={busy} onClick={() => void acao(invoice, "mark-paid", { method: "pix" })}
              className="btn">
              <CheckCircle2 className="size-4" />Marcar como paga
            </button>
            <button type="button" onClick={() => setCancelling(invoice)} className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-canvas">
              <Ban className="size-4" />Cancelar
            </button>
          </>}
        </div>
      </article>;
    })}</div> : <p className="empty-state">Nenhuma fatura por aqui. As faturas de um projeto nascem em rascunho na conversão da oportunidade, pelo nível de produto vendido.</p>}

    <p className="text-xs text-slate-600">Sem gateway de pagamento configurado, <strong className="text-slate-700">marcar como paga</strong> é o único caminho de baixa — e é um caminho completo. Com o gateway ligado, o pagamento registrado no provedor chega por webhook e fecha a fatura sozinho, com a data dele.</p>
  </section>;
}
