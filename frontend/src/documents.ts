/**
 * O catálogo de finalidades do documento — **um lugar só** deste lado.
 *
 * Espelha `Document.Kind` e `DOCUMENT_KINDS_QUE_ABREM_ENGAGEMENT`
 * (`backend/apps/core/models.py`, ADR 0061). São duas listas, uma em cada lado da rede, e não há
 * como o TypeScript conferir a do Python — então o que resta é mantê-las **uma** de cada lado, com
 * o ponteiro escrito: quem acrescentar um valor lá procura por este comentário.
 *
 * `abreMandato` não é decoração de tela: é o que decide se a opção aparece quando o vínculo não é
 * uma conta. A razão é do servidor — abrir mandato exige conta, porque `Engagement.clean()` compara
 * a conta do acordo com a do mandato —, e oferecer a opção fora dali devolveria um 400 que a tela
 * podia ter evitado (DAP `dap-finalidade-do-documento-r2`, A1-r2).
 */
export type DocumentKind = { value: string; label: string; abreMandato: boolean };

export const DOCUMENT_KINDS: DocumentKind[] = [
  { value: "nda", label: "NDA", abreMandato: false },
  { value: "commercial_contract", label: "Contrato comercial", abreMandato: false },
  { value: "proposal", label: "Proposta", abreMandato: false },
  { value: "design_partner_agreement", label: "Design Partner Agreement", abreMandato: true },
];

/** O rótulo de uma finalidade gravada, para a listagem. Vazio quando é documento comum. */
export function rotuloDaFinalidade(kind: string): string {
  return DOCUMENT_KINDS.find(item => item.value === kind)?.label ?? "";
}

/** As finalidades oferecidas para um tipo de vínculo (A1-r2). */
export function finalidadesPara(linkType: string): DocumentKind[] {
  return DOCUMENT_KINDS.filter(item => !item.abreMandato || linkType === "account");
}
