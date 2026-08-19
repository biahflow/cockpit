/**
 * A tradução do código de falha da API em orientação — o que quem leu precisa fazer a seguir.
 *
 * Existe como módulo próprio, e não como constante de uma página, porque **dois consumidores já
 * lêem a mesma tabela**: a tela de Cobrança (rascunhar, enviar, suspender) e a timeline de
 * interações do cliente (classificar a resposta). Uma segunda cópia divergiria da primeira sem
 * nada ficar vermelho — é a mesma razão que faz a régua ter uma definição só no backend.
 *
 * O `detail` do backend vem **na frente**: é ele que diz *qual* régua, *qual* degrau, *qual*
 * recurso está desligado. A orientação vem atrás, e é o que muda entre um código e outro. Trocar
 * os quatro por um "não foi possível concluir a operação" apagaria justamente a diferença entre
 * "ligue a régua", "recarregue a tela" e "escreva o texto à mão".
 */
export const ORIENTACAO: Record<number, string> = {
  400: "Confira o degrau e o texto revisado antes de tentar de novo.",
  409: "O estado mudou desde que esta tela carregou — recarregue para ver o que vale agora.",
  // **`nada foi gravado` é a metade que importa.** Um 502 aqui não é "a IA respondeu que não sabe":
  // é a IA não ter devolvido sinal utilizável, e o backend recusar gravar um palpite no lugar. A
  // coluna do sinal roteia conduta, e um valor chutado manda alguém insistir com quem está
  // insatisfeito — que é exatamente onde insistir piora tudo.
  502: "A IA não devolveu resposta utilizável e nada foi gravado — nenhum palpite entra no lugar. Tente de novo ou siga sem ela.",
  503: "Um administrador liga isso na tela de Configurações.",
};

export function mensagemDeFalha(cause: unknown): string {
  // Leitura estrutural em vez de `instanceof ApiError`: a tela não precisa da classe para ler o
  // código, e depender dela amarraria a página ao formato interno do cliente de API.
  const erro = cause as { message?: string; status?: number };
  const detalhe = erro.message || "Não foi possível concluir a operação.";
  const orientacao = erro.status ? ORIENTACAO[erro.status] : undefined;
  return orientacao ? `${detalhe} ${orientacao}` : detalhe;
}
