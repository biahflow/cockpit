import type { SessionUser } from "./types";

/**
 * Entrega **e nada mais** — a pergunta que decide se a tela mostra a ação de escrita.
 *
 * Superusuário passa por aqui mesmo com `role = "delivery"`, porque é assim que a API o lê:
 * `User.is_admin_role` é `role == ADMIN or is_superuser` (`backend/apps/core/models.py`), e
 * `RolePermission` libera na entrada. Filtrar só por `role` esconde da tela o que a API
 * aceitaria — o oposto da regra que vale aqui, que é deixar de mostrar o que a API recusaria.
 *
 * Não é hipótese: `createsuperuser` não pergunta o papel e o default do modelo é `DELIVERY`,
 * então esse é o estado de todo mundo que acabou de subir o produto. `Layout.tsx` já tinha
 * corrigido o menu lateral por esse motivo; o detalhe da conta, a Cobrança e a Comercial não
 * receberam a correção e escondiam formulário de quem podia escrever.
 *
 * Mora num lugar só pela razão de `tiers.ts` e `journey.ts`: a regra estava copiada em seis
 * pontos, duas cópias certas e quatro erradas — que é exatamente como uma segunda definição
 * diverge da primeira sem nada ficar vermelho.
 */
export function isDeliveryOnly(user: SessionUser | null | undefined): boolean {
  return !!user && user.role === "delivery" && !user.is_admin;
}

/**
 * Quem escreve o que a Entrega não escreve — o portão dos formulários e dos botões de ação.
 *
 * Separado de `isDeliveryOnly` porque as duas perguntas discordam quando **não há usuário**
 * (sessão carregando, ou deslogado): ali "é Entrega restrita?" é `false`, mas "pode escrever?"
 * também é `false`, e um portão escrito como a negação do outro passaria a desenhar formulário de
 * escrita para ninguém logado. São duas perguntas, e por isso são duas funções — cada uma com
 * uma definição.
 */
export function canWriteBeyondDelivery(user: SessionUser | null | undefined): boolean {
  return !!user && !isDeliveryOnly(user);
}
