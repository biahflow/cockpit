import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef, useSyncExternalStore } from "react";

import { useEscape, useFocusTrap } from "../a11y";

type Width = "md" | "3xl";

// `max-w-md` serve a um formulário curto e sufoca o resto: o detalhe da oportunidade carrega
// formulário, documentos, texto de IA e artefatos em 448px, e o rascunho da IA saía numa coluna de
// ~400px. `width="3xl"` é a saída para esses casos, sem alargar os diálogos que já cabiam.
const widths: Record<Width, string> = { md: "max-w-md", "3xl": "max-w-3xl" };

/**
 * Pilha dos diálogos abertos, em ordem de abertura.
 *
 * Existe porque um `ConfirmDialog` aberto de dentro de outro `Modal` ficava **atrás** dele e o
 * `Escape` fechava os dois. Duas causas, ambas invisíveis em qualquer teste de modal solitário:
 *
 * - os overlays são **irmãos** no contexto de empilhamento raiz e tinham o mesmo `z-40`; empate de
 *   z-index se resolve por ordem de DOM, e a página renderizava a confirmação antes do diálogo que
 *   a abriu;
 * - `useEscape` chama `stopPropagation()`, que **não** interrompe outros listeners registrados no
 *   mesmo `EventTarget` (isso seria `stopImmediatePropagation`) — e os dois estão no `document`.
 *
 * Ordenar por ordem de abertura, e não por ordem no JSX, é o que torna a correção independente de
 * onde a página escolheu colocar cada `<Modal>`. Fica fora do React porque `App.tsx` não tem
 * provider nenhum e um contexto novo seria caro demais para um contador.
 */
const pilha: symbol[] = [];
const ouvintes = new Set<() => void>();

function inscrever(aoMudar: () => void): () => void {
  ouvintes.add(aoMudar);
  return () => { ouvintes.delete(aoMudar); };
}

function empilhar(id: symbol): () => void {
  pilha.push(id);
  ouvintes.forEach(aoMudar => aoMudar());
  return () => {
    const posicao = pilha.indexOf(id);
    if (posicao !== -1) pilha.splice(posicao, 1);
    ouvintes.forEach(aoMudar => aoMudar());
  };
}

export function Modal({ title, children, onClose, width = "md" }: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  width?: Width;
}) {
  const caixa = useRef<HTMLDivElement>(null);
  const id = useRef<symbol>(undefined as unknown as symbol);
  if (id.current === undefined) id.current = Symbol("modal");

  useEffect(() => empilhar(id.current), []);
  // Snapshots primitivos: `useSyncExternalStore` compara por `Object.is`, então devolver booleano e
  // número evita o laço infinito que um objeto novo a cada leitura provocaria.
  const topo = useSyncExternalStore(inscrever, () => pilha[pilha.length - 1] === id.current);
  const profundidade = useSyncExternalStore(inscrever, () => Math.max(pilha.indexOf(id.current), 0));

  // `aria-modal` promete ao leitor de tela que o resto da página está inerte. Sem prender o `Tab`
  // e sem fechar no `Escape`, a promessa era falsa: dava para tabular para fora do diálogo sem
  // fechá-lo, e quem abriu pelo teclado não tinha como sair. O axe não pega isso (FDD 022).
  //
  // Só o diálogo do topo escuta o `Escape` — assim uma tecla fecha uma camada, e a ordem em que os
  // listeners foram registrados deixa de importar (ela é instável, porque `onClose` costuma ser uma
  // arrow recriada a cada render).
  useEscape(topo, onClose);
  // O trap segue ativo nos dois: gatá-lo em `topo` faria o cleanup do de baixo rodar o
  // `anterior?.focus()` e jogar o foco para a página atrás. Quem impede o `Tab` de alcançar a
  // camada de baixo é o `inert`, nativamente — e ele também resolve o segundo `aria-modal` visível,
  // que era inválido.
  useFocusTrap(true, caixa);

  // `zIndex` no `style` porque o Tailwind não gera classe a partir de valor calculado.
  return <div
    className="fixed inset-0 grid place-items-center bg-ink/45 p-4"
    style={{ zIndex: 40 + profundidade * 10 }}
    role="dialog"
    aria-modal="true"
    aria-label={title}
    inert={!topo}
    ref={caixa}
  >
    {/* `max-h-[90vh] overflow-y-auto` no painel: o overlay é `fixed`, então a página não rola atrás
        dele. Sem isto, um diálogo mais alto que a viewport ficava cortado em cima **e** embaixo pelo
        `place-items-center`, e o topo do formulário era inalcançável. */}
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
 * `DELETE`, e não havia como desfazer. Reusa o `Modal` para herdar foco preso, `Escape` e o
 * empilhamento (FDD 022, FDD 025) — é o único diálogo que hoje abre de dentro de outro.
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
      <button type="button" className="btn btn--secondary" onClick={onCancel}>Cancelar</button>
      <button type="button" className="btn btn--danger" disabled={busy} onClick={onConfirm}>{busy ? "Aguarde…" : confirmLabel}</button>
    </div>
  </Modal>;
}
