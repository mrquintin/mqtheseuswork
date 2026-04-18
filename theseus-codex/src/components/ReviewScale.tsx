"use client";

import { useCallback } from "react";
import AsciiCanvas from "./AsciiCanvas";
import { CELL_H, CELL_W } from "@/lib/ascii/shapeVectors";

/**
 * A small ASCII balance-scale that tips according to how the six
 * coherence layers voted on a claim pair. One pan rises when the
 * cohere-side outweighs the contradict-side and vice versa.
 *
 * Rendered inline on each row of `/peer-review`, making the disagreement
 * structure legible at a glance — you can see "this one is tilting hard
 * toward contradict" from 6 feet away, without parsing the JSON.
 *
 * Inputs:
 *   - `cohereCount` and `contradictCount` — the raw layer-verdict tallies
 *     (0..6 each). The "unresolved" layers don't add to either side and
 *     therefore don't tip the scale.
 *   - `severity` — 0..1; controls the amber saturation of the fulcrum.
 *
 * The animation is a subtle ongoing bob: the scale settles to its tip
 * angle but overshoots slightly, suggesting it hasn't come to rest.
 * That's intentional; an *open* review item hasn't come to rest.
 */

export type ReviewScaleProps = {
  cohereCount: number;
  contradictCount: number;
  severity?: number;
  cols?: number;
  rows?: number;
  ariaLabel?: string;
};

export default function ReviewScale({
  cohereCount,
  contradictCount,
  severity = 0.5,
  cols = 22,
  rows = 8,
  ariaLabel = "Balance of coherence-layer verdicts",
}: ReviewScaleProps) {
  const width = cols * CELL_W;
  const height = rows * CELL_H;
  const S = Math.max(0, Math.min(1, severity));

  // Target tip in radians. Max ~0.45 rad (~26°) so the pans don't fly off
  // the canvas at an extreme 6-vs-0 split.
  const diff = contradictCount - cohereCount; // negative → tip toward cohere (right pan heavier)
  const maxSwing = 0.45;
  const targetTip = Math.max(-maxSwing, Math.min(maxSwing, (diff / 6) * maxSwing * 2));

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const t = timeMs / 1000;
      ctx.clearRect(0, 0, width, height);

      // Bob the target slightly so the scale never looks frozen. A small
      // slow oscillation around the target reads as "not quite at rest".
      const tip = targetTip + Math.sin(t * 0.9) * 0.04 * (1 - Math.abs(diff) / 6);

      const cx = width / 2;
      const fulcrumY = height * 0.6;

      // Fulcrum post (the vertical rod the beam balances on).
      ctx.strokeStyle = `rgba(255, 220, 160, ${0.7 + S * 0.3})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, fulcrumY);
      ctx.lineTo(cx, height * 0.92);
      ctx.stroke();

      // Base plate.
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(cx - 5, height * 0.92);
      ctx.lineTo(cx + 5, height * 0.92);
      ctx.stroke();

      // Beam — rotated at `tip`. The two endpoints are reached by rotating
      // (±armLen, 0) around (cx, fulcrumY).
      const armLen = width * 0.38;
      const cosT = Math.cos(tip);
      const sinT = Math.sin(tip);
      const leftEnd = { x: cx - armLen * cosT, y: fulcrumY - armLen * sinT };
      const rightEnd = { x: cx + armLen * cosT, y: fulcrumY + armLen * sinT };

      ctx.strokeStyle = `rgba(255, 200, 120, ${0.9})`;
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(leftEnd.x, leftEnd.y);
      ctx.lineTo(rightEnd.x, rightEnd.y);
      ctx.stroke();

      // Pans — one hangs from each end. Drawn as short vertical chains
      // plus a semicircle pan at the bottom.
      const hangLen = 5;
      const panR = 4;
      for (const end of [leftEnd, rightEnd]) {
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(end.x, end.y);
        ctx.lineTo(end.x, end.y + hangLen);
        ctx.stroke();
        // Pan: half-circle opening upward
        ctx.beginPath();
        ctx.arc(end.x, end.y + hangLen + 1, panR, 0, Math.PI, false);
        ctx.stroke();
      }

      // Verdict count weights — small blocks on each pan, one per vote.
      // Makes the numbers legible without a legend.
      const drawWeights = (baseX: number, baseY: number, n: number) => {
        for (let i = 0; i < n; i++) {
          const row = Math.floor(i / 3);
          const col = i % 3;
          const bx = baseX - 3 + col * 2;
          const by = baseY - 2 - row * 2;
          ctx.fillStyle = `rgba(255, 230, 180, 0.95)`;
          ctx.fillRect(bx, by, 1.4, 1.4);
        }
      };
      drawWeights(leftEnd.x, leftEnd.y + hangLen + 1 - panR + 1, contradictCount);
      drawWeights(rightEnd.x, rightEnd.y + hangLen + 1 - panR + 1, cohereCount);

      // Tiny labels — single glyphs at each pan to disambiguate.
      ctx.fillStyle = `rgba(200, 170, 120, 0.85)`;
      ctx.font = `${Math.floor(CELL_H * 0.9)}px "IBM Plex Mono", monospace`;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      ctx.fillText("✕", leftEnd.x, leftEnd.y + hangLen + 7); // contradict
      ctx.fillText("∙", rightEnd.x, rightEnd.y + hangLen + 7); // cohere (quieter glyph)
    },
    [width, height, targetTip, diff, S, cohereCount, contradictCount],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.6}
      ariaLabel={ariaLabel}
    />
  );
}
