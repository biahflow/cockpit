/**
 * A marca Pulse no shell, medida no runtime (ADR 0043, DAP GH-26 r1).
 *
 * Existe porque a entrega é `BROWSER_REQUIRED` e três das afirmações dela **não sobrevivem ao
 * jsdom**: qual arquivo o `<img>` foi de fato buscar, se o contorno de foco aparece no link da
 * marca, e se a gaveta do celular — que só existe abaixo de `lg` — passa no axe depois de aberta.
 * O `Layout.test.tsx` cobre o texto e o nome acessível; isto cobre o que depende de layout, de CSS
 * aplicado e de rede.
 *
 * **A gaveta aberta era o ponto cego.** A matriz do `a11y.spec.ts` varre 390px, mas com a gaveta
 * **fechada**: o menu do celular nunca esteve no DOM na hora da varredura, e é justamente a
 * superfície que esta entrega mudou. O caso 2 abaixo fecha esse buraco.
 *
 * Serve a dois propósitos, como o `design-system.spec.ts` da r2: afirma sempre, e **captura**
 * quando `PULSE_DAP_EVIDENCE_DIR` está no ambiente — a evidência de runtime que acompanha o gate
 * de design não é gerada à mão nem por um spec descartável.
 *
 * Roda **só no projeto `e2e`** (Desktop Chrome), porque o `MATRIZ` do `playwright.config.ts:13`
 * casa apenas `a11y|responsive|design-system`. A largura é trocada por `page.setViewportSize()`
 * dentro do teste: triplicar a matriz inteira por causa de uma tela custaria mais do que mede.
 */

import AxeBuilder from "@axe-core/playwright";
import type { Locator } from "@playwright/test";

import { expect, test } from "./fixtures";

import { abrir } from "./matrix";

const VISAO_GERAL = { path: "/", name: "Visão geral", role: "admin" } as const;
const LOGIN = { path: "/", name: "Login", role: null } as const;

const DESKTOP = { width: 1280, height: 800 };
const MOBILE = { width: 390, height: 844 };

/**
 * Qual variante do mark o browser **de fato** carregou.
 *
 * O `src` não é sempre um caminho: o Vite embute asset abaixo de `assetsInlineLimit` como `data:`
 * URI, e os dois arquivos da marca cabem nesse limite. Afirmar pelo nome do arquivo passaria numa
 * configuração e reprovaria na outra sem que nada de verdade tivesse mudado — foi o que esta spec
 * fez na primeira versão. As duas formas são lidas aqui, e o que decide é o mesmo fato nos dois
 * casos: **o preenchimento do tile**, que é a única coisa que separa as variantes (a geometria é
 * idêntica de propósito).
 */
async function variante(img: Locator): Promise<"clay" | "invertida"> {
  const src = (await img.getAttribute("src")) ?? "";
  const conteudo = src.startsWith("data:") ? decodeURIComponent(src) : src;
  if (/pulse-mark-inverse\.svg$/.test(conteudo) || /<rect[^>]*fill='#FFFFFF'/.test(conteudo)) return "invertida";
  if (/pulse-mark\.svg$/.test(conteudo) || /<rect[^>]*fill='#BD4A30'/.test(conteudo)) return "clay";
  throw new Error(`o src do mark não corresponde a nenhuma variante conhecida: ${conteudo.slice(0, 120)}`);
}

/** Só captura quando o diretório de evidência é pedido — em CI e no dia a dia o spec só afirma. */
const capturar = async (pagina: { screenshot: (o: { path: string; fullPage: boolean }) => Promise<unknown> }, nome: string) => {
  if (process.env.PULSE_DAP_EVIDENCE_DIR) {
    await pagina.screenshot({ path: `${process.env.PULSE_DAP_EVIDENCE_DIR}/${nome}`, fullPage: true });
  }
};

test("a barra lateral traz o mark canônico e o wordmark Pulse", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await abrir(page, VISAO_GERAL);

  const lockup = page.locator("aside .brand-row");
  await expect(lockup).toBeVisible();

  // **Pelo DOM, não pela aparência.** O que a regra do repositório proíbe é colar o SVG inline
  // (`assets/brand/README.md:20`), e um `<svg>` colado renderiza idêntico a um `<img>` — só o DOM
  // denuncia. A superfície é clara, então o mark é o clay.
  expect(await lockup.locator("svg").count(), "SVG de marca colado inline no lockup do sidebar").toBe(0);
  expect(await variante(lockup.locator("img"))).toBe("clay");
  await expect(lockup.locator("strong")).toHaveText("Pulse");
  await expect(lockup.locator("small")).toHaveText("Operação Biahflow");

  // A raiz do rastro é o produto, e o segundo nível é a rota atual.
  await expect(page.locator(".breadcrumb")).toHaveText("Pulse/Visão geral");

  await capturar(page, "browser-desktop.png");
});

test("a gaveta do celular recebe o lockup e passa no axe aberta", async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await abrir(page, VISAO_GERAL);

  // Abaixo de `lg` o `<aside>` sai de cena, então nenhum lockup está visível antes de abrir. Sem
  // esta linha o teste passaria medindo o lockup da barra lateral escondida.
  expect(await page.locator(".brand-row:visible").count(), "havia lockup visível antes de abrir a gaveta").toBe(0);

  await page.getByRole("button", { name: "Abrir menu" }).click();

  const naGaveta = page.locator(".brand-row:visible");
  await expect(naGaveta).toHaveCount(1);
  expect(await variante(naGaveta.locator("img"))).toBe("clay");
  await expect(naGaveta.locator("strong")).toHaveText("Pulse");
  // Lockup denso: no celular o subtítulo não entra.
  expect(await naGaveta.locator("small").count(), "a gaveta não leva subtítulo").toBe(0);
  // A gaveta continua servida pelo mesmo `nav()` da barra lateral.
  await expect(page.locator("nav").getByRole("link", { name: "Comercial", exact: true })).toBeVisible();

  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  expect(
    violations.map(v => `${v.id} (${v.impact}) — ${v.nodes.map(n => n.target.join(" ")).join(", ")}`),
    "violação de acessibilidade na gaveta aberta",
  ).toEqual([]);

  await capturar(page, "browser-mobile.png");
});

test("o painel escuro do login usa a variante invertida do mark", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await abrir(page, LOGIN);

  const painel = page.locator(".auth-brand");
  await expect(painel).toBeVisible();

  // **Pelo conteúdo do asset e não por cor computada**: o mark é uma imagem, então
  // `getComputedStyle` não diz nada sobre o que há dentro dela. Qual arquivo chegou é a única
  // prova — e o clay sobre `brand-900` dá 2,45:1, que é o defeito que a variante existe para
  // evitar.
  expect(await variante(painel.locator("img"))).toBe("invertida");
  await expect(painel.locator("strong")).toHaveText("Pulse");
  // Biahflow permanece como guarda-chuva: no eyebrow e na assinatura do rodapé.
  await expect(painel.getByText("Operação Biahflow")).toBeVisible();
  await expect(painel.getByText("Biahflow · processos que fluem")).toBeVisible();

  await capturar(page, "browser-login-desktop.png");
});

test("o link da marca mostra contorno ao receber foco por teclado", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await abrir(page, VISAO_GERAL);

  // `Tab` e não `.focus()`: foco programático nem sempre casa com `:focus-visible` no Chromium,
  // que é justamente o seletor em teste (mesma razão do `a11y.spec.ts:29`). O link da marca é o
  // primeiro tabulável do documento, mas o laço dá folga para um elemento novo entrar antes dele.
  for (let salto = 0; salto < 6; salto++) {
    await page.keyboard.press("Tab");
    const foco = await page.evaluate(() => {
      const alvo = document.activeElement;
      if (!alvo?.closest(".brand-row")) return null;
      const estilo = getComputedStyle(alvo);
      return { estilo: estilo.outlineStyle, largura: parseFloat(estilo.outlineWidth), nome: alvo.textContent?.trim() ?? "" };
    });
    if (!foco) continue;

    expect(foco.estilo, "link da marca sem contorno de foco").not.toBe("none");
    expect(foco.largura, "link da marca com contorno de foco de largura zero").toBeGreaterThan(0);
    expect(foco.nome).toContain("Pulse");
    await capturar(page, "focus-desktop.png");
    return;
  }
  throw new Error("o link da marca não recebeu foco em 6 tabulações — o teste não chegou a verificar nada");
});
