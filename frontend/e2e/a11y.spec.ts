/**
 * Acessibilidade: varredura axe em toda a matriz de telas, nas três larguras (FDD 022).
 *
 * Roda no browser de verdade, não em jsdom, porque as duas falhas que mais doem aqui —
 * contraste de texto e indicador de foco — dependem de layout e de CSS aplicado, e jsdom não
 * calcula nem um nem outro. Um `jest-axe` no Vitest daria a sensação de cobertura sem ver
 * justamente o que estava quebrado.
 *
 * Roda nas três larguras porque a marcação **muda** com a largura: abaixo de `lg` o `<aside>`
 * some e o menu hambúrguer aparece, então o menu mobile só existe para o axe no viewport
 * mobile e tablet.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { abrir, ROUTES } from "./matrix";

/**
 * O axe **não** cobre isto, e é bom saber por quê: "foco visível" (WCAG 2.4.7) depende de
 * comparar o antes e o depois de um estado que a página não está exibindo, então a regra é de
 * verificação manual — não existe checagem automatizada dela no axe. Foi verificado: com o
 * `focus:outline-none` cru de volta no `index.css`, as 51 varreduras acima continuavam passando.
 *
 * Sem este teste, a correção de foco desta mesma entrega ficaria sem gate nenhum — e seria
 * desfeita no primeiro `focus:outline-none` que alguém colasse de volta.
 *
 * `Tab` e não `.focus()`: foco programático nem sempre casa com `:focus-visible` no Chromium,
 * que é justamente o seletor em teste. Precisa ser navegação por teclado de verdade.
 */
test("o foco de teclado fica visível nos botões", async ({ page }) => {
  await abrir(page, { path: "/", name: "Visão geral", role: "admin" });

  // O orçamento de tabulações precisa caber a navegação inteira antes do primeiro `<button>`: são
  // links até lá, e cada item novo no menu lateral consome um salto. Com 12 ele estourava assim
  // que "Serviços" entrou na lista.
  for (let salto = 0; salto < 24; salto++) {
    await page.keyboard.press("Tab");
    const foco = await page.evaluate(() => {
      const alvo = document.activeElement;
      if (!alvo || alvo.tagName !== "BUTTON") return null;
      const estilo = getComputedStyle(alvo);
      return {
        rotulo: alvo.getAttribute("aria-label") ?? alvo.textContent?.trim().slice(0, 40) ?? "",
        estilo: estilo.outlineStyle,
        largura: parseFloat(estilo.outlineWidth),
      };
    });
    if (!foco) continue;

    expect(foco.estilo, `botão "${foco.rotulo}" sem contorno de foco`).not.toBe("none");
    expect(foco.largura, `botão "${foco.rotulo}" com contorno de foco de largura zero`).toBeGreaterThan(0);
    return;
  }
  throw new Error("nenhum botão recebeu foco em 12 tabulações — o teste não chegou a verificar nada");
});

for (const screen of ROUTES) {
  test(`${screen.name} não tem violação de acessibilidade`, async ({ page }) => {
    await abrir(page, screen);

    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    // Mensagem com regra, impacto e alvo: "1 violação" sem o seletor obriga quem quebrou a
    // reproduzir à mão para descobrir onde.
    expect(
      violations.map(v => `${v.id} (${v.impact}) — ${v.nodes.map(n => n.target.join(" ")).join(", ")}`),
    ).toEqual([]);
  });
}
