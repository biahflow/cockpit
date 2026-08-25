import pulseMarkInverseUrl from "../assets/brand/pulse-mark-inverse.svg";
import pulseMarkUrl from "../assets/brand/pulse-mark.svg";

type PulseBrandProps = {
  /** `null` suprime a linha de subtítulo. É o lockup denso: mark + wordmark, nada abaixo. */
  subtitle?: string | null;
  /**
   * `"dark"` troca o mark pela variante invertida. O clay `#BD4A30` sobre `brand-900` `#5C2317`
   * dá **2,45:1** e o mark some; o tile branco dá 12,3:1 (DAP GH-26 r1).
   */
  tone?: "light" | "dark";
};

export function PulseBrand({ subtitle = "Operação Biahflow", tone = "light" }: PulseBrandProps) {
  const isDark = tone === "dark";
  return (
    <span className="inline-flex items-center gap-2.5">
      {/* O `<img>` é decorativo e o wordmark é **sempre** visível, de modo que o `<a href="/">` que
          embrulha o lockup nunca fica sem nome acessível — a violação `link-name` do axe que o
          componente da PR #27 carregava (DAP GH-26 r1, decisão 6).

          O conserto é a **ausência de um modo**, não um `sr-only` condicional. Havia um `compact`
          que escondia o wordmark e nenhuma das quatro chamadas o usava: um nome que só existe para
          leitor de tela é o primeiro a divergir do wordmark quando alguém troca um dos dois, e um
          ramo sem chamador é a mesma dívida que classe sem consumidor (ADR 0043). `subtitle={null}`
          já dá a versão densa, que é a única compressão que este produto pediu. */}
      <img src={isDark ? pulseMarkInverseUrl : pulseMarkUrl} alt="" aria-hidden="true" className="size-8 shrink-0" />
      <span className="min-w-0">
        <strong className={`type-title block tracking-[-0.03em] ${isDark ? "text-white" : "text-ink"}`}>
          Pulse
        </strong>
        {subtitle && <small className={`type-meta block truncate ${isDark ? "text-white/80" : "text-muted"}`}>{subtitle}</small>}
      </span>
    </span>
  );
}
