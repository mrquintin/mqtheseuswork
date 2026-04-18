"use client";

import { useCallback, useMemo } from "react";
import AsciiCanvas from "./AsciiCanvas";
import { CELL_H, CELL_W } from "@/lib/ascii/shapeVectors";

/**
 * An ancient scroll (papyrus volumen), rendered as live 3D ASCII and used
 * as a decorative banner at the top of the upload page.
 *
 * Why this redesign
 * -----------------
 * The first version of this component put small rollers at the ends of
 * the parchment and several horizontal filaments between them. Rendered
 * as ASCII that read as "horizontal stripes", not "scroll" — and because
 * it sat *behind* the dropzone text in the same amber, it competed with
 * the form copy. Two concrete fixes here:
 *
 *   1. Geometry. The rolls are now the dominant visual element. Each end
 *      is a proper cylinder (radius ~0.35 of the parchment width) with
 *      visible top/bottom caps, a side wall, and a spiral pattern on the
 *      exposed face that reads as rolled-up paper. The parchment between
 *      them is shorter (narrower vertically than the rolls are tall) and
 *      carries vertical columns of short glyphs — the classical arrangement
 *      of written Greek/Latin in a volumen, and unmistakable as "written
 *      scroll" after ASCII conversion.
 *
 *   2. Intensity. The component now defaults to `--amber-dim` rather than
 *      `--amber`, so when placed near form copy it reads as a background
 *      artifact rather than competing. Active drag bumps it to full
 *      `--amber` for ~0.5s — the drag transition itself is the moment
 *      we want user attention pulled toward the scroll.
 *
 * The component is no longer placed behind the dropzone — the upload form
 * now renders it as a top banner. See UploadForm.tsx.
 */

export type UploadScrollProps = {
  /** Brighten + agitate while the user drags a file. */
  active?: boolean;
  /** Render a wax seal hanging below — true once a file has been selected. */
  sealed?: boolean;
  cols?: number;
  rows?: number;
  ariaLabel?: string;
};

type Vec3 = [number, number, number];

function project3D(
  [x, y, z]: Vec3,
  yaw: number,
  pitch: number,
  cx: number,
  cy: number,
  scale: number,
): { x: number; y: number; depth: number } {
  const cy_ = Math.cos(yaw);
  const sy_ = Math.sin(yaw);
  const x1 = x * cy_ + z * sy_;
  const z1 = -x * sy_ + z * cy_;
  const y1 = y;
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  const y2 = y1 * cp - z1 * sp;
  const z2 = y1 * sp + z1 * cp;
  return { x: cx + x1 * scale, y: cy - y2 * scale, depth: z2 };
}

export default function UploadScroll({
  active = false,
  sealed = false,
  cols = 64,
  rows = 18,
  ariaLabel = "An ancient scroll, unrolled to receive your contribution",
}: UploadScrollProps) {
  const width = cols * CELL_W;
  const height = rows * CELL_H;

  // Pre-compute ring geometry for the two rolls. Each roll is a vertical
  // cylinder: top cap ring, bottom cap ring, and meridians between them.
  // Keeping this out of the render loop avoids rebuilding 60 points/frame.
  const rollGeom = useMemo(() => {
    const segs = 14;
    const rolls: {
      cx: number; // world-space x of the roll's axis
      topRing: Vec3[];
      botRing: Vec3[];
      // Spiral on the end cap — rendered as concentric shrinking ellipses
      // so the exposed face of the roll reads as coiled paper.
      spiral: Vec3[];
    }[] = [];

    const R = 0.36; // roll radius
    const H = 0.95; // roll height (vertical extent)

    for (const cx of [-1.45, 1.45]) {
      const top: Vec3[] = [];
      const bot: Vec3[] = [];
      for (let i = 0; i < segs; i++) {
        const t = (i / segs) * Math.PI * 2;
        const dy = 0; // flat ring (no curve along the cap)
        const dx = Math.cos(t) * R;
        const dz = Math.sin(t) * R;
        top.push([cx + dx, H / 2 + dy, dz]);
        bot.push([cx + dx, -H / 2 - dy, dz]);
      }
      // Spiral — a flat coil on the top cap. Renders as nested ovals that
      // read as the end of a rolled piece of paper.
      const spiral: Vec3[] = [];
      const coils = 3;
      const spiralSteps = 70;
      for (let i = 0; i <= spiralSteps; i++) {
        const u = i / spiralSteps;
        const t = u * coils * Math.PI * 2;
        const r = R * (1 - u * 0.92); // shrinks toward centre
        spiral.push([cx + Math.cos(t) * r, H / 2 + 0.001, Math.sin(t) * r]);
      }
      rolls.push({ cx, topRing: top, botRing: bot, spiral });
    }
    return rolls;
  }, []);

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const t = timeMs / 1000;
      ctx.clearRect(0, 0, width, height);

      // Slight yaw + fixed downward pitch so the rolls' top caps are
      // visible (that's what makes them read as cylinders-from-above
      // rather than rectangles-seen-edge-on).
      const yaw = Math.sin(t * 0.55) * (active ? 0.11 : 0.06);
      const pitch = -0.22;

      const cx = width / 2;
      const cy = height / 2;
      const scale = Math.min(width / 3.6, height / 1.3);

      // Overall brightness — the ASCII picker uses the R channel only, so
      // "brightness" here maps directly to glyph density. Keeping the
      // scroll moderately saturated means the ASCII picker chooses middle-
      // weight glyphs (mostly `·`, `:`, `-`, `/`) rather than solid blocks,
      // which keeps the silhouette airy even when sitting above text.
      const base = active ? 0.95 : 0.68;

      // ── Rolls ─────────────────────────────────────────────────────────
      for (const roll of rollGeom) {
        // Top and bottom cap ellipses.
        const drawRing = (ring: Vec3[], lw: number, alpha: number) => {
          ctx.lineWidth = lw;
          ctx.beginPath();
          for (let i = 0; i <= ring.length; i++) {
            const p = project3D(ring[i % ring.length]!, yaw, pitch, cx, cy, scale);
            if (i === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
          }
          ctx.strokeStyle = `rgba(255, 210, 140, ${alpha * base})`;
          ctx.stroke();
        };
        drawRing(roll.topRing, 1.7, 1.0);
        drawRing(roll.botRing, 1.7, 0.85);

        // Side meridians — the vertical filaments along the cylinder body
        // that give it volume. Draw every other segment so the surface
        // reads as "paper rolled up" not "a dense barrel".
        for (let i = 0; i < roll.topRing.length; i += 2) {
          const top = project3D(roll.topRing[i]!, yaw, pitch, cx, cy, scale);
          const bot = project3D(roll.botRing[i]!, yaw, pitch, cx, cy, scale);
          const alpha = top.depth > 0 ? 0.4 : 0.85; // back-facing dim
          ctx.strokeStyle = `rgba(255, 200, 120, ${alpha * base})`;
          ctx.lineWidth = 1.1;
          ctx.beginPath();
          ctx.moveTo(top.x, top.y);
          ctx.lineTo(bot.x, bot.y);
          ctx.stroke();
        }

        // Spiral on the top cap — the distinctive "rolled paper" cue.
        ctx.strokeStyle = `rgba(255, 230, 180, ${base})`;
        ctx.lineWidth = 1.0;
        ctx.beginPath();
        for (let i = 0; i < roll.spiral.length; i++) {
          const p = project3D(roll.spiral[i]!, yaw, pitch, cx, cy, scale);
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();

        // Rod protruding on the outboard side — a short horizontal bar
        // sticking out of the roll's centre, visible as a "handle".
        const sign = roll.cx < 0 ? -1 : 1;
        const rodIn = project3D(
          [roll.cx + sign * 0.02, 0, 0],
          yaw,
          pitch,
          cx,
          cy,
          scale,
        );
        const rodOut = project3D(
          [roll.cx + sign * 0.5, 0, 0],
          yaw,
          pitch,
          cx,
          cy,
          scale,
        );
        ctx.strokeStyle = `rgba(255, 215, 150, ${base})`;
        ctx.lineWidth = 2.1;
        ctx.beginPath();
        ctx.moveTo(rodIn.x, rodIn.y);
        ctx.lineTo(rodOut.x, rodOut.y);
        ctx.stroke();

        // Rod end cap (a tiny perpendicular tick) so the rod doesn't just
        // peter out into empty space.
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(rodOut.x, rodOut.y - 4);
        ctx.lineTo(rodOut.x, rodOut.y + 4);
        ctx.stroke();
      }

      // ── Parchment sheet between the rolls ──────────────────────────────
      // Width extends from just inside the left roll to just inside the
      // right roll. Height is about half the roll's height, so the paper
      // reads as a ribbon spanning the two coils.
      const paperLX = -1.45 + 0.36;
      const paperRX = 1.45 - 0.36;
      const paperTopY = 0.3;
      const paperBotY = -0.3;

      // Top edge — slightly wavy (ragged torn-papyrus feel).
      const raggedSteps = 50;
      const drawEdge = (y0: number, amp: number, phase: number) => {
        ctx.strokeStyle = `rgba(255, 210, 140, ${base * 0.85})`;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        for (let s = 0; s <= raggedSteps; s++) {
          const u = s / raggedSteps;
          const x = paperLX + (paperRX - paperLX) * u;
          const wave = Math.sin(u * 18 + phase) * amp;
          const y = y0 + wave;
          const p = project3D([x, y, 0], yaw, pitch, cx, cy, scale);
          if (s === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      };
      drawEdge(paperTopY, 0.012, t * 0.4);
      drawEdge(paperBotY, 0.012, t * 0.4 + Math.PI);

      // Vertical columns of "text" — short horizontal ticks stacked in
      // each column. This is the single most recognisable cue for
      // "Greek/Latin manuscript" and the reason the old design wasn't
      // reading as a scroll: the old version had horizontal filaments
      // across the paper, which doesn't look like writing.
      const columns = 10;
      const ticksPerCol = 8;
      ctx.strokeStyle = `rgba(255, 220, 160, ${base * 0.9})`;
      ctx.lineWidth = 1.1;
      for (let c = 0; c < columns; c++) {
        const u = (c + 0.5) / columns;
        const x = paperLX + (paperRX - paperLX) * u;
        for (let k = 0; k < ticksPerCol; k++) {
          const v = (k + 0.5) / ticksPerCol;
          const y = paperBotY + (paperTopY - paperBotY) * v;
          // Slight length variation so the script looks handwritten.
          const len = 0.045 + Math.sin(c * 1.3 + k * 0.7) * 0.012;
          const p0 = project3D([x - len, y, 0], yaw, pitch, cx, cy, scale);
          const p1 = project3D([x + len, y, 0], yaw, pitch, cx, cy, scale);
          ctx.beginPath();
          ctx.moveTo(p0.x, p0.y);
          ctx.lineTo(p1.x, p1.y);
          ctx.stroke();
        }
      }

      // ── Wax seal (only when a file has been chosen) ────────────────────
      // Hangs below the scroll on a short ribbon — visually definitive
      // "you have committed this", stronger than a filename in a text box.
      if (sealed) {
        const ribbonTop = project3D([0, paperBotY, 0], yaw, pitch, cx, cy, scale);
        const ribbonBot = project3D(
          [0, paperBotY - 0.35, 0],
          yaw,
          pitch,
          cx,
          cy,
          scale,
        );
        // Ribbon
        ctx.strokeStyle = `rgba(200, 80, 40, 0.9)`;
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.moveTo(ribbonTop.x, ribbonTop.y);
        ctx.lineTo(ribbonBot.x, ribbonBot.y);
        ctx.stroke();
        // Seal disc
        const R = 8;
        ctx.fillStyle = `rgba(210, 70, 35, 0.96)`;
        ctx.beginPath();
        ctx.arc(ribbonBot.x, ribbonBot.y + R - 2, R, 0, Math.PI * 2);
        ctx.fill();
        // Cross-burst on the seal
        ctx.strokeStyle = `rgba(255, 220, 170, 1)`;
        ctx.lineWidth = 1;
        for (let k = 0; k < 6; k++) {
          const ang = (k / 6) * Math.PI * 2 + t * 0.25;
          ctx.beginPath();
          ctx.moveTo(ribbonBot.x, ribbonBot.y + R - 2);
          ctx.lineTo(
            ribbonBot.x + Math.cos(ang) * R * 0.9,
            ribbonBot.y + R - 2 + Math.sin(ang) * R * 0.9,
          );
          ctx.stroke();
        }
      }
    },
    [width, height, rollGeom, active, sealed],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      // Default to amber-dim so the scroll reads as a background artifact
      // rather than competing with form copy. Drag-active state bumps to
      // full amber automatically via the `active`-scaled `base` factor in
      // `render()` above.
      color="var(--amber-dim)"
      contrast={1.9}
      ariaLabel={ariaLabel}
      style={{ display: "flex", justifyContent: "center" }}
    />
  );
}
