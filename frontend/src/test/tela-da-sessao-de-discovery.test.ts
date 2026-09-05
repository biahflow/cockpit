/**
 * As duas guardas de **forma do código** da Discovery Session (FDD 055).
 * ---------------------------------------------------------------------------
 * Elas moram aqui, e não em `pages/DiscoverySessionPage.test.tsx`, pelo motivo que o
 * `tsconfig.app.json` já registra para `primitivas.test.ts`: quem lê `src/**` do disco com
 * `node:fs` é ferramenta, não código de tela — alargar os tipos de lá levaria os globais do Node
 * para dentro do bundle do navegador.
 *
 * São duas asserções sobre o arquivo, e as duas existem porque o teste de comportamento não as
 * alcança: um caminho de gravação que nenhum teste exercita renderiza igual a um que não existe, e
 * uma pergunta copiada para dentro da tela renderiza igual a uma que veio do servidor.
 */

import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

const TELA = "src/pages/DiscoverySessionPage.tsx";

test("a tela captura texto e não tem caminho para gravar achado (decisão C1)", () => {
  // C2 e C3 quebram a invariante 8 do mapa de linguagem pelo lado que ninguém vigia: não é a IA
  // classificando errado, é a tela gravando achado sem passar pelo coletor que impõe o rótulo.
  // Estruturar continua sendo o ato explícito, disparado depois, com revisão.
  const fonte = readFileSync(TELA, "utf8");

  for (const proibido of ["/findings", "publishFinding", "epistemic_status", "/evidence"]) {
    expect(fonte, `a tela não pode alcançar ${proibido} — estruturar é ato à parte (C1)`)
      .not.toContain(proibido);
  }
});

test("nenhuma pergunta da base está escrita na tela (decisão E1)", () => {
  // E3 (constantes no frontend) foi recusada porque o método precisa alcançar o corpus e os
  // agentes, e nada disso roda no navegador. Uma pergunta copiada para cá viraria a segunda
  // versão dela, divergindo em silêncio da ficha do Notion.
  const fonte = readFileSync(TELA, "utf8");

  const amostra = [
    "Quantos casos desse tipo passam por aqui num mês?",
    "Que planilha existe fora do sistema?",
    "Vocês sabem esse número ou é impressão?",
  ];
  for (const pergunta of amostra) {
    expect(fonte, "a base de perguntas vem do backend (E1)").not.toContain(pergunta);
  }
});
