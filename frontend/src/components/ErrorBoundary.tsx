import { RefreshCw, TriangleAlert } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { getLastRequestId, reportError } from "../observability";

// Um erro de render no React desmonta a árvore inteira: sem isto, o que o usuário vê é a tela
// branca — e ninguém do outro lado fica sabendo. Aqui ele vira uma mensagem com o **request-id**
// da última chamada, que é o que permite achar a requisição no log do servidor (FDD 020).
//
// Precisa ser classe: `componentDidCatch` não tem equivalente em hook.

type Props = { children: ReactNode };
type State = { erro: Error | null; requestId: string };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { erro: null, requestId: "" };

  static getDerivedStateFromError(erro: Error): Partial<State> {
    return { erro, requestId: getLastRequestId() };
  }

  componentDidCatch(erro: Error, info: ErrorInfo): void {
    reportError(erro, { componentStack: info.componentStack, origem: "ErrorBoundary" });
  }

  render(): ReactNode {
    const { erro, requestId } = this.state;
    if (!erro) return this.props.children;

    // `data-erro-de-render` é a âncora de que o e2e depende para reprovar uma tela que estourou
    // (`e2e/fixtures.ts`). Precisa ser atributo e não o texto do `h1`: o `h1` é copy, e foi
    // justamente por confiar nele que a matriz passou a medir este cartão achando que media a
    // tela. Renomeá-lo desliga a trava — por isso há teste travando o nome.
    return <main data-erro-de-render className="grid min-h-screen place-items-center bg-canvas px-5 py-10">
      <div className="w-full max-w-lg rounded-3xl border bg-white p-7 shadow-xl shadow-ink/5 sm:p-9">
        <span className="grid size-11 place-items-center rounded-2xl bg-red-50 text-danger"><TriangleAlert className="size-5" /></span>
        <div className="page-head mt-6"><p className="eyebrow">Algo saiu do lugar</p>
        <h1>Esta tela não conseguiu carregar</h1>
        <p className="max-w-none">O erro já foi registrado. Recarregar costuma resolver; se voltar a acontecer, mande o código abaixo para quem cuida do portal.</p></div>
        {requestId && <p className="rounded-xl bg-brand-50 px-3 py-2.5 text-sm text-ink">Código da ocorrência: <code className="font-mono font-semibold">{requestId}</code></p>}
        <button className="btn mt-7" onClick={() => window.location.reload()} type="button"><RefreshCw className="size-4" />Recarregar a página</button>
      </div>
    </main>;
  }
}
