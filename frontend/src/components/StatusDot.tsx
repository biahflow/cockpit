import { Eye, EyeOff } from "lucide-react";

import type { CustoEstadoAtual, EpistemicStatus, HealthLevel, PublicationState, SatisfacaoNivel } from "../types";

// Semáforo de saúde 🟢🟡🔴 reutilizável (eleva o mapa antes duplicado em IndicadoresPage).
// Variantes de `.state`, não as cores delas (ADR 0026): um `bg-emerald-50` escrito aqui é uma
// segunda definição de "saudável", e ela diverge da primeira sem nada ficar vermelho.
const HEALTH_BADGE: Record<HealthLevel, string> = {
  "saudável": "state--1",
  "atenção": "state--2",
  "crítico": "state--3",
};
const HEALTH_DOT: Record<HealthLevel, string> = {
  "saudável": "bg-emerald-500",
  "atenção": "bg-amber-500",
  "crítico": "bg-danger",
};

export function healthBadgeClass(level: HealthLevel): string {
  return HEALTH_BADGE[level];
}

// A satisfação do cliente (FDD 037, ADR 0032). Duas telas leem o mesmo nível — a de detalhe do
// cliente e a de Cobrança —, e o mapa mora aqui, ao lado do de saúde, pela mesma razão: uma cópia
// por tela é a segunda definição que diverge sem nada ficar vermelho. `neutro` é `state--off` de
// propósito — é o nível que não é alerta, no molde de "Desligada"/"Arquivado". `insatisfeito` é o
// único que muda comportamento (Health Score e escada da régua) e é o único em `state--3`.
const SATISFACAO_BADGE: Record<SatisfacaoNivel, string> = {
  promotor: "state--0",
  satisfeito: "state--1",
  neutro: "state--off",
  insatisfeito: "state--3",
};

export function satisfacaoBadgeClass(nivel: SatisfacaoNivel): string {
  return SATISFACAO_BADGE[nivel];
}

// A sustentação do custo do estado atual (FDD 039, ADR 0034). Mora aqui, ao lado dos dois mapas
// acima, pela mesma razão deles: **duas telas leem o mesmo valor** — o painel de processos no
// detalhe do cliente e a tela do processo —, e uma cópia por tela é a segunda definição que diverge
// sem nada ficar vermelho.
//
// `hipotese` é `state--2` e não `state--3`: um número ainda não sustentado por fato não é falha, é
// aviso de que aquilo não se apresenta como número fechado ao cliente. E o **texto** vem junto da
// variante de propósito: `"sustentado"`/`"hipotese"` é vocabulário de API, e as duas telas
// precisam dizer a mesma frase legível — separá-los faria uma delas escrever a outra metade à mão.
type Sustentacao = CustoEstadoAtual["sustentacao"];
const SUSTENTACAO_BADGE: Record<Sustentacao, string> = {
  sustentado: "state--1",
  hipotese: "state--2",
};
export const SUSTENTACAO_LABEL: Record<Sustentacao, string> = {
  sustentado: "Sustentado por evidência",
  hipotese: "Ainda em hipótese",
};

export function sustentacaoBadgeClass(sustentacao: Sustentacao): string {
  return SUSTENTACAO_BADGE[sustentacao];
}

// A classificação epistêmica do achado (FDD 045, ADR 0034). Subiu para cá quando ganhou a
// **segunda** tela que o lê — a de publicação do Discovery —, pela razão dos três mapas acima: uma
// cópia por tela é a segunda definição de "fato", e ela diverge da primeira sem nada ficar
// vermelho.
//
// Variante, nunca a cor. `unknown` é `state--off` — o neutro de "Desligada"/"Arquivado" —, porque
// nomear o que ainda não se sabe **não é falha**: é o Discovery fazendo o trabalho. Pintá-lo de
// vermelho mandaria apagar a linha mais honesta do mapa.
const EPISTEMICO_BADGE: Record<EpistemicStatus, string> = {
  fact: "state--1",
  hypothesis: "state--2",
  unknown: "state--off",
};

export function epistemicoBadgeClass(status: EpistemicStatus): string {
  return EPISTEMICO_BADGE[status];
}

// A publicação do Discovery (FDD 051, ADR 0060; DAP `dap-publicacao-discovery-r1`, decisão **D1**).
//
// **Mora aqui, encostado no `sustentacaoBadgeClass` acima, de propósito.** Os dois selos aparecem
// na *mesma linha* de achado e de dor, junto com o `STATUS_BADGE` epistêmico da
// `ProcessDetailPage`, e a decisão D1 é inteira sobre eles não se confundirem. Pôr os mapas lado a
// lado no código é o que torna a distinção visível para quem mexer no próximo — separá-los faria a
// próxima variante nascer sem ninguém ver o vizinho que ela precisa não imitar.
//
// **Dois selos, não quatro.** A pergunta que ele responde é binária — *o cliente vê isto?* —, e é
// por isso que os três estados do servidor caem em duas variantes: `ready` e `blocked` são o mesmo
// "Oculto do cliente". "Pronto" e "bloqueado" respondem *"posso mudar isto?"*, que é pergunta de
// ação e mora junto da ação, como frase vinda do servidor — nunca como uma terceira pastilha.
//
// A separação dos vizinhos é por três eixos e nenhum é só matiz: **forma** (é o único sólido
// escuro, e o único com ícone), **copy** ("Visível"/"Oculto ao cliente" não divide palavra com
// "Fato"/"Hipótese"/"Desconhecido" nem com "Sustentado por evidência") e **posição** (último selo
// da `.row-meta`, encostado na ação).
type EstadoDePublicacao = PublicationState["state"];
const PUBLICACAO_BADGE: Record<EstadoDePublicacao, string> = {
  published: "state--active",
  ready: "state--off",
  blocked: "state--off",
};
export const PUBLICACAO_LABEL: Record<EstadoDePublicacao, string> = {
  published: "Visível ao cliente",
  ready: "Oculto do cliente",
  blocked: "Oculto do cliente",
};

export function publicacaoBadgeClass(estado: EstadoDePublicacao): string {
  return PUBLICACAO_BADGE[estado];
}

/** O selo, com o ícone junto — no molde do `HealthBadge` abaixo.
 *
 * Componente e não só a classe porque **o ícone é metade da distinção**: um `Eye` esquecido numa
 * das três telas que o mostram devolveria a colisão que a decisão D1 resolve, e nada ficaria
 * vermelho. Ele é decorativo (`aria-hidden` implícito pelo `lucide`), e quem nomeia o estado é o
 * texto ao lado.
 */
export function PublicacaoBadge({ estado }: { estado: EstadoDePublicacao }) {
  const Icone = estado === "published" ? Eye : EyeOff;
  return <span className={`state ${PUBLICACAO_BADGE[estado]}`}><Icone className="size-3" />{PUBLICACAO_LABEL[estado]}</span>;
}

export function StatusDot({ level, title }: { level: HealthLevel | null; title?: string }) {
  const cls = level ? HEALTH_DOT[level] : "bg-slate-300";
  return (
    <span
      className={`inline-block size-2.5 rounded-full ${cls}`}
      title={title ?? (level ? `Saúde: ${level}` : "Sem projeto ativo")}
      aria-label={level ? `Saúde ${level}` : "Sem projeto ativo"}
    />
  );
}

export function HealthBadge({ level, score }: { level: HealthLevel; score?: number }) {
  return (
    <span className={`state ${HEALTH_BADGE[level]}`}>
      {level}{score !== undefined ? ` · ${score}` : ""}
    </span>
  );
}
