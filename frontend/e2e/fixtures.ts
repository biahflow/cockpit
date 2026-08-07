/**
 * A trava que faltava: **nenhum e2e passa sobre uma tela que estourou** (FDD 022).
 *
 * O helper da matriz esperava por um `<h1>` como prova de que a tela carregou. O `ErrorBoundary`
 * também tem um `<h1>` — "Esta tela não conseguiu carregar" —, então uma tela que estourava no
 * render era aceita como se fosse a tela, e as duas specs mediam o cartão de erro: pequeno,
 * centrado, sem rolagem horizontal e sem violação de axe. Passava com louvor sem ter olhado para
 * nada, e foi o que aconteceu com **Configurações** desde a ADR 0018 — seis varreduras verdes sobre
 * um cartão de erro.
 *
 * É o mesmo desenho do drill de backup da FDD 021, que confere que a destruição foi real "senão o
 * drill passaria por não ter destruído nada". Um gate precisa saber dizer quando não mediu nada.
 *
 * `auto: true` é o ponto: a guarda não é pedida por teste nenhum, ela **vale para todos** — os da
 * matriz e os três de fluxo, que montam mocks à mão e envelhecem do mesmo jeito. Guarda opcional é
 * guarda que a próxima spec esquece.
 *
 * **`console.error` fica de fora, de propósito.** Pegaria warning de React que hoje ninguém vê
 * (chave de lista, input que troca de controlado para não-controlado), mas o volume pré-existente é
 * desconhecido e transformaria qualquer entrega em faxina de warning. Os dois sinais aqui não têm
 * falso positivo: ou o browser lançou, ou o React desistiu de renderizar a tela.
 */

import { expect, test as base } from "@playwright/test";

export const test = base.extend<{ semTelaEstourada: void }>({
  semTelaEstourada: [
    async ({ page }, use) => {
      const excecoes: string[] = [];
      page.on("pageerror", erro => excecoes.push(erro.message));

      await use();

      // A página pode ter sido fechada pelo próprio teste; aí só resta o que foi coletado.
      if (!page.isClosed()) {
        const estourou = await page.locator("[data-erro-de-render]").count();
        expect(
          estourou,
          "a tela renderizou o ErrorBoundary — o que este teste mediu foi o cartão de erro, não a tela",
        ).toBe(0);
      }
      expect(excecoes, "exceção não tratada na página durante o teste").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
