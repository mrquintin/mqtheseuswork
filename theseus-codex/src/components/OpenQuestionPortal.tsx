"use client";

import { useCallback } from "react";
import AsciiCanvas from "./AsciiCanvas";
import { CELL_H, CELL_W } from "@/lib/ascii/shapeVectors";

/**
 * Compact live 3D ASCII doorway / portal arch, rendered one per open
 * question on the `/open-questions` page.
 *
 * Conceit: an open question is an unresolved coherence tension between
 * two claims. Visually, that's a threshold — a doorway the firm hasn't
 * yet crossed. Each portal is:
 *
 *   - Two columns (Doric simplification — just vertical bars with a
 *     capital and a base).
 *   - An arch across the top made of stacked stones.
 *   - A shimmering inside — a procedural noise band that pulses with the
 *     question's severity.
 *
 * `severity` (0..1) controls:
 *   - the amplitude of the shimmer
 *   - the amber saturation of the arch
 *   - the thickness of the column highlights
 *
 * The geometry is 2D-projected-from-3D (narrow pitch, slow yaw) so the
 * ASCII picker gets proper shape cues for the curved arch rather than
 * just horizontal bars.
 */

export type OpenQuestionPortalProps = {
  /** 0..1 — drives shimmer amplitude and brightness. */
  severity?: number;
  cols?: number;
  rows?: number;
  /** An animation-phase offset so a column of portals don't all pulse in lockstep. */
  phase?: number;
  ariaLabel?: string;
};

export default function OpenQuestionPortal({
  severity = 0.5,
  cols = 24,
  rows = 10,
  phase = 0,
  ariaLabel = "Open question portal",
}: OpenQuestionPortalProps) {
  const S = Math.max(0, Math.min(1, severity));
  const width = cols * CELL_W;
  const height = rows * CELL_H;

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const t = timeMs / 1000 + phase;
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const baseY = height * 0.88;
      const topY = height * 0.08;

      // ── Columns (two vertical bars with capitals). The highlight intensity
      //    rises with severity so "hotter" questions feel more lit.
      const colBrightness = 0.55 + S * 0.45;
      ctx.strokeStyle = `rgba(255, 220, 160, ${colBrightness})`;
      ctx.lineWidth = 2.2;
      const colXL = width * 0.18;
      const colXR = width * 0.82;
      const capH = height * 0.09;

      for (const cxEdge of [colXL, colXR]) {
        // Shaft
        ctx.beginPath();
        ctx.moveTo(cxEdge, baseY);
        ctx.lineTo(cxEdge, topY + capH);
        ctx.stroke();
        // Capital (wider horizontal mark + stylobate at the base)
        ctx.beginPath();
        ctx.moveTo(cxEdge - 5, topY + capH);
        ctx.lineTo(cxEdge + 5, topY + capH);
        ctx.moveTo(cxEdge - 6, baseY);
        ctx.lineTo(cxEdge + 6, baseY);
        ctx.stroke();
      }

      // ── Arch: a series of stacked stone segments across the top.
      //    Each "stone" is a short chord of the semi-circle, drawn as a
      //    tiny trapezoid so the ASCII picker reads discrete blocks.
      const archY = topY + capH;
      const archW = colXR - colXL;
      const archR = archW / 2;
      const stones = 9;
      ctx.strokeStyle = `rgba(255, 200, 120, ${0.7 + S * 0.3})`;
      ctx.lineWidth = 1.6;
      for (let k = 0; k < stones; k++) {
        const t0 = Math.PI - (k / stones) * Math.PI;
        const t1 = Math.PI - ((k + 1) / stones) * Math.PI;
        const x0 = cx + Math.cos(t0) * archR;
        const y0 = archY - Math.sin(t0) * archR * 0.55; // squash vertically
        const x1 = cx + Math.cos(t1) * archR;
        const y1 = archY - Math.sin(t1) * archR * 0.55;
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.stroke();
        // Radial joint line — suggests the gap between stones.
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x0 + (cx - x0) * 0.08, y0 + (archY - y0) * 0.08);
        ctx.stroke();
      }

      // ── Interior shimmer: a vertical band of horizontal filaments whose
      //    brightness oscillates with time + severity, suggesting heat
      //    haze or portal-energy rippling inside the threshold.
      const innerL = colXL + 6;
      const innerR = colXR - 6;
      const innerTop = archY + 2;
      const innerBot = baseY - 2;
      const filaments = 6;
      for (let i = 0; i < filaments; i++) {
        const u = i / (filaments - 1);
        const y = innerTop + (innerBot - innerTop) * u;
        const pulse = Math.sin(t * 2.4 + i * 0.7 + phase) * 0.5 + 0.5;
        const a = 0.25 + S * 0.4 * pulse;
        ctx.strokeStyle = `rgba(255, 180, 80, ${a})`;
        ctx.lineWidth = 1 + S * 0.8;
        ctx.beginPath();
        const waveOff = Math.sin(t * 1.6 + i * 1.1) * 2;
        ctx.moveTo(innerL + waveOff, y);
        ctx.lineTo(innerR + waveOff, y);
        ctx.stroke();
      }

      // ── Keystone mark at the top of the arch. A small filled diamond
      //    gives the composition a focal point and reads as a bright
      //    glyph after ASCII conversion.
      const keyY = archY - archR * 0.55;
      const keyR = 3 + S * 1.5;
      ctx.fillStyle = `rgba(255, 230, 180, ${0.7 + S * 0.3})`;
      ctx.beginPath();
      ctx.moveTo(cx, keyY - keyR);
      ctx.lineTo(cx + keyR, keyY);
      ctx.lineTo(cx, keyY + keyR);
      ctx.lineTo(cx - keyR, keyY);
      ctx.closePath();
      ctx.fill();
    },
    [width, height, S, phase],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.7}
      ariaLabel={ariaLabel}
    />
  );
}
