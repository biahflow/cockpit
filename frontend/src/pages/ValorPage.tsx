import { ArrowLeft, Coins } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, getKpi, getMeasurement, listValueLedgerEntries } from "../api";
import { useAuth } from "../auth";
import { mensagemDeFalha } from "../erros";
import type { Account, Engagement, KPI, ValueLedgerEntry, ValueLedgerStatus } from "../types";

/**
 * O **Value Ledger** da conta — `/contas/:id/valor`.
 *
 * Governada pelo DAP `docs/design/dap-prove-e-valor-r1/`, revisão 1, decisão **D1**: tela própria,
 * simétrica a `/contas/:id/priorizacao`. Uma lista financeira com fluxo de aprovação
 * (`status`/`approved_by`/`attribution_method`) é auditável demais para caber como nona seção de
 * uma página de cadastro. **Nenhum link novo no menu lateral**: valor é sempre *de uma conta*, e
 * um item de menu que abre pedindo "qual conta?" é um beco.
 *
 * **Pendente não entra no total, e a lacuna é `—`, nunca `0`.** Só valor aprovado é valor — é o que
 * `ValueLedgerEntry.status` existe para distinguir —, e uma entrada sem montante apurado mostra o
 * traço: zero afirmaria que se apurou e deu zero.
 *
 * O ledger consolidado entre contas fica **reservado** no DAP: o total da casa é tela de
 * Indicadores, e tem dono diferente.
 */

/** Variante, nunca a cor (ADR 0026). `draft` é o neutro — rascunho não é aviso. */
const LEDGER_VARIANT: Record<ValueLedgerStatus, string> = {
  draft: "state--off", pending: "state--2", approved: "state--1",
};

const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

/** O montante. **`null` é "não apurado" e sai como `—`**, nunca `R$ 0`. */
const montante = (valor: string | null) => valor === null || valor === "" ? "—" : moeda.format(Number(valor));

const mesDe = (iso: string) => {
  const data = new Date(`${iso}T12:00:00`);
  return `${data.toLocaleDateString("pt-BR", { month: "long" })}/${data.getFullYear()}`;
};

/** A janela da entrada. Um mês só não vira intervalo: "julho/2026 → julho/2026" não diz mais nada. */
const janelaDe = (entrada: ValueLedgerEntry) => {
  const inicio = mesDe(entrada.period_start); const fim = mesDe(entrada.period_end);
  return inicio === fim ? inicio : `${inicio} → ${fim}`;
};

export function ValorPage({ accountId }: { accountId: number }) {
  const { user } = useAuth();
  const [account, setAccount] = useState<Account>();
  const [entradas, setEntradas] = useState<ValueLedgerEntry[]>([]);
  /** Medição → KPI, que é como a linha cita o **Outcome de origem pelo nome do indicador**. */
  const [kpiDaMedicao, setKpiDaMedicao] = useState<Record<number, KPI>>({});
  const [error, setError] = useState("");
  const [semAcesso, setSemAcesso] = useState(false);

  /**
   * Encadeado em `.then()` e não `async//await` no corpo do efeito, no molde de `PriorizacaoPage`:
   * um `setState` alcançável sincronicamente de dentro do efeito dispara renderização em cascata,
   * e é o que o `react-hooks/set-state-in-effect` cobra.
   */
  const load = useCallback(() => Promise.all([
    // A **rota** da conta continua sendo `/clients/` — ela morre na `/api/v2/`
    // (`docs/ontology/aliases.md`). As demais já nascem com o nome canônico.
    api<Account>(`/clients/${accountId}/`),
    api<Engagement[]>(`/engagements/?account=${accountId}`),
  ]).then(async ([loadedAccount, engagements]) => {
    // Uma chamada por mandato, e não uma só: a entrada pende do `Engagement` (valor é do mandato,
    // não do projeto) e a rota não expõe filtro por conta.
    const listas = await Promise.all(engagements.map(engagement => listValueLedgerEntries(engagement.id)));
    const todas = listas.flat()
      .sort((a, b) => b.period_end.localeCompare(a.period_end) || b.id - a.id);
    // O nome do KPI chega em dois saltos — entrada → medição → indicador —, deduplicados: uma
    // entrada de valor sem o indicador que a sustenta é um número sem procedência, que é
    // exatamente o que `attribution_method` existe para impedir.
    const medicoes = await Promise.all(
      [...new Set(todas.map(entrada => entrada.outcome_measurement))].map(getMeasurement));
    const kpis = await Promise.all([...new Set(medicoes.map(medicao => medicao.kpi))].map(getKpi));
    const porId = new Map(kpis.map(kpi => [kpi.id, kpi]));
    setAccount(loadedAccount); setEntradas(todas); setSemAcesso(false);
    setKpiDaMedicao(Object.fromEntries(medicoes.flatMap(medicao => {
      const kpi = porId.get(medicao.kpi);
      return kpi ? [[medicao.id, kpi] as const] : [];
    })));
  }).catch((cause: unknown) => {
    // O recorte da Entrega (RFC 0003) chega como 404 na conta: quem não participa de projeto
    // nenhum dela não a alcança pela rota. Só quem é da Entrega vê a frase — para admin e Vendas
    // um 404 significa mesmo "esta conta não existe".
    const status = (cause as { status?: number }).status;
    if (user?.role === "delivery" && (status === 403 || status === 404)) { setSemAcesso(true); return; }
    setError(mensagemDeFalha(cause));
  }), [accountId, user?.role]);
  useEffect(() => { void load(); }, [load]);

  if (semAcesso) return <section className="space-y-7">
    <a href={`/contas/${accountId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para a conta</a>
    <section className="panel"><p className="empty-state">Você não participa de nenhum projeto desta conta.</p></section>
  </section>;
  if (error && !account) return <div role="alert" className="alert--error">{error}</div>;
  // O mesmo esqueleto de `PriorizacaoPage` — não um estado de carregamento novo.
  if (!account) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  const aprovadas = entradas.filter(entrada => entrada.status === "approved");
  const total = aprovadas.reduce((soma, entrada) => soma + (entrada.amount === null ? 0 : Number(entrada.amount)), 0);
  const foraDoTotal = entradas.filter(entrada => entrada.status !== "approved");
  const somaForaDoTotal = foraDoTotal.reduce((soma, entrada) => soma + (entrada.amount === null ? 0 : Number(entrada.amount)), 0);
  // **A entrada aprovada sem montante também fica fora, e o rodapé precisa dizer isso.** Ela é o
  // caso do `value_type: capacity`, que carrega `quantity` e não `amount`: somá-la como zero é
  // aritmética correta e leitura errada — o total afirmaria ter contado tudo que foi aprovado.
  // É a mesma distinção nulo≠zero que a Fase 5 inteira existe para preservar, do lado de quem lê.
  const aprovadasSemMontante = aprovadas.filter(entrada => entrada.amount === null);

  const notasDoTotal = [
    foraDoTotal.length
      ? `${foraDoTotal.length} ${foraDoTotal.length === 1 ? "entrada não aprovada" : "entradas não aprovadas"} de ${moeda.format(somaForaDoTotal)} ${foraDoTotal.length === 1 ? "não somada" : "não somadas"}`
      : null,
    aprovadasSemMontante.length
      ? `${aprovadasSemMontante.length} ${aprovadasSemMontante.length === 1 ? "aprovada sem montante" : "aprovadas sem montante"} — valor em quantidade, não em dinheiro`
      : null,
  ].filter(Boolean);

  return <section className="space-y-7">
    <a href={`/contas/${accountId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para {account.name}</a>
    <header className="page-head">
      {/* "VALUE" é o termo canônico, em inglês, com o texto ao redor em pt-BR — a mesma regra do
          mapa de linguagem §1 que a Decisão A do DAP de Engagements já registrou. */}
      <p className="eyebrow">VALUE</p>
      <h1>Valor gerado — {account.name}</h1>
      <p>Cada entrada aponta para um Outcome medido no PROVE. Pendente não conta para o total — só valor aprovado é valor.</p>
    </header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    <div className="metric-card max-w-xs">
      <span>Total aprovado</span>
      <strong>{moeda.format(total)}</strong>
      <span>{notasDoTotal.length ? `${notasDoTotal.join(" · ")} — fora deste total.` : "Nenhuma entrada fora do total."}</span>
    </div>

    <section className="panel panel--flush">
      {entradas.length ? <div className="panel-rows">{entradas.map(entrada => {
        const kpi = kpiDaMedicao[entrada.outcome_measurement];
        return <div className="row" key={entrada.id}>
          <span className="metric-icon"><Coins className="size-4" /></span>
          <div className="row-main">
            <strong>{entrada.value_type_display}</strong>
            <span>{montante(entrada.amount)} · {janelaDe(entrada)} · atribuição: {entrada.attribution_method}</span>
            {/* O Outcome de origem **pelo nome do KPI**: é ele que diz de qual indicador este
                dinheiro saiu, e sem ele a linha é um valor que ninguém consegue conferir. */}
            <span>Outcome de origem: {kpi ? kpi.name : "—"}</span>
          </div>
          {/* Pílula e link fora do `.row-main`: a primitiva sobrescreve display e cor de qualquer
              `span`/`strong` aninhado nela; `.row-meta` lhes reserva a linha própria. */}
          <div className="row-meta">
            <span className={`state ${LEDGER_VARIANT[entrada.status]}`}>{entrada.status_display}</span>
            {entrada.project !== null && <a className="back-link ml-auto text-xs" href={`/projetos/${entrada.project}#prove`}>Ver no PROVE</a>}
          </div>
        </div>;
      })}</div> : <div className="p-5 sm:p-6"><p className="empty-state">Nenhum valor registrado. Uma entrada de valor aponta para um Outcome medido.</p></div>}
    </section>
  </section>;
}
