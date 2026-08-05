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

    return <main className="grid min-h-screen place-items-center bg-sand px-5 py-10">
      <div className="w-full max-w-lg rounded-3xl border bg-white p-7 shadow-xl shadow-ocean/5 sm:p-9">
        <span className="grid size-11 place-items-center rounded-2xl bg-red-50 text-signal"><TriangleAlert className="size-5" /></span>
        <p className="mt-6 text-sm font-semibold text-ocean">Algo saiu do lugar</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">Esta tela não conseguiu carregar</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">O erro já foi registrado. Recarregar costuma resolver; se voltar a acontecer, mande o código abaixo para quem cuida do portal.</p>
        {requestId && <p className="mt-5 rounded-xl bg-mint px-3 py-2.5 text-sm text-ink">Código da ocorrência: <code className="font-mono font-semibold">{requestId}</code></p>}
        <button className="mt-7 inline-flex items-center justify-center gap-2 rounded-xl bg-ocean px-4 py-3.5 text-sm font-semibold text-white transition hover:bg-ink" onClick={() => window.location.reload()} type="button"><RefreshCw className="size-4" />Recarregar a página</button>
      </div>
    </main>;
  }
}
