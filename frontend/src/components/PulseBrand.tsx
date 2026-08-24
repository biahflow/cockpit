import pulseMarkUrl from "../assets/brand/pulse-mark.svg";

type PulseBrandProps = {
  compact?: boolean;
  subtitle?: string;
};

export function PulseBrand({ compact = false, subtitle = "Biahflow operational command center" }: PulseBrandProps) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <img src={pulseMarkUrl} alt="" aria-hidden="true" className="size-8 shrink-0" />
      {!compact && (
        <span className="min-w-0">
          <strong className="block text-[17px] font-semibold leading-tight tracking-[-0.03em] text-ink">
            Pulse
          </strong>
          <small className="block truncate text-[11px] leading-4 text-muted">{subtitle}</small>
        </span>
      )}
    </span>
  );
}
