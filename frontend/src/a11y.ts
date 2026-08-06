/**
 * Teclado em coisas que abrem por cima: `Escape` para fechar e foco preso no diálogo.
 *
 * A FDD 022 deixou isto de fora e explicou por quê: **o axe não pega**. Ordem de foco e "dá para
 * sair daqui sem mouse?" dependem de interação, e uma varredura estática de uma página parada não
 * enxerga nenhuma das duas. Foi a mesma lição do indicador de foco — o gate passava e o portal
 * estava quebrado.
 *
 * Os dois casos do portal são diferentes e por isso são dois hooks:
 *
 * - **Menu que abre por cima** (sino de notificações, menu do usuário): fechava só por clique num
 *   overlay. Quem abriu com `Enter` não tinha como fechar — precisa de `Escape`, e o foco volta
 *   para o botão que abriu, senão a pessoa é despejada no início da página.
 * - **Diálogo** (`role="dialog" aria-modal="true"`): além do `Escape`, o foco não pode escapar
 *   para trás dele. `aria-modal` **promete** ao leitor de tela que o resto está inerte; sem prender
 *   o `Tab`, a promessa é falsa e a navegação por teclado sai do diálogo sem fechá-lo.
 */

import { useEffect, type RefObject } from "react";

/** Seletor de tudo que recebe foco por `Tab`. `[hidden]` e `disabled` já ficam de fora. */
const FOCALIZAVEL =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** `Escape` fecha, e o foco volta para quem abriu. */
export function useEscape(ativo: boolean, aoFechar: () => void, retornarPara?: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    if (!ativo) return;
    const naTecla = (evento: KeyboardEvent) => {
      if (evento.key !== "Escape") return;
      evento.stopPropagation();
      aoFechar();
      retornarPara?.current?.focus();
    };
    document.addEventListener("keydown", naTecla);
    return () => document.removeEventListener("keydown", naTecla);
  }, [ativo, aoFechar, retornarPara]);
}

/**
 * Prende o `Tab` dentro do contêiner e devolve o foco ao fechar.
 *
 * O foco inicial vai para o primeiro focalizável — e não para o contêiner — porque quem usa leitor
 * de tela espera cair no primeiro controle acionável, não num `div`.
 */
export function useFocusTrap(ativo: boolean, ref: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    if (!ativo || !ref.current) return;
    const container = ref.current;
    const anterior = document.activeElement as HTMLElement | null;
    const focalizaveis = () => [...container.querySelectorAll<HTMLElement>(FOCALIZAVEL)];

    focalizaveis()[0]?.focus();

    const naTecla = (evento: KeyboardEvent) => {
      if (evento.key !== "Tab") return;
      const itens = focalizaveis();
      if (itens.length === 0) return;
      const primeiro = itens[0];
      const ultimo = itens[itens.length - 1];
      // O ciclo é manual porque o navegador não sabe que este `div` é modal: `aria-modal` fala com
      // a tecnologia assistiva, não com a ordem de tabulação.
      if (evento.shiftKey && document.activeElement === primeiro) {
        evento.preventDefault();
        ultimo.focus();
      } else if (!evento.shiftKey && document.activeElement === ultimo) {
        evento.preventDefault();
        primeiro.focus();
      }
    };

    document.addEventListener("keydown", naTecla);
    return () => {
      document.removeEventListener("keydown", naTecla);
      anterior?.focus();
    };
  }, [ativo, ref]);
}
