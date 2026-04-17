/**
 * The Cretan labyrinth — the classical seven-course unicursal maze Theseus
 * walked to the Minotaur and back. Used as the site's logo / favicon.
 *
 * Rendered as inline SVG so it inherits color via `currentColor`. The path
 * is the standard "walls" (concentric arcs) minus the entrance gap at the
 * bottom. When you trace from the outside, there's exactly one path through
 * to the center — which is the whole point of this symbol.
 *
 * Props:
 *   - `size`   — px; default 28
 *   - `color`  — override; defaults to currentColor
 *   - `glow`   — apply amber drop-shadow when true
 */

export default function LabyrinthIcon({
  size = 28,
  color,
  glow = false,
  className,
}: {
  size?: number;
  color?: string;
  glow?: boolean;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Theseus labyrinth"
      className={className}
      style={{
        color: color ?? "currentColor",
        filter: glow ? "drop-shadow(0 0 4px var(--amber-glow))" : undefined,
      }}
    >
      {/* Concentric walls (outer → inner). Each one has a strategic gap so
          the path from the entrance at the bottom winds through in classic
          labyrinth order. Stroke uses currentColor, width scales with size. */}
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="square"
      >
        {/* Outer ring with bottom entrance */}
        <path d="M 32 4 A 28 28 0 1 1 31.99 4" />
        <line x1="30" y1="60" x2="34" y2="60" stroke="var(--stone)" strokeWidth="5" />

        {/* Ring 2 */}
        <path d="M 32 10 A 22 22 0 1 1 31.99 10" />
        <line x1="26" y1="54" x2="38" y2="54" stroke="var(--stone)" strokeWidth="4" />

        {/* Ring 3 */}
        <path d="M 32 16 A 16 16 0 1 1 31.99 16" />
        <line x1="32" y1="48" x2="42" y2="48" stroke="var(--stone)" strokeWidth="4" />

        {/* Ring 4 */}
        <path d="M 32 22 A 10 10 0 1 1 31.99 22" />
        <line x1="24" y1="42" x2="32" y2="42" stroke="var(--stone)" strokeWidth="4" />

        {/* Inner chamber — the center of the maze where the Minotaur lived.
            Drawn as a filled dot so it reads as the destination. */}
        <circle cx="32" cy="32" r="3" fill="currentColor" />
      </g>
    </svg>
  );
}
