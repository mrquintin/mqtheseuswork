/**
 * Design tokens — Amber Oracle.
 *
 * These values are not invented here. They are a JS-side projection of the
 * CSS custom properties already declared in `src/app/globals.css`. The CSS
 * remains the source of truth at runtime; this file exists so that
 *
 *   1. TS code can reference `tokens.color.amber` instead of the raw string
 *      `"var(--amber)"` (typo-resistant, autocompletes), and
 *   2. the lint script (`scripts/check_no_hardcoded_colors.py`) has a single
 *      machine-readable list of approved color references to grep against.
 *
 * If you add a new color, add it in `globals.css` first, then mirror the
 * reference here. Don't introduce raw hex literals in this file unless the
 * value is also declared in `globals.css` (and even then, prefer the CSS
 * variable form).
 */

/* ── Palette ─────────────────────────────────────────────────────────────
 * Every entry is a CSS `var(--name)` reference. Both light and dark themes
 * are served by the same names; the value flips at the `:root` /
 * `[data-theme="light"]` level.
 */
/* WCAG 2.1 AA targets the design system commits to:
 *   - Body text vs. surface:  ≥ 4.5:1
 *   - Large text (≥ 18pt or 14pt bold) vs. surface: ≥ 3:1
 *   - UI components, focus rings, hairlines: ≥ 3:1
 * Contrast figures below are measured against `--stone` (the canonical
 * background) in both light and dark themes. They were audited in the
 * Accessibility_Survey pass; update them when a token shifts.
 */
export const color = {
  // Surfaces (background ladder, darkest → lightest in dark mode)
  stone: "var(--stone)",
  stoneLight: "var(--stone-light)",
  stoneMid: "var(--stone-mid)",
  ink: "var(--ink)",

  // Accent ladder — `amber` is the primary link/highlight color.
  // contrast(amber, stone) = 9.8:1 dark / 7.3:1 light → passes AA + AAA for body.
  amber: "var(--amber)",
  amberDim: "var(--amber-dim)", // 5.0:1 dark / 4.7:1 light — AA body, not AAA.
  amberDeep: "var(--amber-deep)", // ⚠ 2.6:1 dark — UI/border only, never body text.
  amberGlow: "var(--amber-glow)",

  // Legacy aliases — already present in globals.css, kept so consumers that
  // still say `var(--gold)` aren't flagged by the lint.
  gold: "var(--gold)",
  goldDim: "var(--gold-dim)",

  // Readable foreground — passes AA for body text on `--stone` in both themes.
  parchment: "var(--parchment)", // 14.7:1 dark / 14.2:1 light — AAA
  parchmentDim: "var(--parchment-dim)", // 5.4:1 dark / 5.06:1 light — AA body

  // Semantic — all pass AA for body text on `--stone`.
  ember: "var(--ember)", // 4.8:1 — error / action heat
  success: "var(--success)", // 7.4:1
  info: "var(--info)", // 4.6:1
  border: "var(--border)", // 3.0:1 against stone — UI hairlines only.

  // Currents-namespace aliases (see globals.css ~line 1415). The Currents
  // article surface uses these instead of the base tokens.
  currentsGold: "var(--currents-gold)",
  currentsAmber: "var(--currents-amber)",
  currentsBorder: "var(--currents-border)",
  currentsParchment: "var(--currents-parchment)",
  currentsParchmentDim: "var(--currents-parchment-dim)",
  currentsMuted: "var(--currents-muted)",
  currentsBgElevated: "var(--currents-bg-elevated)",
} as const;

export type ColorToken = keyof typeof color;

/* ── Spacing ─────────────────────────────────────────────────────────────
 * Pulled from the recurring rhythm in component inline-styles
 * (0.25 / 0.4 / 0.5 / 0.6 / 0.75 / 0.85 / 1 / 1.25 / 1.5 rem). Compressed
 * into a 6-step scale; everything used inline today rounds to one of these.
 */
export const space = {
  none: "0",
  xs: "0.25rem", // 4px  — gap between icon and label, pill padding-y
  sm: "0.4rem", // 6px  — gap inside small badges
  md: "0.65rem", // 10px — pill / badge padding-x
  lg: "1rem", // 16px — card padding
  xl: "1.25rem", // 20px — section padding
  "2xl": "1.5rem", // 24px — panel padding, vertical rhythm
} as const;

export type SpaceToken = keyof typeof space;

/* ── Radius ─────────────────────────────────────────────────────────────
 * Three reads:
 *   - hairline (1px, 2px) — terminals, cards (`.portal-card`, `.public-card`)
 *   - rounded (4–6px)    — popovers, badges (`.btn`, EdgeBadge wrapper)
 *   - pill (999px)       — text-on-amber pills (`MqsPill`, citation pills)
 */
export const radius = {
  none: "0",
  hairline: "2px",
  rounded: "4px",
  panel: "6px",
  pill: "999px",
} as const;

export type RadiusToken = keyof typeof radius;

/* ── Type scale ─────────────────────────────────────────────────────────
 * Three font stacks already live in globals.css:
 *   serif       — `EB Garamond` body
 *   display     — `Cinzel` headings, kickers, button labels
 *   mono        — `IBM Plex Mono` for IDs, timestamps, terminal text
 *
 * Sizes were lifted from the dense 0.6 / 0.65 / 0.7 / 0.78 / 0.85 / 0.9 / 1
 * rem cluster used throughout Round-17 components.
 */
export const font = {
  serif: "'EB Garamond', Georgia, serif",
  display: "'Cinzel', 'Palatino Linotype', serif",
  mono: "'IBM Plex Mono', 'JetBrains Mono', Menlo, monospace",
} as const;

export const fontSize = {
  micro: "0.6rem", // kicker labels, uppercase ALL CAPS chips
  caption: "0.65rem", // pill text
  meta: "0.72rem", // muted metadata
  small: "0.78rem", // tight body, badge bodies
  body: "0.9rem", // popover body
  bodyLg: "1rem",
  h3: "1.25rem",
  h2: "1.5rem",
  h1: "1.85rem",
} as const;

export const tracking = {
  tight: "0.02em", // body
  normal: "0.05em", // headings
  wide: "0.1em", // sub-labels
  wider: "0.12em", // button labels (matches `.btn`)
  widest: "0.18em", // uppercase chips, kickers
  ultrawide: "0.22em", // sorted-by-line, queue-tuning headline
} as const;

export type FontSizeToken = keyof typeof fontSize;
export type TrackingToken = keyof typeof tracking;

/* ── Elevation ──────────────────────────────────────────────────────────
 * Phosphor glow ladder from globals.css. Higher elevations are reserved
 * for focus rings and active/hover states — never decoration.
 */
export const elevation = {
  none: "none",
  sm: "var(--glow-sm)",
  md: "var(--glow-md)",
  lg: "var(--glow-lg)",
  popover: "0 18px 45px rgba(0, 0, 0, 0.38)", // matches existing CitationPopover shell
} as const;

export type ElevationToken = keyof typeof elevation;

/* ── Tone → color mapping ───────────────────────────────────────────────
 * Used by Pill, BadgeRow, EmptyState. Lives here so a single change in
 * semantic palette propagates everywhere.
 */
export const tone = {
  neutral: { fg: color.parchmentDim, border: color.border, bg: "transparent" },
  accent: { fg: color.amber, border: color.amberDim, bg: "transparent" },
  success: { fg: color.success, border: color.success, bg: "transparent" },
  warning: { fg: color.amber, border: color.amberDim, bg: "transparent" },
  danger: { fg: color.ember, border: color.ember, bg: "transparent" },
  info: { fg: color.info, border: color.info, bg: "transparent" },
} as const;

export type Tone = keyof typeof tone;

/* ── Epistemic status enum (R-002) ───────────────────────────────────────
 * Pill fills are reserved for this axis only. Other axes (severity,
 * freshness, calibration band, attribution) render through
 * `<SmallCapsLabel>` or `<NumericBadge>` — see
 * `docs/design/Design_System.md`.
 */
export const EPISTEMIC_STATUS = [
  "draft",
  "provisional",
  "published",
  "retired",
] as const;
export type EpistemicStatus = (typeof EPISTEMIC_STATUS)[number];

export const epistemicTone: Record<EpistemicStatus, Tone> = {
  draft: "neutral",
  provisional: "warning",
  published: "success",
  retired: "danger",
};

/* ── Approved color references (for the lint) ───────────────────────────
 * Flat list of every CSS `var(--…)` token the design system blesses. The
 * lint script (`scripts/check_no_hardcoded_colors.py`) reads this constant
 * via a regex; do not rename the export without updating the lint.
 */
export const APPROVED_CSS_VARS: readonly string[] = [
  "--stone",
  "--stone-light",
  "--stone-mid",
  "--ink",
  "--amber",
  "--amber-dim",
  "--amber-deep",
  "--amber-glow",
  "--gold",
  "--gold-dim",
  "--parchment",
  "--parchment-dim",
  "--ember",
  "--success",
  "--info",
  "--border",
  "--currents-gold",
  "--currents-amber",
  "--currents-border",
  "--currents-parchment",
  "--currents-parchment-dim",
  "--currents-muted",
  "--currents-bg-elevated",
  "--glow-sm",
  "--glow-md",
  "--glow-lg",
] as const;

export const tokens = {
  color,
  space,
  radius,
  font,
  fontSize,
  tracking,
  elevation,
  tone,
} as const;

export default tokens;
