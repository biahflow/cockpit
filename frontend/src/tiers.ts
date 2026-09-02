import type { Service, ServiceTier } from "./types";

/** O único degrau gratuito por definição da metodologia (ADR 0030, `docs/metodologia-fde.md`). */
export const DEGRAU_GRATUITO: ServiceTier = "qualification_call";

/**
 * Gratuito é o **degrau**, não o preço zero.
 *
 * A escada nasce com `list_price = 0` em degrau que ainda não teve preço decidido — a
 * Transformation Partnership, por exemplo, é recorrente mensal e o catálogo ainda não sabe
 * representar recorrência (migração `0050`). Ler zero como "gratuito" anunciaria de graça o que a
 * casa cobra, e é por isso que esta regra mora num lugar só: uma segunda definição de "gratuito"
 * diverge da primeira no dia em que um degrau novo entrar com preço a definir.
 */
export function ehGratuito(service: Pick<Service, "tier" | "list_price">): boolean {
  return service.tier === DEGRAU_GRATUITO && Number(service.list_price) === 0;
}

/** Zero sem ser gratuito: preço que ainda não foi decidido na tela Serviços. */
export function precoADefinir(service: Pick<Service, "tier" | "list_price">): boolean {
  return Number(service.list_price) === 0 && !ehGratuito(service);
}


/**
 * O rótulo de um degrau no seletor de nível de produto — **um lugar só**.
 *
 * Nasceu escrito à mão no Comercial e foi copiado para o modal de criar projeto pelo mandato (DAP
 * `dap-engagement-r3`). As duas cópias já divergiam no dia em que a segunda nasceu: uma formatava
 * sem centavos, a outra com — o mesmo degrau aparecendo de dois jeitos a dois cliques de distância,
 * que é exatamente o defeito que `dinheiro.ts` descreve.
 *
 * Unificado na forma **que já estava no ar** (sem centavos), e não na do `moeda()`: trocar para
 * duas casas mudaria o que o Comercial exibe hoje, e o `dinheiro.ts` registra que essa troca é
 * decisão de produto — quais telas passam a mostrar centavos —, não arrumação de código. Aqui o
 * preço é de catálogo, lido de relance num `<option>`, onde o centavo é ruído.
 */
const precoDoDegrau = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", maximumFractionDigits: 0,
});

export function rotuloDoDegrau(service: Pick<Service, "name" | "tier" | "list_price">): string {
  if (!service.tier) return service.name;
  const preco = ehGratuito(service) ? "gratuito"
    : precoADefinir(service) ? "preço a definir"
      : precoDoDegrau.format(Number(service.list_price));
  return `${service.name} — ${preco}`;
}
