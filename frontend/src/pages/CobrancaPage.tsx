import { CalendarClock, CirclePlay, ExternalLink, History, MessageSquareText, PauseCircle, PowerOff, Receipt, Send, Sparkles } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api, getConfig } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog, Modal } from "../components/Modal";
import { healthBadgeClass, satisfacaoBadgeClass } from "../components/StatusDot";
import { mensagemDeFalha } from "../erros";
import type { CobrancaContato, CobrancaPainelLinha, CobrancaRascunho, CobrancaRegua, CobrancaTensaoCausa, SatisfacaoFonte, SatisfacaoNivel, SessionUser } from "../types";

/**
 * A tela onde se decide o próximo passo da cobrança (FDD 036, critério de aceite 7).
 *
 * **O Financeiro é o razão — quem deve o quê. Esta tela é a decisão — o que dizer a quem, e se
 * dizer.** São trabalhos diferentes, e é por isso que são telas diferentes. A seção Segurança da
 * RFC 0004 pede uma coisa só e é ela que justifica a separação: *"quem decide o próximo passo
 * precisa ver health, tempo de casa e valor do cliente na mesma tela, não a dois cliques"* — e a
 * dois cliques ninguém olha.
 *
 * **Nada é calculado aqui.** Próximo degrau, régua aplicada, reincidência, tempo de casa e o motivo
 * do silêncio chegam prontos de `/cobranca/painel/`. Reimplementar qualquer um deles em TypeScript
 * criaria uma segunda definição da régua — o que a ADR 0026 e a FDD 017 proíbem justamente porque
 * duas cópias não ficam vermelhas ao divergir: elas só passam a discordar do relógio, em silêncio,
 * e quem lê a tela decide por um número que o job não usa. O que este arquivo faz com os campos é
 * **formatar** (dinheiro, data, dias em anos) e **rotular** (variante de `.state`, texto do motivo).
 */

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

// O `T12:00:00` não é enfeite: uma data pura vira meia-noite UTC e volta um dia atrás em
// `America/Sao_Paulo`. Num vencimento, um dia é a diferença entre "vence amanhã" e "venceu" — e
// aqui é também a diferença entre o pré-aviso e o lembrete. Mesma forma do `FinanceiroPage`.
const formatDate = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR");

const REGUA: Record<CobrancaRegua, string> = {
  padrao: "régua padrão",
  relacao_longa: "régua de relação longa",
  // O rótulo descreve a régua, não julga o cliente (FDD 037, ADR 0032): quem está "tensa" é a
  // relação, não a pessoa. Insatisfação declarada tira o degrau firme e antecipa a escalada
  // interna — a régua nunca cala por causa da satisfação, ela troca de escada.
  relacao_tensa: "relação tensa",
};

// A satisfação vigente no card da fatura (FDD 037). Só o nível tem rótulo próprio aqui: a fonte já
// vem pronta em `fonte_display` no cadastro de satisfação, mas o painel manda o **código**
// (`declarada`/`percebida`), não o rótulo — mandar os dois seria duplicar o texto por dois
// caminhos que podem discordar.
const SATISFACAO_NIVEL: Record<SatisfacaoNivel, string> = {
  promotor: "Promotor",
  satisfeito: "Satisfeito",
  neutro: "Neutro",
  insatisfeito: "Insatisfeito",
};
const SATISFACAO_FONTE: Record<SatisfacaoFonte, string> = {
  declarada: "declarada pelo cliente",
  percebida: "percebida por quem entrega",
};

// Por que a relação está tensa (FDD 038). O rótulo existe porque a escada é a **mesma** nas duas
// origens: sem ele a tela diria "relação tensa" e quem lê não saberia se conserta a entrega ou liga
// para o cliente. Quem decide a escada continua sendo o backend — isto aqui é texto.
const TENSAO_CAUSA: Record<CobrancaTensaoCausa, string> = {
  satisfacao: "o cliente declarou insatisfação",
  entrega: "a nossa entrega está em estado crítico",
  ambas: "o cliente declarou insatisfação e a nossa entrega está crítica",
};

// O nível que o formulário do atalho nasce marcando, por sinal lido (FDD 038). É **palpite
// editável**, não classificação: `insatisfeito` é a única leitura que afirma algo sobre a relação,
// e as outras duas falam de dinheiro, não de satisfação — daí `neutro`, que é o nível que não é
// alerta. Quem salva escolhe, e é a escolha dela que vira registro (ADR 0032).
const NIVEL_SUGERIDO: Record<Exclude<CobrancaPainelLinha["sinal_kind"], null>, SatisfacaoNivel> = {
  esqueceu: "neutro",
  nao_pode: "neutro",
  insatisfeito: "insatisfeito",
};

/** "há 12 dias" — a idade que faz alguém perguntar de novo (FDD 037). O corte é do backend. */
function satisfacaoIdade(dias: number): string {
  if (dias === 0) return "hoje";
  if (dias === 1) return "há 1 dia";
  return `há ${dias} dias`;
}

/** Dias de casa em prosa. Formatação do número que o backend entregou — o corte da régua é dele. */
function tempoDeCasa(dias: number): string {
  if (dias >= 730) return `${Math.floor(dias / 365)} anos`;
  if (dias >= 365) return "1 ano";
  if (dias >= 60) return `${Math.floor(dias / 30)} meses`;
  if (dias >= 30) return "1 mês";
  return `${Math.max(dias, 0)} dia(s)`;
}

/** Variante de `.state`, nunca a cor (ADR 0026): um `bg-red-50` aqui seria a segunda definição. */
function atrasoTone(dias: number): string {
  if (dias > 0) return "state--3";
  if (dias === 0) return "state--2";
  return "state--off";
}

function atrasoLabel(dias: number): string {
  if (dias > 0) return `${dias} dia(s) de atraso`;
  if (dias === 0) return "Vence hoje";
  return `Vence em ${Math.abs(dias)} dia(s)`;
}

/**
 * O silêncio traduzido. As constantes são as do backend (`cobranca.py`) e cada uma tem texto
 * próprio: uma tela que só diz "nada hoje" ensina quem a usa a não confiar nela, e a régua tem
 * quatro motivos legítimos de calar.
 *
 * O teto de frequência é descrito **sem o número de dias** de propósito: ele mora em
 * `settings.DUNNING_MIN_DAYS_BETWEEN_CONTACTS` e não vem no contrato do painel. Escrevê-lo aqui
 * seria uma cópia da configuração do servidor, e ela passaria a mentir no primeiro ajuste.
 */
function motivoDoSilencio(linha: CobrancaPainelLinha): string {
  switch (linha.motivo) {
    case "suspensa":
      return linha.suspensao
        ? `Cobrança suspensa até ${formatDate(linha.suspensao.until)}, sob ${linha.suspensao.owner_name}.`
        : "Cobrança suspensa.";
    case "degrau_gasto":
      return "O degrau que caberia hoje já foi enviado — ele não se repete, nem hoje nem amanhã.";
    case "teto_de_frequencia":
      return "Teto de frequência: este cliente já recebeu contato há poucos dias. Quem tem três faturas vencidas recebe um e-mail, não três.";
    case "sem_degrau":
      return "Nada hoje — nenhum degrau da régua cabe nesta data. O silêncio da carência é o degrau.";
    case "estado_nao_cobravel":
      return "A fatura não está em estado cobrável.";
    default:
      return "";
  }
}

/**
 * Por que o botão Enviar está desabilitado — ou `""` quando não está.
 *
 * Desabilitado **com o motivo à vista**, e não escondido: botão que some deixa quem usa procurando
 * o que falta. É o padrão da casa desde a tela de Cases (FDD 027) e o `FinanceiroPage`.
 */
function porQueNaoEnvia(linha: CobrancaPainelLinha): string {
  if (!linha.regua_ligada) return "A régua de cobrança está desligada — nada sai por aqui enquanto ela não for ligada.";
  if (linha.suspensao) return `A cobrança está suspensa até ${formatDate(linha.suspensao.until)}. Levante a suspensão antes de enviar.`;
  // Curto de propósito: o motivo por extenso já está na faixa da decisão, logo acima. Repetir o
  // parágrafo inteiro ao lado do botão diria a mesma coisa duas vezes na mesma linha.
  if (!linha.proximo_degrau) return "Sem degrau hoje — o motivo está na linha da decisão, acima.";
  return "";
}

/** Por que o botão de rascunho está desabilitado. A IA desligada **tira o botão**, não o desabilita. */
function porQueNaoRascunha(linha: CobrancaPainelLinha): string {
  if (!linha.proximo_degrau) return "A régua não indica degrau hoje — não há tom a rascunhar.";
  return "";
}

type Envio = { linha: CobrancaPainelLinha; subject: string; body: string; ai_interaction: number | null };

/**
 * `alcance` decide **qual** dos dois vínculos vai no corpo. O `clean()` do modelo exige
 * exatamente uma fatura **ou** um cliente, nunca os dois: uma suspensão que valesse para os dois
 * níveis teria duas leituras possíveis de "levantar", e a errada devolve a cobrança a quem ainda
 * não devia ouvi-la. Nasce em `fatura` porque é o alcance da linha em que se clicou.
 */
type Alcance = "fatura" | "cliente";
const suspensaoVazia = { alcance: "fatura" as Alcance, owner: "", until: "", reason: "" };

/**
 * O registro que o atalho do sinal abre. `fonte` **não** está aqui e não é escolha: a resposta é do
 * cliente, então a fonte é `declarada` (ADR 0032). O que se edita é o nível e a nota — e é uma
 * pessoa quem salva, o que é a decisão inteira desta metade da fatia: a IA leu, ela não registrou.
 */
const registroVazio = { nivel: "neutro" as SatisfacaoNivel, note: "" };

export function CobrancaPage() {
  const { user } = useAuth();
  const isAdmin = Boolean(user?.is_admin);
  // Suspender é o único ato financeiro que Vendas pratica, e a assimetria é do backend (FDD 036):
  // recuar é decisão de *relação*, e quem a carrega é quem responde pelo cliente.
  const podeSuspender = Boolean(user) && user?.role !== "delivery";
  const [linhas, setLinhas] = useState<CobrancaPainelLinha[]>([]);
  const [iaLigada, setIaLigada] = useState(false);
  const [donos, setDonos] = useState<SessionUser[]>([]);
  const [historico, setHistorico] = useState<Record<number, CobrancaContato[]>>({});
  const [aberto, setAberto] = useState<number | null>(null);
  const [envio, setEnvio] = useState<Envio | null>(null);
  const [suspendendo, setSuspendendo] = useState<CobrancaPainelLinha | null>(null);
  const [suspensao, setSuspensao] = useState(suspensaoVazia);
  const [levantando, setLevantando] = useState<CobrancaPainelLinha | null>(null);
  const [registrando, setRegistrando] = useState<CobrancaPainelLinha | null>(null);
  const [registro, setRegistro] = useState(registroVazio);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isLoading, setLoading] = useState(true);

  const load = useCallback(() => api<CobrancaPainelLinha[]>("/cobranca/painel/")
    .then(setLinhas)
    .catch((cause: unknown) => setError(mensagemDeFalha(cause)))
    .finally(() => setLoading(false)), []);

  useEffect(() => { void load(); }, [load]);
  // A flag de IA decide se o rascunho existe na tela (ADR 0031). Só admin rascunha e envia, então
  // só ele precisa perguntar — pedir por Vendas seria colher um 403 previsível.
  useEffect(() => {
    if (!isAdmin) return;
    void getConfig().then(config => setIaLigada(config.ai_enabled)).catch(() => setIaLigada(false));
  }, [isAdmin]);
  // Vendas não alcança `/users/` (o recurso é fechado para ela), e é por isso que a lista cai na
  // própria sessão em vez de ficar vazia: um select de dono sem opção nenhuma tornaria a suspensão
  // impossível justamente para quem responde pela relação.
  useEffect(() => { void api<SessionUser[]>("/users/").then(setDonos).catch(() => setDonos([])); }, []);

  const donosDisponiveis = donos.length ? donos : user ? [user] : [];
  const nomeDe = (dono: SessionUser) => `${dono.first_name} ${dono.last_name}`.trim() || dono.username;
  // Todas as linhas trazem o mesmo `regua_ligada` (é o estado da flag, não da fatura). Sem linha
  // nenhuma não há o que decidir, e por isso também não há aviso a dar.
  const reguaLigada = linhas.length ? linhas[0].regua_ligada : null;

  function abrirEnvio(linha: CobrancaPainelLinha, body = "", interaction: number | null = null) {
    setError(""); setNotice("");
    setEnvio({ linha, subject: "", body, ai_interaction: interaction });
  }

  async function rascunhar(linha: CobrancaPainelLinha) {
    if (!linha.proximo_degrau) return;
    setError(""); setNotice(""); setBusy(true);
    try {
      const rascunho = await api<CobrancaRascunho>(`/invoices/${linha.invoice}/cobranca/rascunhar/`, {
        method: "POST", body: JSON.stringify({ degrau: linha.proximo_degrau }),
      });
      abrirEnvio(linha, rascunho.text, rascunho.interaction);
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  async function enviar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!envio?.linha.proximo_degrau) return;
    setError(""); setBusy(true);
    try {
      await api(`/invoices/${envio.linha.invoice}/cobranca/enviar/`, {
        method: "POST",
        body: JSON.stringify({
          degrau: envio.linha.proximo_degrau,
          subject: envio.subject,
          body: envio.body,
          ...(envio.ai_interaction ? { ai_interaction: envio.ai_interaction } : {}),
        }),
      });
      setEnvio(null);
      setNotice("Cobrança enviada e registrada. Este degrau não se repete nesta fatura.");
      await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  async function suspender(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!suspendendo) return;
    setError(""); setBusy(true);
    try {
      await api("/cobranca/suspensoes/", {
        method: "POST",
        body: JSON.stringify({
          // Um **ou** o outro, nunca os dois — a regra é do `clean()` do modelo, e mandar os dois
          // seria pedir 400 para dizer o que a tela já sabia.
          ...(suspensao.alcance === "cliente"
            ? { client: suspendendo.client }
            : { invoice: suspendendo.invoice }),
          owner: Number(suspensao.owner),
          until: suspensao.until,
          reason: suspensao.reason,
        }),
      });
      setSuspendendo(null); setSuspensao(suspensaoVazia);
      setNotice("Cobrança suspensa. Ela expira sozinha na data marcada — recuar aqui é declarado, não silencioso.");
      await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  /**
   * Registra a satisfação a partir da resposta que a IA leu (FDD 038).
   *
   * O atalho **pré-preenche**; quem afirma é quem clica em salvar, e é por isso que o `POST` sai
   * daqui e não do backend ao classificar. `source_activity` é o que faz o sinal sumir da linha
   * depois: sem ele o mesmo lembrete insistiria para sempre, inclusive com o registro já feito.
   */
  async function registrarSatisfacao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!registrando?.sinal_activity) return;
    setError(""); setBusy(true);
    try {
      await api("/satisfacoes/", {
        method: "POST",
        body: JSON.stringify({
          client: registrando.client,
          source_activity: registrando.sinal_activity,
          nivel: registro.nivel,
          fonte: "declarada",
          // O dia do acontecido, e não o de hoje: o sinal envelhece por uma janela de 90 dias, e
          // carimbar o registro com a data do cadastro esticaria a validade do que o cliente disse.
          happened_on: registrando.sinal_em,
          note: registro.note,
        }),
      });
      setRegistrando(null); setRegistro(registroVazio);
      setNotice("Satisfação registrada, com o seu nome. A leitura da IA vira registro só aqui — e agora ela move o Health Score e a régua.");
      await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  async function levantar() {
    const alvo = levantando;
    if (!alvo?.suspensao) return;
    setLevantando(null); setError(""); setNotice(""); setBusy(true);
    try {
      await api(`/cobranca/suspensoes/${alvo.suspensao.id}/levantar/`, { method: "POST" });
      setNotice("Suspensão levantada, com autor e carimbo. A régua volta a falar sobre esta fatura.");
      await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  async function verHistorico(linha: CobrancaPainelLinha) {
    if (aberto === linha.invoice) { setAberto(null); return; }
    setAberto(linha.invoice);
    if (historico[linha.invoice]) return;
    try {
      const itens = await api<CobrancaContato[]>(`/cobranca/?invoice=${linha.invoice}`);
      setHistorico(prev => ({ ...prev, [linha.invoice]: itens }));
    } catch (cause) { setError(mensagemDeFalha(cause)); }
  }

  if (isLoading) return <p className="text-sm text-slate-600">Carregando a régua de cobrança…</p>;

  const emDialogo = Boolean(envio || suspendendo || registrando);

  return <section className="space-y-7">
    {envio && <Modal title="Enviar cobrança" width="3xl" onClose={() => setEnvio(null)}>
      <form className="grid gap-4" onSubmit={event => void enviar(event)}>
        {/* Nunca envia sem alguém ver o corpo (ADR 0031). O degrau determinístico sai sozinho
            porque seu texto é constante revisada uma vez; o que muda aqui é a **redação**, e a
            redação é precisamente o que uma pessoa revisaria. */}
        <p className="text-sm text-muted">
          <strong className="text-ink">{envio.linha.client_name}</strong> · fatura {envio.linha.number || "sem número"} · degrau <strong className="text-ink">{envio.linha.proximo_degrau_display}</strong>.
          O texto sai como está escrito abaixo, com o seu nome no registro.
        </p>
        {error && <p role="alert" className="alert--error">{error}</p>}
        <label className="form-label">Assunto
          <input className="field" value={envio.subject} placeholder="Em branco usa o assunto padrão do degrau"
            onChange={event => setEnvio({ ...envio, subject: event.target.value })} />
        </label>
        <label className="form-label">Texto revisado
          <textarea required rows={12} className="field" value={envio.body}
            onChange={event => setEnvio({ ...envio, body: event.target.value })} />
        </label>
        {envio.ai_interaction && <p className="text-xs text-muted">Rascunhado por IA e registrado como revisado por você — o registro guarda qual interação produziu o texto.</p>}
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={busy || !envio.body.trim()} className="btn"><Send className="size-4" />{busy ? "Enviando…" : "Enviar ao cliente"}</button>
          <button type="button" className="btn btn--secondary" onClick={() => setEnvio(null)}>Cancelar</button>
        </div>
      </form>
    </Modal>}

    {suspendendo && <Modal title="Suspender cobrança" onClose={() => { setSuspendendo(null); setSuspensao(suspensaoVazia); }}>
      <form className="grid gap-4" onSubmit={event => void suspender(event)}>
        {/* Dono, prazo e motivo obrigatórios (RFC 0004). Suspender é a regra que mais apodrece na
            prática: vira desculpa para nunca cobrar, e o recebível estraga invisível. Com dono ela
            tem quem responda, com prazo ela expira sozinha, com motivo a próxima pessoa entende. */}
        <p className="text-sm text-muted">
          A régua se cala até a data marcada e volta a falar sozinha depois dela.
        </p>
        {error && <p role="alert" className="alert--error">{error}</p>}
        {/* Os dois alcances existem porque a RFC 0004 descreve o caso mais importante no nível do
            cliente: *"suspender quando o cliente está insatisfeito"* é sobre a relação, não sobre
            uma fatura. Quem tem três vencidas e está insatisfeito não precisa ser calado três
            vezes — e calar só uma delas deixa as outras duas cobrando por baixo. */}
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium text-slate-700">Alcance da suspensão</legend>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="radio" name="alcance" className="size-4" checked={suspensao.alcance === "fatura"}
              onChange={() => setSuspensao({ ...suspensao, alcance: "fatura" })} />
            Só esta fatura ({suspendendo.number || "sem número"})
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="radio" name="alcance" className="size-4" checked={suspensao.alcance === "cliente"}
              onChange={() => setSuspensao({ ...suspensao, alcance: "cliente" })} />
            Este cliente inteiro — {suspendendo.client_name}
          </label>
        </fieldset>
        <label className="form-label">Dono da suspensão
          <select required className="field" value={suspensao.owner} onChange={event => setSuspensao({ ...suspensao, owner: event.target.value })}>
            <option value="">Selecione quem responde por ela</option>
            {donosDisponiveis.map(dono => <option key={dono.id} value={dono.id}>{nomeDe(dono)}</option>)}
          </select>
        </label>
        <label className="form-label">Suspender até
          <input required type="date" className="field" value={suspensao.until} onChange={event => setSuspensao({ ...suspensao, until: event.target.value })} />
        </label>
        <label className="form-label">Motivo
          <textarea required rows={3} className="field" placeholder="Entrega atrasada, cliente insatisfeito, acordo em andamento…"
            value={suspensao.reason} onChange={event => setSuspensao({ ...suspensao, reason: event.target.value })} />
        </label>
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={busy} className="btn"><PauseCircle className="size-4" />{busy ? "Suspendendo…" : "Suspender"}</button>
          <button type="button" className="btn btn--secondary" onClick={() => { setSuspendendo(null); setSuspensao(suspensaoVazia); }}>Cancelar</button>
        </div>
      </form>
    </Modal>}

    {registrando && <Modal title="Registrar satisfação" onClose={() => { setRegistrando(null); setRegistro(registroVazio); }}>
      <form className="grid gap-4" onSubmit={event => void registrarSatisfacao(event)}>
        {/* A leitura da IA vira registro **aqui**, com o nome de quem salvou (ADR 0032). O modelo
            classificou uma resposta; afirmar que o cliente está insatisfeito é outra coisa, e é
            ela que tira 20 pontos do Health Score e troca a escada da cobrança. */}
        <p className="text-sm text-muted">
          A resposta de <strong className="text-ink">{registrando.client_name}</strong> foi lida como <strong className="text-ink">{registrando.sinal_display}</strong> em {registrando.sinal_em ? formatDate(registrando.sinal_em) : ""}. O que a IA leu não é registro — o registro é este, e sai com o seu nome.
        </p>
        {error && <p role="alert" className="alert--error">{error}</p>}
        {/* A fonte não é escolha: foi o cliente quem respondeu, então é declarada. É a fonte que
            move número (ADR 0032), e deixá-la editável aqui convidaria a registrar como "o cliente
            disse" o que ninguém ouviu dele. */}
        <p className="text-sm text-muted">
          Fonte: <strong className="text-ink">declarada pelo cliente</strong> — foi ele quem respondeu à cobrança.
        </p>
        <label className="form-label">Nível
          <select required className="field" value={registro.nivel}
            onChange={event => setRegistro({ ...registro, nivel: event.target.value as SatisfacaoNivel })}>
            {(Object.keys(SATISFACAO_NIVEL) as SatisfacaoNivel[]).map(nivel =>
              <option key={nivel} value={nivel}>{SATISFACAO_NIVEL[nivel]}</option>)}
          </select>
        </label>
        <label className="form-label">O que o cliente disse
          <textarea required={registro.nivel === "insatisfeito"} rows={3} className="field"
            placeholder="A frase dele, não a sua leitura sobre ele"
            value={registro.note} onChange={event => setRegistro({ ...registro, note: event.target.value })} />
        </label>
        {registro.nivel === "insatisfeito" && <p className="text-xs text-muted">Insatisfeito sem nota não se avalia depois: seis meses adiante ninguém sabe o que o cliente disse, e a cobrança segue abrandada por um registro que ninguém consegue julgar.</p>}
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={busy} className="btn"><MessageSquareText className="size-4" />{busy ? "Registrando…" : "Registrar"}</button>
          <button type="button" className="btn btn--secondary" onClick={() => { setRegistrando(null); setRegistro(registroVazio); }}>Cancelar</button>
        </div>
      </form>
    </Modal>}

    {levantando && <ConfirmDialog
      title="Levantar suspensão"
      message={<>A régua volta a falar sobre a fatura <strong className="text-ink">{levantando.number || "sem número"}</strong> de {levantando.client_name} a partir da próxima passada. O levantamento fica registrado com autor e carimbo — não existe voltar a cobrar em silêncio.</>}
      confirmLabel="Levantar" busy={busy}
      onCancel={() => setLevantando(null)} onConfirm={() => void levantar()}
    />}

    <header className="page-head">
      <p className="eyebrow">Financeiro</p>
      <h1>Cobrança</h1>
      <p>Contas a receber é o razão: quem deve o quê. Esta tela é a decisão: o que dizer a quem, e se dizer. Health, tempo de casa, total já recebido e reincidência aparecem na mesma linha do próximo degrau porque cobrar um cliente de cinco anos com tom de caloteiro é como se perde um cliente de cinco anos por uma fatura de trinta dias.</p>
    </header>

    <a href="/financeiro" className="btn btn--secondary"><Receipt className="size-4" />Ver o razão em Contas a receber</a>

    {/* Estado declarado, não erro — daí `.state--off` e `role="status"` em vez de `.alert--error`.
        A tela continua inteira de propósito: ela serve justamente para decidir se vale ligar. */}
    {reguaLigada === false && <div role="status" className="panel flex flex-wrap items-center gap-4">
      <span className="state state--off"><PowerOff className="size-3" />Régua desligada</span>
      <p className="min-w-0 flex-1 text-sm text-muted">
        <strong className="text-ink">Nada sai sozinho.</strong> Nenhum degrau vira e-mail e nenhum aviso interno é disparado enquanto a régua estiver desligada. Ela nasce assim porque a baixa automática de pagamento ainda não foi homologada — e ligar antes disso é arriscar cobrar quem já pagou, o único defeito desta funcionalidade que custa um cliente.
      </p>
    </div>}

    {error && !emDialogo && <p role="alert" className="alert--error">{error}</p>}
    {notice && <p role="status" className="alert--ok">{notice}</p>}

    {linhas.length ? <div className="grid gap-4">{linhas.map(linha => {
      const naoEnvia = porQueNaoEnvia(linha);
      const naoRascunha = porQueNaoRascunha(linha);
      const silencio = motivoDoSilencio(linha);
      const identifica = `${linha.client_name} · fatura ${linha.number || "sem número"}`;
      const contatos = historico[linha.invoice];
      return <article key={linha.invoice} className="panel panel--flush">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line bg-slate-50/60 px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="metric-icon"><Receipt className="size-4" /></span>
              <h2 className="font-semibold text-ink">{linha.client_name}</h2>
              <span className={`state ${linha.status === "overdue" ? "state--3" : "state--2"}`}>{linha.status_display}</span>
              <span className={`state ${atrasoTone(linha.dias_de_atraso)}`}>{atrasoLabel(linha.dias_de_atraso)}</span>
            </div>
            <p className="mt-1 text-sm text-muted">Fatura {linha.number || "sem número"}</p>
          </div>
          <div className="text-right">
            <p className="text-lg font-semibold text-ink">{money.format(Number(linha.amount))}</p>
            <p className="text-xs text-muted">Vence {formatDate(linha.due_date)}</p>
          </div>
        </div>

        {/* A razão de esta tela existir separada do Financeiro (RFC 0004, seção Segurança): os
            quatro fatos da relação **na mesma linha do próximo degrau**, sem clique. Pô-los atrás
            de um "ver mais" seria não ter entregado nada — a dois cliques ninguém olha. */}
        <div className="grid gap-3 border-b border-line px-5 py-4 sm:px-6">
          <p className="text-sm text-ink">
            Cliente há {tempoDeCasa(linha.tempo_de_casa_dias)}, {linha.reincidente ? "já atrasou antes" : "nunca atrasou"} — {REGUA[linha.regua]}{linha.tensao_causa ? `, porque ${TENSAO_CAUSA[linha.tensao_causa]}` : ""}.
          </p>
          <dl className="flex flex-wrap gap-x-8 gap-y-3">
            {/* O **pior** nível entre os projetos ativos do cliente, e não o do projeto da fatura
                (FDD 038): a trava de entrega olha todos eles, e mostrar o da fatura faria a tela
                dizer "saudável" com a régua já tensa. O corte e a escolha são do backend. */}
            <div>
              <dt className="text-xs text-muted">Saúde da entrega</dt>
              <dd className="mt-1">{linha.health_level
                ? <span className={`state ${healthBadgeClass(linha.health_level)}`}>{linha.health_level}</span>
                : <span className="state state--off">Sem projeto ativo neste cliente</span>}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Já recebido deste cliente</dt>
              <dd className="mt-1 text-sm font-semibold text-ink">{money.format(Number(linha.recebido_do_cliente))}</dd>
            </div>
            {/* A satisfação vigente (FDD 037, ADR 0032), ao lado de saúde, tempo de casa e
                reincidência — o mesmo "na mesma tela, não a dois cliques" da RFC 0004. Sem
                registro na janela de 90 dias o campo some, no molde do que o card já faz com
                `health_level` nulo — não inventa texto de ausência ruidoso. A fonte vai sempre
                junto do nível: é o que diz se aquilo é o cliente falando ou a nossa leitura sobre
                ele, e é a fonte declarada — não a percebida — que troca a régua para `relacao_tensa`. */}
            {linha.satisfacao_nivel && linha.satisfacao_fonte && <div>
              <dt className="text-xs text-muted">Satisfação</dt>
              <dd className="mt-1 flex flex-wrap items-center gap-2">
                <span className={`state ${satisfacaoBadgeClass(linha.satisfacao_nivel)}`}>{SATISFACAO_NIVEL[linha.satisfacao_nivel]}</span>
                <span className="text-xs text-muted">{SATISFACAO_FONTE[linha.satisfacao_fonte]}{linha.satisfacao_dias != null ? ` · ${satisfacaoIdade(linha.satisfacao_dias)}` : ""}</span>
              </dd>
            </div>}
            {/* O sinal que a IA leu na resposta do cliente (FDD 038), e que **ninguém registrou**.
                Fica logo abaixo da satisfação vigente e é rotulado pela diferença entre os dois,
                não pela semelhança: aquela é registro e move número; este é leitura e não move
                nada. Dois sinais parecidos sem essa distinção viram dois números discordando sem
                que ninguém saiba qual olhar (FDD 030), e é por isso que o selo aqui é o neutro
                (`state--off`) e o rótulo diz "por registrar" em vez de repetir "Satisfação". */}
            {linha.sinal_kind && <div>
              <dt className="text-xs text-muted">Resposta lida pela IA — por registrar</dt>
              <dd className="mt-1 flex flex-wrap items-center gap-2">
                <span className="state state--off"><MessageSquareText className="size-3" />{linha.sinal_display}</span>
                <span className="text-xs text-muted">{linha.sinal_em ? formatDate(linha.sinal_em) : ""} · não move o Health Score nem a régua</span>
                <button type="button" className="btn btn--secondary" aria-label={`Registrar satisfação — ${linha.client_name} · fatura ${linha.number || "sem número"}`}
                  onClick={() => { setError(""); setNotice(""); setRegistrando(linha); setRegistro({ ...registroVazio, nivel: NIVEL_SUGERIDO[linha.sinal_kind!] }); }}>
                  Registrar satisfação
                </button>
              </dd>
            </div>}
          </dl>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4 sm:px-6">
          {linha.proximo_degrau_display
            ? <>
                <span className="state state--0"><CalendarClock className="size-3" />Próximo degrau: {linha.proximo_degrau_display}</span>
                {linha.proximo_degrau_em && <span className="text-xs text-muted">cabe desde {formatDate(linha.proximo_degrau_em)}</span>}
              </>
            : <>
                <span className="state state--off">Nada sai hoje</span>
                <span className="min-w-0 flex-1 text-sm text-muted">{silencio}</span>
              </>}
        </div>

        <div className="flex flex-wrap items-center gap-2 px-5 py-4 sm:px-6">
          {linha.payment_url && <a href={linha.payment_url} target="_blank" rel="noreferrer" className="btn btn--secondary">
            <ExternalLink className="size-4" />Link de pagamento
          </a>}

          {/* A IA desligada **tira o botão da tela** e não tira um único lembrete do ar (ADR 0031):
              o texto do degrau é constante de código, e a régua funciona sem modelo nenhum. */}
          {isAdmin && iaLigada && <>
            <button type="button" disabled={busy || Boolean(naoRascunha)} title={naoRascunha}
              aria-label={`Rascunhar no tom — ${identifica}`} onClick={() => void rascunhar(linha)} className="btn btn--secondary">
              <Sparkles className="size-4" />Rascunhar no tom
            </button>
            {naoRascunha && <span className="text-xs text-muted">{naoRascunha}</span>}
          </>}

          {isAdmin && <>
            <button type="button" disabled={busy || Boolean(naoEnvia)} title={naoEnvia}
              aria-label={`Enviar cobrança — ${identifica}`} onClick={() => abrirEnvio(linha)} className="btn">
              <Send className="size-4" />Enviar
            </button>
            {naoEnvia && <span className="min-w-0 flex-1 text-xs text-muted">{naoEnvia}</span>}
          </>}

          {podeSuspender && (linha.suspensao
            ? <button type="button" disabled={busy} aria-label={`Levantar suspensão — ${identifica}`}
                onClick={() => setLevantando(linha)} className="btn btn--secondary">
                <CirclePlay className="size-4" />Levantar
              </button>
            : <button type="button" disabled={busy} aria-label={`Suspender cobrança — ${identifica}`}
                onClick={() => { setSuspendendo(linha); setSuspensao({ ...suspensaoVazia, owner: user ? String(user.id) : "" }); }} className="btn btn--secondary">
                <PauseCircle className="size-4" />Suspender
              </button>)}

          <button type="button" aria-expanded={aberto === linha.invoice} aria-label={`Histórico de cobrança — ${identifica}`}
            onClick={() => void verHistorico(linha)} className="btn btn--secondary">
            <History className="size-4" />Histórico
          </button>
        </div>

        {aberto === linha.invoice && (contatos?.length
          ? <div className="panel-rows border-t border-line">{contatos.map(contato => <div key={contato.id} className="row">
              <div className="row-main">
                <strong>{contato.degrau_display} · {contato.canal_display}</strong>
                <span>{formatDate(contato.sent_on)}{contato.to_email && ` · ${contato.to_email}`}{contato.sent_by ? "" : " · enviado pela régua"}</span>
                {contato.subject && <span>{contato.subject}</span>}
              </div>
            </div>)}</div>
          : <p className="border-t border-line px-5 py-4 text-sm text-muted sm:px-6">{contatos ? "Nada saiu sobre esta fatura ainda." : "Carregando o histórico…"}</p>)}
      </article>;
    })}</div> : <p className="empty-state">Nenhuma fatura cobrável hoje. A régua só olha fatura emitida ou vencida — paga, cancelada e renegociada são estados terminais e não têm degrau.</p>}

    <p className="text-xs text-muted">O degrau determinístico sai sozinho porque seu texto é constante revisada uma vez; o texto de IA nunca sai sem uma pessoa ver o corpo (ADR 0031). Escalar, renegociar, dar desconto e suspender seguem sendo atos humanos, com autor e carimbo.</p>
  </section>;
}
