import { TriangleAlert, User, X } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { api } from "../api";
import { Modal } from "./Modal";
import type { Contact, DocumentEntry, SignaturePositioningGap } from "../types";

/** O papel que a tela oferece. "Biahflow" **não** está aqui, e é decisão (DAP r1, C1): quem
 * atribui `house` é o servidor, a partir de `ESIGN_HOUSE_SIGNER_EMAIL`. Deixá-lo escolhível
 * criaria um segundo caminho para o mesmo fato — e ele poderia nomear a casa com outro e-mail. */
type PapelEscolhivel = "counterparty" | "witness";

type Signatario = { email: string; name: string; role: PapelEscolhivel };

/** A copy diz o **fato**, não a causa técnica (DAP r1, E1) — é o que a pessoa precisa saber antes
 * de clicar, e não por que o backend não achou a âncora. */
const AVISO_DA_LACUNA: Record<SignaturePositioningGap, string> = {
  not_pdf: "Este documento não é PDF. As assinaturas vão para a última página do relatório, e não sobre as linhas de assinatura.",
  kind_without_block: "Documentos desta finalidade não têm bloco de assinatura. As assinaturas vão para a última página do relatório.",
};

/** Quantas linhas de testemunha o template da casa desenha. Da terceira em diante a assinatura vai
 * **sem posição** (ADR 0065), e a tela avisa em vez de deixar isso virar surpresa.
 *
 * É **suposição aprovada**, não invariante reexpressa: quem conta as linhas de verdade é
 * `esign.posicoes_da_rodada`, lendo o PDF, e não há campo que publique esse número. O risco está
 * registrado no DAP r1 (risco 3) — se três testemunhas virarem caso comum, quem muda é o template,
 * não a tela. O número aqui **não desabilita nada**: só rotula a linha. */
const LINHAS_DE_TESTEMUNHA = 2;

/**
 * A rodada de assinatura, montada de uma vez (DAP `dap-assinatura-com-papeis-r1`, A1).
 *
 * Substitui o `window.prompt` que pedia um e-mail solto: o backend aceita N signatários com papel
 * numa chamada desde a ADR 0065, e o primeiro contrato real da casa teve três.
 *
 * **A casa não vai no corpo.** O servidor a acrescenta a partir de `ESIGN_HOUSE_SIGNER_EMAIL`, e
 * mandá-la daqui seria o segundo caminho para o mesmo fato — além de repetir o e-mail que o
 * próprio servidor recusa com 400. A linha dela existe porque *aceitar exige todos* (D1): quem
 * envia precisa saber quantas assinaturas o documento vai esperar.
 */
export function RequestSignatureModal({ document, houseEmail, onClose, onSent }: {
  document: DocumentEntry;
  houseEmail: string | null;
  onClose: () => void;
  onSent: () => Promise<void>;
}) {
  const [signers, setSigners] = useState<Signatario[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [novoEmail, setNovoEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // A conta-dona vem **derivada** do servidor (`owning_account`): reexpressar aqui a cadeia
    // conta → oportunidade → projeto seria a segunda definição de "de quem é este documento".
    if (document.owning_account === null) return;
    // Falhar a busca não quebra o modal: o caminho do e-mail digitado continua de pé, e um
    // alerta vermelho aqui diria que o envio deu errado quando nada foi enviado.
    api<Contact[]>(`/contacts/?account=${document.owning_account}`).then(setContacts).catch(() => setContacts([]));
  }, [document.owning_account]);

  const casa = (houseEmail ?? "").toLowerCase();
  const naRodada = new Set(signers.map(signer => signer.email.toLowerCase()));
  const disponiveis = contacts.filter(
    contact => contact.email && !naRodada.has(contact.email.toLowerCase()) && contact.email.toLowerCase() !== casa,
  );
  const total = signers.length + (houseEmail ? 1 : 0);

  function acrescentar(email: string, name: string): boolean {
    const limpo = email.trim();
    if (!limpo) return false;
    if (naRodada.has(limpo.toLowerCase()) || limpo.toLowerCase() === casa) {
      setError("Este e-mail já está na rodada.");
      return false;
    }
    setError("");
    setSigners([...signers, { email: limpo, name, role: "counterparty" }]);
    return true;
  }

  function acrescentarDigitado(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (acrescentar(novoEmail, "")) setNovoEmail("");
  }

  async function enviar() {
    setBusy(true); setError("");
    try {
      await api(`/documents/${document.id}/request-signature/`, {
        method: "POST",
        // A ordem enviada **é** a ordem das linhas no documento (ADR 0065), então o array vai
        // como está na tela. A casa fica de fora: quem a acrescenta é o servidor.
        body: JSON.stringify({ signers: signers.map(({ email, role }) => ({ email, role })) }),
      });
      await onSent();
      onClose();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  // A ordem da lista **é** a ordem das linhas do documento (ADR 0065): a enésima testemunha ocupa
  // a linha n, e `0` marca quem não é testemunha. Derivado aqui, e não contado dentro do JSX.
  let contadas = 0;
  const linhaDaTestemunha = signers.map(signer => signer.role === "witness" ? ++contadas : 0);

  return <Modal title="Enviar para assinatura" width="2xl" onClose={onClose}>
    <p className="mb-5 text-sm text-muted">{document.original_name}</p>
    {document.signature_positioning_gap && <div role="status" className="alert--warn mb-4 flex items-start gap-2.5">
      <TriangleAlert className="mt-0.5 size-4 shrink-0" />
      <span>{AVISO_DA_LACUNA[document.signature_positioning_gap]}</span>
    </div>}
    {error && <p role="alert" className="alert--error mb-4">{error}</p>}

    {(houseEmail || signers.length > 0) && <div className="panel panel--flush">
      <div className="panel-rows">
        {houseEmail && <div className="row bg-slate-50">
          <span className="metric-icon"><User className="size-4" /></span>
          <div className="row-main">
            <strong>Você (Biahflow)</strong>
            <span>{houseEmail} · assina como a casa</span>
          </div>
          <span className="state state--off">Fixo</span>
        </div>}
        {signers.map((signer, indice) => {
          const linha = linhaDaTestemunha[indice];
          return <div className="row" key={signer.email}>
            <span className="metric-icon"><User className="size-4" /></span>
            <div className="row-main">
              <strong>{signer.name || signer.email}</strong>
              {signer.name && <span>{signer.email}</span>}
            </div>
            {/* Em 390px o par desce para a própria linha e o seletor toma a largura (board, §5):
                inline num `.row` estreito, o nome ficaria espremido a quase zero por ser o único
                item encolhível da faixa. */}
            <div className="flex w-full items-center gap-3 sm:w-auto">
              <select
                className="field flex-1 sm:w-auto sm:flex-none"
                aria-label={`Papel de ${signer.email}`}
                value={signer.role}
                onChange={event => setSigners(signers.map((item, posicao) => posicao === indice
                  ? { ...item, role: event.target.value as PapelEscolhivel }
                  : item))}
              >
                <option value="counterparty">Parte contratante</option>
                <option value="witness">Testemunha</option>
              </select>
              <button
                type="button" className="btn btn--secondary btn--icon"
                aria-label={`Remover ${signer.email}`}
                onClick={() => { setError(""); setSigners(signers.filter((_, posicao) => posicao !== indice)); }}
              ><X className="size-4" /></button>
            </div>
            {linha > 0 && <div className="row-meta">
              <span className="type-meta text-muted">{linha <= LINHAS_DE_TESTEMUNHA
                ? <>Ocupa a <strong>linha {linha}</strong> de testemunha do documento</>
                : "Sem linha de testemunha no documento — a assinatura vai sem posição"}</span>
            </div>}
          </div>;
        })}
      </div>
    </div>}

    {signers.length === 0 && <div className="empty-state mt-4">
      Nenhum signatário do cliente ainda. Escolha um contato da conta ou informe um e-mail.
    </div>}

    {disponiveis.length > 0 && <label className="form-label mt-4">Contato da conta
      <select className="field" value="" onChange={event => {
        const escolhido = disponiveis.find(contact => String(contact.id) === event.target.value);
        if (escolhido) acrescentar(escolhido.email, escolhido.name);
      }}>
        <option value="">Selecione um contato…</option>
        {disponiveis.map(contact => <option key={contact.id} value={contact.id}>{contact.name} · {contact.email}</option>)}
      </select>
    </label>}

    <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={acrescentarDigitado}>
      <label className="form-label min-w-0 flex-1">Ou informe um e-mail
        <input className="field" type="email" value={novoEmail} onChange={event => setNovoEmail(event.target.value)} placeholder="pessoa@empresa.com.br" />
      </label>
      <button type="submit" className="btn btn--secondary">Adicionar</button>
    </form>

    <div className="mt-6 flex flex-wrap justify-end gap-3">
      <button type="button" className="btn btn--secondary" onClick={onClose}>Cancelar</button>
      {/* Desabilitado com zero signatários do cliente: a casa sozinha não é uma rodada, e um
          botão vivo para um `POST` que o servidor recusa é o defeito que o `CLAUDE.md` nomeia. */}
      <button type="button" className="btn" disabled={busy || signers.length === 0} onClick={() => void enviar()}>
        {signers.length === 0 ? "Enviar" : `Enviar para ${total} ${total === 1 ? "signatário" : "signatários"}`}
      </button>
    </div>
  </Modal>;
}
