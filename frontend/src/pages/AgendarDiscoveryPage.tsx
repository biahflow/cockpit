import { useCallback, useEffect, useState } from "react";

import { ApiError, bookDiscovery, getDiscoveryBookingSlots } from "../api";
import { PulseBrand } from "../components/PulseBrand";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro"; codigo: string }
  | { tipo: "agendado"; conta: string; horario: string }
  | { tipo: "vazio"; conta: string }
  | { tipo: "pronto"; conta: string; slots: string[] };

/**
 * As mensagens dos estados de exceção — decisão **D1** do DAP `dap-agendamento-discovery-r1`:
 * cada estado com a sua, porque "seu link expirou" e "não há horário livre" pedem coisas
 * diferentes de quem está lendo.
 *
 * O board desenha **quatro**. O backend tem um quinto — `booking_disabled`, a flag desligada —
 * que não está no pacote. Ele reaproveita a mensagem de `calendar_unavailable` de propósito: para
 * quem está do outro lado do link, as duas são a mesma coisa — não dá para escolher agora, e a
 * culpa não é dele. Esta é a única decisão desta tela que não está no board.
 */
const MENSAGEM_DE_ERRO: Record<string, { titulo: string; corpo: string }> = {
  token_expired: {
    titulo: "Seu link expirou",
    corpo: "Responda ao e-mail que enviamos e mandamos outro.",
  },
  token_invalid: {
    titulo: "Link não reconhecido",
    corpo: "Confira se copiou o endereço inteiro.",
  },
  calendar_unavailable: {
    titulo: "Não foi possível carregar os horários",
    corpo: "Tente de novo em alguns minutos.",
  },
  booking_disabled: {
    titulo: "Não foi possível carregar os horários",
    corpo: "Tente de novo em alguns minutos.",
  },
};

function mensagemDoErro(codigo: string) {
  return MENSAGEM_DE_ERRO[codigo] ?? MENSAGEM_DE_ERRO.calendar_unavailable;
}

function capitalizado(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** "quinta-feira" → "quinta". Fins de semana (fora de `BOOKING_HOURS`) não têm o sufixo e ficam como vêm. */
function diaDaSemana(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { weekday: "long" }).format(new Date(iso)).split("-feira")[0];
}

/** "Quinta, 4 de setembro" — o cabeçalho de cada grupo de horários. */
function diaFormatado(iso: string): string {
  const dataCurta = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long" }).format(new Date(iso));
  return `${capitalizado(diaDaSemana(iso))}, ${dataCurta}`;
}

/** "10:00" — a hora de um horário. */
function horaFormatada(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

/** Chave de dia local, para agrupar sem depender do fuso de quem lê o ISO. */
function chaveDoDia(iso: string): string {
  const data = new Date(iso);
  return `${data.getFullYear()}-${data.getMonth()}-${data.getDate()}`;
}

type GrupoDeDia = { chave: string; primeiro: string; horarios: string[] };

/** Agrupa os horários por dia local, preservando a ordem cronológica que o backend já manda. */
function agruparPorDia(slots: string[]): GrupoDeDia[] {
  const grupos: GrupoDeDia[] = [];
  for (const slot of slots) {
    const chave = chaveDoDia(slot);
    const grupo = grupos.find(item => item.chave === chave);
    if (grupo) grupo.horarios.push(slot);
    else grupos.push({ chave, primeiro: slot, horarios: [slot] });
  }
  return grupos;
}

/**
 * A página pública `/agendar/<token>` — o cliente escolhe o horário do Discovery (DAP
 * `dap-agendamento-discovery-r1`, decisões **A1 · B1 · C1 · D1 · E2**).
 *
 * Sem `Layout`, sem menu, sem breadcrumb, sem link para `/`: o token é a credencial, e a página
 * não oferece caminho para o resto do produto (nota de implementação do DAP).
 */
export function AgendarDiscoveryPage({ token }: { token: string }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [avisoDeCorrida, setAvisoDeCorrida] = useState("");

  const carregar = useCallback(() => {
    return getDiscoveryBookingSlots(token)
      .then(resposta => {
        if (resposta.scheduled_at) {
          setEstado({ tipo: "agendado", conta: resposta.account, horario: resposta.scheduled_at });
        } else if (resposta.slots.length === 0) {
          setEstado({ tipo: "vazio", conta: resposta.account });
        } else {
          setEstado({ tipo: "pronto", conta: resposta.account, slots: resposta.slots });
        }
      })
      .catch((cause: unknown) => setEstado({ tipo: "erro", codigo: cause instanceof ApiError ? cause.code : "" }));
  }, [token]);

  useEffect(() => { void carregar(); }, [carregar]);

  async function confirmar() {
    if (!selecionado) return;
    setEnviando(true);
    setAvisoDeCorrida("");
    try {
      await bookDiscovery({ token, slot_start: selecionado });
      setSelecionado(null);
      await carregar();
    } catch (cause) {
      const codigo = cause instanceof ApiError ? cause.code : "";
      if (codigo === "slot_unavailable") {
        // O horário que alguém pegou entre o carregamento e o clique: recarrega a agenda e diz
        // que aquele acabou de sair, em vez de deixar o cliente no escuro.
        setSelecionado(null);
        setAvisoDeCorrida("Esse horário acabou de ser preenchido. Escolha outro.");
        await carregar();
      } else if (codigo === "already_scheduled") {
        // A mesma corrida, vista do outro lado: outra aba já marcou este mandato. Recarrega e
        // mostra o horário marcado (decisão C1), em vez de repetir a tentativa.
        await carregar();
      } else {
        setEstado({ tipo: "erro", codigo });
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-canvas px-4 py-10">
      <div className="panel w-full max-w-md sm:p-8">
        <PulseBrand subtitle={null} />

        {estado.tipo === "carregando" && (
          <div className="mt-6" aria-live="polite">
            <p className="sr-only">Carregando horários…</p>
            <div className="h-3 w-2/5 animate-pulse rounded bg-line" />
            <div className="mt-3 h-6 w-3/4 animate-pulse rounded bg-line" />
            <div className="mt-4 flex gap-2">
              <div className="h-9 w-16 animate-pulse rounded-lg bg-line" />
              <div className="h-9 w-16 animate-pulse rounded-lg bg-line" />
              <div className="h-9 w-16 animate-pulse rounded-lg bg-line" />
            </div>
          </div>
        )}

        {estado.tipo === "erro" && (() => {
          const mensagem = mensagemDoErro(estado.codigo);
          return (
            <div className="mt-6">
              <h1 className="text-2xl font-semibold tracking-tight text-ink">{mensagem.titulo}</h1>
              <p role="alert" className="alert--error mt-4">{mensagem.corpo}</p>
            </div>
          );
        })()}

        {estado.tipo === "agendado" && (
          <div className="mt-6">
            <p className="text-xs text-muted">{estado.conta}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Está marcado</h1>
            <p className="mt-2 text-sm text-muted">
              {diaFormatado(estado.horario)}, às {horaFormatada(estado.horario)}. O convite foi para o seu e-mail.
            </p>
            <span className="state state--1 mt-4">Discovery agendado</span>
            <p className="mt-4 text-xs text-muted">Precisa mudar? Responda ao e-mail que enviamos.</p>
          </div>
        )}

        {estado.tipo === "vazio" && (
          <div className="mt-6">
            <p className="text-xs text-muted">{estado.conta}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Vamos marcar seu Discovery</h1>
            <div className="empty-state mt-4">
              <strong className="mb-1 block text-ink">Nenhum horário livre nos próximos 14 dias</strong>
              Responda ao e-mail que enviamos e achamos uma data juntos.
            </div>
          </div>
        )}

        {estado.tipo === "pronto" && (
          <div className="mt-6">
            <p className="text-xs text-muted">{estado.conta}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">Vamos marcar seu Discovery</h1>
            <p className="mt-2 text-sm text-muted">
              São de 5 a 7 dias percorrendo seu processo com quem o executa. Escolha o melhor horário para a
              primeira conversa.
            </p>

            {avisoDeCorrida && <p role="alert" className="alert--error mt-4">{avisoDeCorrida}</p>}

            <div className="mt-4 grid gap-4">
              {agruparPorDia(estado.slots).map(grupo => (
                <div key={grupo.chave}>
                  <p className="text-xs font-bold text-ink">{diaFormatado(grupo.primeiro)}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {grupo.horarios.map(slot => (
                      <button
                        key={slot}
                        type="button"
                        aria-pressed={selecionado === slot}
                        onClick={() => setSelecionado(slot)}
                        className={`slot${selecionado === slot ? " slot--on" : ""}`}
                      >
                        {horaFormatada(slot)}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <button
              type="button"
              className="btn mt-6 w-full"
              disabled={!selecionado || enviando}
              onClick={() => void confirmar()}
            >
              {selecionado ? `Confirmar ${horaFormatada(selecionado)} de ${diaDaSemana(selecionado)}` : "Escolha um horário"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
