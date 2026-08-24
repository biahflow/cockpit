import { CheckCircle2, CircleAlert, Info, LoaderCircle, XCircle } from "lucide-react";

import { useAuth } from "../auth";

const SWATCHES = [
  ["ink", "bg-ink"],
  ["muted", "bg-muted"],
  ["line", "bg-line"],
  ["line-strong", "bg-line-strong"],
  ["canvas", "bg-canvas"],
  ["surface", "bg-surface"],
  ["surface-subtle", "bg-surface-subtle"],
  ["brand-50", "bg-brand-50"],
  ["brand-100", "bg-brand-100"],
  ["brand-200", "bg-brand-200"],
  ["brand-500", "bg-brand-500"],
  ["brand-600", "bg-brand-600"],
  ["brand-700", "bg-brand-700"],
  ["brand-900", "bg-brand-900"],
  ["danger", "bg-danger"],
  ["danger-50", "bg-danger-50"],
  ["success", "bg-success"],
  ["success-50", "bg-success-50"],
  ["warning", "bg-warning"],
  ["warning-50", "bg-warning-50"],
  ["info", "bg-info"],
  ["info-50", "bg-info-50"],
] as const;

const ESPACOS = [
  ["4", "w-1"], ["8", "w-2"], ["12", "w-3"], ["16", "w-4"],
  ["20", "w-5"], ["24", "w-6"], ["32", "w-8"], ["40", "w-10"], ["48", "w-12"],
] as const;

const RAIOS = [
  ["4 detalhe", "rounded"],
  ["8 controle", "rounded-lg"],
  ["12 cartão", "rounded-xl"],
  ["full", "rounded-full"],
] as const;

export function DesignSystemPage() {
  const { user } = useAuth();
  if (!user?.is_admin) {
    return <p className="empty-state">Sem permissão para ver o design system.</p>;
  }

  return <section className="space-y-7">
    <header className="page-head">
      <p className="eyebrow">Pulse Design System</p>
      <h1>Design system</h1>
      <p>Fundações aprovadas (ADR 0041, DAP r2). Comando calmo: clay é identidade, informação é azul e perigo é vermelho.</p>
      <a href="/configuracoes" className="back-link">Configurações</a>
    </header>

    <section className="panel">
      <div className="panel-heading"><h2>Paleta</h2></div>
      <div className="flex flex-wrap gap-3">
        {SWATCHES.map(([name, bg]) => (
          <div className="grid gap-1.5" key={name}>
            <div className={`h-14 w-20 rounded-xl border border-line ${bg}`} />
            <p className="text-xs font-medium text-ink">{name}</p>
          </div>
        ))}
      </div>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Tipo</h2></div>
      <p className="eyebrow">Operação</p>
      <p className="type-title mt-2 text-ink">Título de seção — 16/24 650</p>
      <p className="type-body mt-1 text-ink">Texto de corpo — 14/22 400.</p>
      <p className="type-label mt-1 text-muted">Label — 12/16 600.</p>
      <p className="type-meta mt-1 text-muted">Meta — 11/16 500.</p>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Espaço</h2></div>
      <div className="flex flex-wrap items-end gap-3">
        {ESPACOS.map(([name, cls]) => (
          <div className="grid justify-items-center gap-1" key={name}>
            <div className={`h-8 bg-ink ${cls}`} />
            <p className="text-xs text-muted">{name}</p>
          </div>
        ))}
      </div>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Raios</h2></div>
      <div className="flex flex-wrap items-center gap-3">
        {RAIOS.map(([name, cls]) => (
          <div className="grid justify-items-center gap-1.5" key={name}>
            <div className={`size-14 border border-line bg-white ${cls}`} />
            <p className="text-xs text-muted">{name}</p>
          </div>
        ))}
      </div>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Superfície</h2></div>
      <div className="flex flex-wrap gap-4">
        <div className="panel max-w-xs"><p className="text-sm text-muted">Card: 1 px, sombra contida.</p></div>
        <div className="max-w-xs rounded-xl bg-surface p-3 shadow-raised"><p className="text-sm text-muted">Raised: ação contextual.</p></div>
        <div className="max-w-xs rounded-xl bg-surface p-3 shadow-pop"><p className="text-sm text-muted">Popover: sobreposição.</p></div>
      </div>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Botões</h2></div>
      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn" data-testid="ds-primary">Primário</button>
        <button type="button" className="btn" data-testid="ds-primary-disabled" disabled>Primário desligado</button>
        <button type="button" className="btn btn--secondary" data-testid="ds-secondary">Secundário</button>
        <button type="button" className="btn btn--secondary" data-testid="ds-secondary-disabled" disabled>Secundário desligado</button>
        <button type="button" className="btn btn--danger">Perigo</button>
        <button type="button" className="btn btn--danger" disabled>Perigo desligado</button>
      </div>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Selos</h2></div>
      <div className="flex flex-wrap gap-2">
        <span className="state state--0"><Info className="size-3" aria-hidden="true" />Informativo</span>
        <span className="state state--1"><CheckCircle2 className="size-3" aria-hidden="true" />Concluído</span>
        <span className="state state--2"><CircleAlert className="size-3" aria-hidden="true" />Atenção</span>
        <span className="state state--3"><XCircle className="size-3" aria-hidden="true" />Falha</span>
        <span className="state state--off">Arquivado</span>
      </div>
    </section>

    <section className="panel space-y-3">
      <div className="panel-heading"><h2>Alertas</h2></div>
      <p role="alert" className="alert--error">Não foi possível concluir a operação.</p>
      <p role="status" className="alert--ok">Alteração salva.</p>
    </section>

    <section className="panel space-y-3">
      <div className="panel-heading"><h2>Vazio e carregamento</h2></div>
      <p className="empty-state">Nada para mostrar neste recorte.</p>
      <p className="flex items-center gap-2 text-sm text-muted">
        <LoaderCircle className="size-5 animate-spin" aria-label="Carregando" />
      </p>
    </section>

    <section className="panel">
      <div className="panel-heading"><h2>Campo</h2></div>
      <div className="form-grid">
        <label className="form-label">Nome
          <input className="field" defaultValue="Portal operacional" />
        </label>
        <label className="form-label">Título
          <input className="field border-danger" defaultValue="" aria-invalid="true" aria-describedby="ds-erro-titulo" />
          <span id="ds-erro-titulo" className="text-sm font-normal text-danger">O título é obrigatório.</span>
        </label>
      </div>
    </section>
  </section>;
}
