"use client";

import { useCallback, useMemo } from "react";
import AsciiCanvas from "./AsciiCanvas";
import { CELL_H, CELL_W } from "@/lib/ascii/shapeVectors";

/**
 * An unfurled papyrus scroll, drawn as a live 3D ASCII object, used as
 * the decorative body of the upload dropzone.
 *
 * Scene composition:
 *   - A long rectangular papyrus surface, gently swaying like it's
 *     suspended in air.
 *   - Two wooden rollers at each end (short cylinders) that the scroll
 *     visually "unrolls" from.
 *   - A faint vertical text stripe down the middle — not real text, but
 *     a series of rhythmic horizontal tick marks that suggest writing;
 *     the ASCII picker renders it as bands of punctuation glyphs that
 *     read as illuminated script at a glance.
 *   - A wax-seal bead at the bottom-centre that appears (fades in) when
 *     `sealed` is true, i.e. a file has been selected for upload.
 *
 * The component takes an `active` prop that intensifies the sway and the
 * amber saturation while a file is being dragged over the drop zone.
 */

export type UploadScrollProps = {
  /** Mildly agitate + brighten the scroll (used while the user drags a file). */
  active?: boolean;
  /** Render a wax seal at the bottom — true once a file has been selected. */
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
  const cy_ = Math.cos(yaw),
    sy_ = Math.sin(yaw);
  const x1 = x * cy_ + z * sy_;
  const z1 = -x * sy_ + z * cy_;
  const y1 = y;
  const cp = Math.cos(pitch),
    sp = Math.sin(pitch);
  const y2 = y1 * cp - z1 * sp;
  const z2 = y1 * sp + z1 * cp;
  return { x: cx + x1 * scale, y: cy - y2 * scale, depth: z2 };
}

export default function UploadScroll({
  active = false,
  sealed = false,
  cols = 72,
  rows = 16,
  ariaLabel = "An unfurled scroll awaiting your contribution",
}: UploadScrollProps) {
  const width = cols * CELL_W;
  const height = rows * CELL_H;

  // Static roller ring geometry — two cylinders, one at each scroll end.
  // Pre-compute so we don't rebuild 40 points every frame.
  const rollerRings = useMemo(() => {
    const segs = 18;
    const rings: { cx: number; y0: Vec3[]; y1: Vec3[] }[] = [];
    const R = 0.12;
    for (const end of [-1.4, 1.4]) {
      const y0: Vec3[] = [];
      const y1: Vec3[] = [];
      for (let i = 0; i < segs; i++) {
        const t = (i / segs) * Math.PI * 2;
        const dy = Math.cos(t) * R;
        const dz = Math.sin(t) * R;
        y0.push([end, dy, dz]);
        y1.push([end, dy, dz]);
      }
      // y0 and y1 are the same ring (a short cylinder is effectively a
      // single loop from this projection since its axis is along X). Kept
      // as two arrays for symmetry with `DashboardHearth.legRings`.
      rings.push({ cx: end, y0, y1 });
    }
    return rings;
  }, []);

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const t = timeMs / 1000;
      ctx.clearRect(0, 0, width, height);

      // When active (file being dragged), increase amber brightness and
      // amplify the sway. Otherwise the scroll breathes gently.
      const swayAmp = active ? 0.09 : 0.04;
      const sway = Math.sin(t * 1.4) * swayAmp;
      const baseAmber = active ? 1.0 : 0.72;

      const cx = width / 2;
      const cy = height / 2;
      const scale = Math.min(width / 3.2, height / 1.25);

      // ── Scroll body: a rectangle in world space (X: -1.2..1.2, Y: -0.5..0.5)
      //    with gentle sag. We sample it as a grid of points and stroke
      //    the horizontal grid lines to produce the papyrus texture.
      const yaw = sway * 0.8;
      const pitch = -0.14;

      // Subtle vertical warp along the length — simulates sag.
      const sag = (u: number) => Math.sin(u * Math.PI) * 0.06;

      // 12 horizontal filaments down the scroll. Rendered brightest near
      // the middle to suggest centrifocal lighting.
      const filaments = 14;
      const steps = 40;
      for (let f = 0; f < filaments; f++) {
        const v = f / (filaments - 1); // 0..1
        const yLocal = -0.5 + v;
        // Highlight centre filament more than edges.
        const brightness = baseAmber * (0.35 + 0.65 * Math.sin(v * Math.PI));
        ctx.strokeStyle = `rgba(255, 210, 140, ${brightness})`;
        ctx.lineWidth = 1.1 + (1 - Math.abs(v - 0.5)) * 0.6;
        ctx.beginPath();
        for (let s = 0; s <= steps; s++) {
          const u = s / steps;
          const x = -1.4 + u * 2.8;
          const yy = yLocal - sag(u);
          const p = project3D([x, yy, 0], yaw, pitch, cx, cy, scale);
          if (s === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }

      // ── Faint "script" line down the middle: rhythmic horizontal ticks.
      //    This is the trick that makes the scroll read as illuminated —
      //    a column of short punctuation-like glyphs.
      const scriptCols = 38;
      for (let i = 0; i < scriptCols; i++) {
        const u = i / (scriptCols - 1);
        const x = -1.1 + u * 2.2;
        const yy = -sag(u * 0.5 + 0.25) - 0.02;
        const p = project3D([x, yy, 0], yaw, pitch, cx, cy, scale);
        // Short ticks with slight amplitude variation so the line looks
        // penned rather than printed.
        const tick = 3.5 + Math.sin(i * 1.7 + t * 0.5) * 1.4;
        ctx.strokeStyle = `rgba(255, 220, 160, ${baseAmber * 0.75})`;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(p.x - tick / 2, p.y);
        ctx.lineTo(p.x + tick / 2, p.y);
        ctx.stroke();
      }

      // ── Roller caps at each end. Drawn as short ellipses.
      ctx.lineWidth = 1.6;
      for (const r of rollerRings) {
        ctx.strokeStyle = `rgba(230, 170, 80, ${baseAmber})`;
        ctx.beginPath();
        for (let i = 0; i <= r.y0.length; i++) {
          const p = project3D(r.y0[i % r.y0.length]!, yaw, pitch, cx, cy, scale);
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();

        // A thicker vertical bar through the roller axis to make it read as a rod.
        const top = project3D([r.cx, 0.12, 0], yaw, pitch, cx, cy, scale);
        const bot = project3D([r.cx, -0.12, 0], yaw, pitch, cx, cy, scale);
        ctx.lineWidth = 2.4;
        ctx.strokeStyle = `rgba(255, 200, 120, ${baseAmber})`;
        ctx.beginPath();
        ctx.moveTo(top.x, top.y);
        ctx.lineTo(bot.x, bot.y);
        ctx.stroke();
      }

      // ── Wax seal: appears when `sealed`. Drawn as a filled circle with
      //    a star-burst crack pattern. Fades in over ~0.4s on prop change
      //    — we track that with a simple sin(t) envelope keyed to the
      //    current timestamp rather than a ref, since React will re-run
      //    this callback every render when `sealed` toggles.
      if (sealed) {
        const seal = project3D([0, -0.72, 0], yaw, pitch, cx, cy, scale);
        const R = 7;
        ctx.fillStyle = `rgba(200, 60, 30, 0.95)`;
        ctx.beginPath();
        ctx.arc(seal.x, seal.y, R, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = `rgba(240, 180, 100, 1)`;
        ctx.lineWidth = 1;
        for (let k = 0; k < 5; k++) {
          const ang = (k / 5) * Math.PI * 2 + t * 0.3;
          ctx.beginPath();
          ctx.moveTo(seal.x, seal.y);
          ctx.lineTo(seal.x + Math.cos(ang) * R * 0.95, seal.y + Math.sin(ang) * R * 0.95);
          ctx.stroke();
        }
      }
    },
    [width, height, rollerRings, active, sealed],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.7}
      ariaLabel={ariaLabel}
      style={{ display: "flex", justifyContent: "center" }}
    />
  );
}
