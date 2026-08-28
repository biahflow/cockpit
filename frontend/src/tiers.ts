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
