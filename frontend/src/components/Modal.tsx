import { X } from "lucide-react";
import { type ReactNode, useRef } from "react";

import { useEscape, useFocusTrap } from "../a11y";

type Width = "md" | "3xl";

// `max-w-md` serve a um formulário curto e sufoca o resto: o detalhe da oportunidade carrega
// formulário, documentos, texto de IA e artefatos em 448px, e o rascunho da IA saía numa coluna de
// ~400px. `width="3xl"` é a saída para esses casos, sem alargar os diálogos que já cabiam.
const widths: Record<Width, string> = { md: "max-w-md", "3xl": "max-w-3xl" };

export function Modal({ title, children, onClose, width = "md" }: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  width?: Width;
}) {
  // `aria-modal` promete ao leitor de tela que o resto da página está inerte. Sem prender o `Tab`
  // e sem fechar no `Escape`, a promessa era falsa: dava para tabular para fora do diálogo sem
  // fechá-lo, e quem abriu pelo teclado não tinha como sair. O axe não pega isso (FDD 022).
  const caixa = useRef<HTMLDivElement>(null);
  useEscape(true, onClose);
  useFocusTrap(true, caixa);
  // `max-h-[90vh] overflow-y-auto` no painel: o overlay é `fixed`, então a página não rola atrás
  // dele. Sem isto, um diálogo mais alto que a viewport ficava cortado em cima **e** embaixo pelo
  // `place-items-center`, e o topo do formulário era inalcançável.
  return <div className="fixed inset-0 z-40 grid place-items-center bg-ink/45 p-4" role="dialog" aria-modal="true" aria-label={title} ref={caixa}>
    <div className={`max-h-[90vh] w-full ${widths[width]} overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl sm:p-6`}>
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        <button className="grid size-8 place-items-center rounded-lg text-slate-600 hover:bg-slate-100" aria-label="Fechar" onClick={onClose}><X className="size-4" /></button>
      </div>
      {children}
    </div>
  </div>;
}

/** Confirmação para ação destrutiva — arquivar, remover, excluir.
 *
 * Existe porque nenhum dos botões de excluir do portal pedia confirmação: um clique disparava o
 * `DELETE`, e não havia como desfazer. Reusa o `Modal` para herdar foco preso e `Escape` (FDD 022);
 * o foco começa no botão de cancelar, que é o desfecho seguro.
 */
export function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel, busy = false }: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return <Modal title={title} onClose={onCancel}>
    <div className="text-sm text-slate-600">{message}</div>
    <div className="mt-6 flex flex-wrap justify-end gap-3">
      <button type="button" className="rounded-xl border px-4 py-2.5 text-sm font-semibold text-ink hover:border-ocean" onClick={onCancel}>Cancelar</button>
      <button type="button" className="rounded-xl bg-signal px-4 py-2.5 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60" disabled={busy} onClick={onConfirm}>{busy ? "Aguarde…" : confirmLabel}</button>
    </div>
  </Modal>;
}
