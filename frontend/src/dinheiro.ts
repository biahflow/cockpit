/**
 * O dinheiro do produto, formatado num lugar só.
 *
 * **Por que existe.** `new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })`
 * está escrito à mão em sete páginas, com **duas configurações diferentes** — quatro delas usam
 * `maximumFractionDigits: 0` porque são painéis, onde o centavo é ruído; as outras mostram as duas
 * casas. Uma tela nova que copiasse a linha da vizinha herdaria a decisão da vizinha por acidente,
 * e é assim que o mesmo valor passa a aparecer com duas formas na mesma sessão.
 *
 * **Por que não foi aplicado retroativamente.** Trocar os sete pelo `moeda()` mudaria o número que
 * quatro painéis exibem hoje — `R$ 1.440.000` viraria `R$ 1.440.000,00` —, e aquilo não é dívida:
 * é escolha de leitura de painel, tomada por quem os escreveu. Um refactor que altera saída visível
 * em telas fora do escopo da fatia é exatamente o "aproveitei para melhorar" que o diff não deixa
 * revisar. Quem quiser unificar depois precisa decidir antes **quais** telas passam a mostrar
 * centavos, e isso é decisão de produto, não de arrumação.
 *
 * **Duas casas, sempre.** O custo do estado atual (FDD 039) chega da API como string decimal de
 * duas casas, e o `Process` inteiro existe para levar um número ao cliente com a conta à vista.
 * Um total exibido sem centavos não fecharia com a soma das parcelas exibidas do lado.
 */

const BRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formata para exibição — e **só** para exibição.
 *
 * O `Number()` aqui é a última coisa que acontece com o valor, na borda da tela. A API manda
 * dinheiro como string de propósito (`COERCE_DECIMAL_TO_STRING`, e o `process.py` evita `float`
 * por dentro pela mesma razão), então somar, subtrair ou comparar esses valores em `number` no SPA
 * reintroduziria o erro de centavo que o backend gastou trabalho para não ter. Formatar não soma;
 * qualquer aritmética de dinheiro continua sendo do servidor.
 */
export function moeda(valor: string | number): string {
  return BRL.format(typeof valor === "string" ? Number(valor) : valor);
}
