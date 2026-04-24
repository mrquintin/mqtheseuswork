"use client";

import { useCallback, useMemo, useRef } from "react";
import AsciiCanvas from "./AsciiCanvas";
import { CELL_H, CELL_W } from "@/lib/ascii/shapeVectors";

/**
 * The Oracle's Hearth — a live 3D ASCII brazier that sits atop the
 * dashboard.
 *
 * The geometry is a bronze half-ellipsoid bowl on three stubby legs,
 * wireframe-projected from 3D to 2D the same way `AsciiHero` handles the
 * armillary sphere. On top of that bowl is a 2D flame field: four rising
 * plumes with sinusoidal horizontal sway and a vertical alpha gradient,
 * plus a scattering of amber embers drifting up from the coals.
 *
 * The flame is parameterised by `intensity` in [0, 1]:
 *   - 0  = barely a wisp; the hearth "smoulders"
 *   - 1  = tall vigorous flames reaching the top of the scene
 *
 * Page code sets `intensity` based on what the firm is actually doing:
 * how many uploads are still processing, whether there are unresolved
 * reviews, how recent the last activity was. The dashboard renders a
 * quiet cauldron when nothing is happening and a roaring forge when
 * it's working — the UI itself pulses with the system's intellectual
 * metabolism.
 */

export type DashboardHearthProps = {
  /** Fire intensity 0..1. Page code derives this from live activity. */
  intensity?: number;
  /** Grid dimensions in character cells. 80×22 is the sweet spot for a banner strip. */
  cols?: number;
  rows?: number;
  /** Accessible label. */
  ariaLabel?: string;
};

type Vec3 = [number, number, number];

/** Rotate vec about Y then project to image-plane coords (px relative to centre). */
function project(
  [x, y, z]: Vec3,
  yaw: number,
  pitch: number,
  cx: number,
  cy: number,
  scale: number,
): { x: number; y: number; depth: number } {
  // Yaw (around Y)
  const cy_ = Math.cos(yaw),
    sy_ = Math.sin(yaw);
  const x1 = x * cy_ + z * sy_;
  const z1 = -x * sy_ + z * cy_;
  const y1 = y;

  // Pitch (around X)
  const cp = Math.cos(pitch),
    sp = Math.sin(pitch);
  const y2 = y1 * cp - z1 * sp;
  const z2 = y1 * sp + z1 * cp;
  const x2 = x1;

  // Simple orthographic projection; scene is small enough that perspective
  // doesn't add much and actively fights the ASCII renderer's flat-ish
  // contrast.
  return {
    x: cx + x2 * scale,
    y: cy - y2 * scale,
    depth: z2,
  };
}

/** Build a ring of points at height `y` with `segs` steps, radius `r`. */
function ring(y: number, r: number, segs: number): Vec3[] {
  const out: Vec3[] = [];
  for (let i = 0; i < segs; i++) {
    const t = (i / segs) * Math.PI * 2;
    out.push([Math.cos(t) * r, y, Math.sin(t) * r]);
  }
  return out;
}

export default function DashboardHearth({
  intensity = 0.35,
  cols = 80,
  rows = 22,
  ariaLabel = "The Oracle's Hearth — live indicator of firm activity",
}: DashboardHearthProps) {
  // Clamp so callers can't accidentally push the flame out of the grid.
  const I = Math.max(0, Math.min(1, intensity));

  // Pre-compute the bowl ring geometry once. It's not cheap to rebuild
  // three dozen rings every frame and it never changes.
  const bowlRings = useMemo(() => {
    // Eight stacked rings from the rim down to the base. Radius follows
    // half of an ellipse for a hemispherical-ish bowl shape.
    const R = 0.95; // rim radius (world-space units)
    const depth = 0.55; // vertical depth of the bowl
    const segs = 48;
    const rings: Vec3[][] = [];
    const N = 8;
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1); // 0 at rim, 1 at base
      const y = -t * depth;
      // Ellipse profile so the bowl rounds at the bottom instead of coning.
      const r = R * Math.sqrt(Math.max(0, 1 - t * t));
      rings.push(ring(y, r, segs));
    }
    return rings;
  }, []);

  // Legs: three cylinders descending from the underside of the bowl at
  // equally-spaced yaw angles. Each cylinder is a top + bottom ring.
  const legRings = useMemo(() => {
    const legs: Vec3[][] = [];
    const legR = 0.11;
    const topY = -0.52;
    const botY = -1.1;
    const segs = 10;
    for (let i = 0; i < 3; i++) {
      const ang = (i / 3) * Math.PI * 2;
      const ox = Math.cos(ang) * 0.55;
      const oz = Math.sin(ang) * 0.55;
      const top: Vec3[] = [];
      const bot: Vec3[] = [];
      for (let k = 0; k < segs; k++) {
        const t = (k / segs) * Math.PI * 2;
        top.push([ox + Math.cos(t) * legR, topY, oz + Math.sin(t) * legR]);
        bot.push([ox + Math.cos(t) * legR, botY, oz + Math.sin(t) * legR]);
      }
      legs.push(top, bot);
    }
    return legs;
  }, []);

  const width = cols * CELL_W;
  const height = rows * CELL_H;

  // Pre-seed ember particles once. We update positions every frame based on
  // elapsed time, but a stable particle pool avoids garbage-collection
  // thrash at 60fps.
  type Ember = {
    x: number;
    y: number;
    vx: number;
    vy: number;
    life: number;
    age: number;
  };
  const embersRef = useRef<Ember[] | null>(null);
  if (embersRef.current === null) {
    const embers: Ember[] = [];
    for (let i = 0; i < 42; i++) {
      embers.push({
        x: (Math.random() - 0.5) * 0.6,
        y: -0.5 + Math.random() * 0.3,
        vx: (Math.random() - 0.5) * 0.02,
        vy: 0.08 + Math.random() * 0.12,
        life: 1.2 + Math.random() * 1.4,
        age: Math.random() * 2,
      });
    }
    embersRef.current = embers;
  }

  const lastTRef = useRef<number>(0);

  const render = useCallback(
    (ctx: CanvasRenderingContext2D, timeMs: number) => {
      const t = timeMs / 1000;
      const dt = Math.max(0, Math.min(0.1, t - lastTRef.current));
      lastTRef.current = t;

      // Very slow yaw so the brazier looks solid and present rather than
      // performing. Just enough rotation to break up the silhouette.
      const yaw = t * 0.12;
      const pitch = -0.28; // looking slightly down into the bowl

      const cx = width / 2;
      const cy = height * 0.6; // scene tilts toward the lower half; flame breathes upward
      const scale = Math.min(width, height) * 0.38;

      ctx.clearRect(0, 0, width, height);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      // ── Bowl: draw each horizontal ring, then a handful of vertical
      //    meridians, wireframe style. Back-facing segments are dimmer.
      ctx.lineWidth = 1.6;
      const drawRing = (ring: Vec3[]) => {
        let prev: ReturnType<typeof project> | null = null;
        for (let i = 0; i <= ring.length; i++) {
          const p = project(ring[i % ring.length]!, yaw, pitch, cx, cy, scale);
          if (prev) {
            // Darken segments whose midpoint is behind (positive z post-rotation).
            const midDepth = (prev.depth + p.depth) * 0.5;
            const alpha = midDepth > 0 ? 0.45 : 1.0;
            ctx.strokeStyle = `rgba(255, 210, 140, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(prev.x, prev.y);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
          }
          prev = p;
        }
      };
      for (const r of bowlRings) drawRing(r);

      // Vertical meridians — one every 8 segments — to give the bowl
      // volume. Without these, rings alone read as a stack of hoops.
      const meridians = 8;
      const topRing = bowlRings[0]!;
      const botRing = bowlRings[bowlRings.length - 1]!;
      for (let m = 0; m < meridians; m++) {
        const idx = Math.floor((m / meridians) * topRing.length);
        const top = project(topRing[idx]!, yaw, pitch, cx, cy, scale);
        const bot = project(botRing[idx]!, yaw, pitch, cx, cy, scale);
        ctx.strokeStyle = `rgba(255, 210, 140, ${top.depth > 0 ? 0.35 : 0.75})`;
        ctx.beginPath();
        ctx.moveTo(top.x, top.y);
        ctx.lineTo(bot.x, bot.y);
        ctx.stroke();
      }

      // Rim highlight — redraw the rim ring over everything, brighter, so
      // the lip of the bowl reads as the strongest horizontal line.
      ctx.lineWidth = 2.1;
      ctx.strokeStyle = "rgba(255, 230, 180, 1)";
      ctx.beginPath();
      for (let i = 0; i <= topRing.length; i++) {
        const p = project(topRing[i % topRing.length]!, yaw, pitch, cx, cy, scale);
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();

      // ── Legs: three triangular prisms projected as ring-pairs.
      ctx.lineWidth = 1.4;
      for (let k = 0; k < legRings.length; k += 2) {
        const top = legRings[k]!;
        const bot = legRings[k + 1]!;
        for (let i = 0; i < top.length; i++) {
          const tp = project(top[i]!, yaw, pitch, cx, cy, scale);
          const bp = project(bot[i]!, yaw, pitch, cx, cy, scale);
          ctx.strokeStyle = `rgba(220, 170, 90, ${tp.depth > 0 ? 0.3 : 0.7})`;
          ctx.beginPath();
          ctx.moveTo(tp.x, tp.y);
          ctx.lineTo(bp.x, bp.y);
          ctx.stroke();
        }
      }

      // ── Flames: four sinusoidal plumes rising from inside the bowl. Each
      //    plume is a vertical ribbon whose x-offset varies with sin(t).
      //    Alpha fades to zero at the top, sharply near the tip so the
      //    ASCII picker produces lighter glyphs at the fringe.
      const flameBaseY = cy - scale * 0.05; // just above the rim visually
      const maxFlameH = scale * (0.5 + I * 1.1); // taller with intensity
      const plumeCount = Math.round(3 + I * 3);
      for (let p = 0; p < plumeCount; p++) {
        const spread = ((p / (plumeCount - 1 || 1)) - 0.5) * scale * 0.9;
        const plumeH = maxFlameH * (0.5 + 0.5 * Math.sin(t * 1.8 + p * 1.3));
        const sway = Math.sin(t * 2.3 + p * 0.9) * scale * 0.07;

        // Draw ribbon as a filled path from bottom-left to top to bottom-right.
        const steps = 18;
        ctx.beginPath();
        for (let s = 0; s <= steps; s++) {
          const ty = s / steps; // 0 at base, 1 at tip
          const y = flameBaseY - plumeH * ty;
          const w = scale * 0.12 * (1 - ty * ty) * (0.6 + I * 0.6); // narrows upward
          const x = cx + spread + sway * ty * ty;
          ctx.lineTo(x - w, y);
        }
        for (let s = steps; s >= 0; s--) {
          const ty = s / steps;
          const y = flameBaseY - plumeH * ty;
          const w = scale * 0.12 * (1 - ty * ty) * (0.6 + I * 0.6);
          const x = cx + spread + sway * ty * ty;
          ctx.lineTo(x + w, y);
        }
        ctx.closePath();

        // Gradient: bright at the base, fading at the tip. We map amber
        // brightness to the R channel; the ASCII picker only samples R.
        const grad = ctx.createLinearGradient(0, flameBaseY, 0, flameBaseY - plumeH);
        grad.addColorStop(0, `rgba(255, 210, 120, ${0.9})`);
        grad.addColorStop(0.55, `rgba(255, 160, 60, ${0.55})`);
        grad.addColorStop(1, "rgba(120, 40, 0, 0)");
        ctx.fillStyle = grad;
        ctx.fill();
      }

      // ── Ember particles — float up and fade. Pool re-used each frame.
      const embers = embersRef.current!;
      for (const e of embers) {
        e.x += e.vx * dt * 60;
        e.y += e.vy * dt * 60 * (0.6 + I * 0.8);
        e.age += dt;
        if (e.age > e.life) {
          e.age = 0;
          e.x = (Math.random() - 0.5) * 0.6;
          e.y = -0.5 + Math.random() * 0.2;
          e.vx = (Math.random() - 0.5) * 0.02;
          e.vy = 0.06 + Math.random() * 0.14;
        }
        const projPt = project([e.x, e.y, 0], yaw, pitch, cx, cy, scale);
        const lifeT = e.age / e.life;
        const size = 1.4 + (1 - lifeT) * 2.2 * (0.5 + I * 0.6);
        const alpha = (1 - lifeT) * (0.5 + I * 0.5);
        ctx.fillStyle = `rgba(255, 200, 100, ${alpha})`;
        ctx.fillRect(projPt.x - size / 2, projPt.y - size / 2, size, size);
      }
    },
    [bowlRings, legRings, height, width, I],
  );

  return (
    <AsciiCanvas
      cols={cols}
      rows={rows}
      render={render}
      contrast={1.8}
      ariaLabel={ariaLabel}
      style={{ display: "flex", justifyContent: "center" }}
    />
  );
}
