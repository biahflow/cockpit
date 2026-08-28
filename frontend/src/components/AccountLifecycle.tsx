import type { AccountLifecycleStatus } from "../types";

// Os três estados do ciclo de vida da conta, num lugar só (ADR 0026, no molde de `StatusDot`).
//
// **"Cliente" é o rótulo de `active`, não o nome da entidade** (`docs/ontology/language-map.md`
// §4): a organização se chama conta desde antes de comprar. `inactive` é quem **já foi** cliente e
// hoje não tem trabalho em andamento — conta que continua no histórico e volta a ser cliente
// quando uma oportunidade for ganha.
//
// Duas telas leem estes mapas — a lista de contas e o detalhe —, e por isso eles moram aqui: uma
// cópia por tela é a segunda definição que diverge sem nada ficar vermelho.
//
// O mapa da pílula devolve **variante** (`"state--1"`), nunca a cor. `prospect` e `inactive` são
// `state--off`, o neutro: nenhum dos dois é aviso, do mesmo jeito que "Desligada" e "Arquivado".
export const LIFECYCLE_OPTION_LABEL: Record<AccountLifecycleStatus, string> = {
  prospect: "Prospect — ainda não fechou",
  active: "Cliente — já fechou",
  inactive: "Inativo — foi cliente, não tem trabalho em andamento",
};

export const LIFECYCLE_BADGE_LABEL: Record<AccountLifecycleStatus, string> = {
  prospect: "Prospect",
  active: "Cliente",
  inactive: "Inativo",
};

const LIFECYCLE_BADGE: Record<AccountLifecycleStatus, string> = {
  prospect: "state--off",
  active: "state--1",
  inactive: "state--off",
};

export const LIFECYCLE_ORDER: AccountLifecycleStatus[] = ["prospect", "active", "inactive"];

export function lifecycleBadgeClass(status: AccountLifecycleStatus): string {
  return LIFECYCLE_BADGE[status];
}

export function LifecycleOptions() {
  return (
    <>
      {LIFECYCLE_ORDER.map(value => (
        <option key={value} value={value}>
          {LIFECYCLE_OPTION_LABEL[value]}
        </option>
      ))}
    </>
  );
}
