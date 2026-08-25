# Pulse brand assets

Canonical application brand assets for Pulse.

## Files

- `pulse-mark.svg` — canonical square mark for app shell, favicon-like surfaces and compact navigation.
- `pulse-mark-inverse.svg` — the same mark on a dark surface: white tile, clay stroke.
- `../../components/PulseBrand.tsx` — reusable application lockup combining the mark with the Pulse wordmark and optional subtitle.

## Which variant

Light surface (sidebar, mobile drawer, light auth column) uses `pulse-mark.svg`. Dark surface —
today only the login brand panel (`.auth-brand`) — uses `pulse-mark-inverse.svg`, and
`PulseBrand` selects it through `tone="dark"`.

The two files share geometry exactly: same `viewBox`, same `rx`, same path, same stroke width and
joins. Only the fill swaps. Measured in DAP GH-26 r1: clay `#BD4A30` over `brand-900` `#5C2317` is
**2,45:1** and the mark disappears; the inverted tile is 12,3:1, and the clay stroke inside the
white tile is 5,02:1. The mark is decorative (`aria-hidden`), so axe would not have caught this —
`color-contrast` measures text. It is a legibility decision, not an automatic gate.

## Design source

Aligned with the approved Pulse Design System r2:

- `brand-500`: `#BD4A30` (clay)
- white foreground for the pulse stroke
- compact operational character

The mark is a v1 application asset. Broad shell adoption remains an `INTERFACE_CHANGE` and must follow the applicable EngineeringOS Design Approval / browser validation lifecycle when required.

Do not duplicate the SVG inline across components; consume the canonical asset/component instead.
