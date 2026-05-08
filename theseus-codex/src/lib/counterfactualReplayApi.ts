/**
 * Founder-only counterfactual replay manifest loader.
 *
 * The "would-have-been-better" matrix is private. Numbers are too easy
 * to misread (small n, mismatched domain bounds) and we never publish
 * them on the calibration page. This loader reads a manifest written
 * by the Python engine to disk; if no manifest exists yet, the page
 * renders an empty state rather than a fabricated grid.
 *
 * Manifest contract — written by `noosphere replay export-manifest`:
 *
 *   {
 *     "generated_at": "...iso...",
 *     "alternative_methods": ["six_layer_coherence", ...],
 *     "actual_methods": ["synthesize_conclusion", ...],
 *     "cells": [
 *       {
 *         "actual_method": "synthesize_conclusion",
 *         "alternative_method": "six_layer_coherence",
 *         "n": 12,
 *         "mean_brier_actual": 0.21,
 *         "mean_brier_alternative": 0.17,
 *         "mean_brier_delta": -0.04,
 *         "mean_abs_brier_delta": 0.08,
 *         "alt_better_count": 8,
 *         "examples": [
 *           {"conclusion_id": "...", "headline": "...",
 *            "actual_confidence": 0.7, "alt_confidence": 0.55,
 *            "outcome": true, "actual_brier": 0.09, "alt_brier": 0.20}
 *         ]
 *       }
 *     ]
 *   }
 */

import fs from "node:fs";
import path from "node:path";

export type CounterfactualExample = {
  conclusionId: string;
  headline: string;
  actualConfidence: number;
  altConfidence: number;
  outcome: boolean;
  actualBrier: number;
  altBrier: number;
};

export type CounterfactualCell = {
  actualMethod: string;
  alternativeMethod: string;
  n: number;
  meanBrierActual: number;
  meanBrierAlternative: number;
  meanBrierDelta: number;
  meanAbsBrierDelta: number;
  altBetterCount: number;
  examples: CounterfactualExample[];
};

export type CounterfactualManifest = {
  generatedAt: string;
  actualMethods: string[];
  alternativeMethods: string[];
  cells: CounterfactualCell[];
  source: "manifest" | "empty";
};

function manifestPath(): string {
  const explicit = process.env.THESEUS_COUNTERFACTUAL_PATH?.trim();
  if (explicit) return explicit;
  const dataDir = process.env.NOOSPHERE_DATA_DIR?.trim();
  const root = dataDir ? dataDir : "/var/lib/theseus";
  return path.join(root, "counterfactual_replay_manifest.json");
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function asString(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function normalizeExample(raw: Record<string, unknown>): CounterfactualExample {
  return {
    conclusionId: asString(raw.conclusion_id),
    headline: asString(raw.headline),
    actualConfidence: asNumber(raw.actual_confidence),
    altConfidence: asNumber(raw.alt_confidence),
    outcome: Boolean(raw.outcome),
    actualBrier: asNumber(raw.actual_brier),
    altBrier: asNumber(raw.alt_brier),
  };
}

function normalizeCell(raw: Record<string, unknown>): CounterfactualCell {
  const examples = Array.isArray(raw.examples)
    ? (raw.examples as Array<Record<string, unknown>>).map(normalizeExample)
    : [];
  return {
    actualMethod: asString(raw.actual_method),
    alternativeMethod: asString(raw.alternative_method),
    n: asNumber(raw.n, 0),
    meanBrierActual: asNumber(raw.mean_brier_actual),
    meanBrierAlternative: asNumber(raw.mean_brier_alternative),
    meanBrierDelta: asNumber(raw.mean_brier_delta),
    meanAbsBrierDelta: asNumber(raw.mean_abs_brier_delta),
    altBetterCount: asNumber(raw.alt_better_count, 0),
    examples,
  };
}

function emptyManifest(): CounterfactualManifest {
  return {
    generatedAt: new Date().toISOString(),
    actualMethods: [],
    alternativeMethods: [],
    cells: [],
    source: "empty",
  };
}

export function loadCounterfactualManifest(): CounterfactualManifest {
  let text: string;
  try {
    text = fs.readFileSync(manifestPath(), "utf8");
  } catch {
    return emptyManifest();
  }
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(text) as Record<string, unknown>;
  } catch (err) {
    console.warn("[counterfactual] manifest parse failed:", err);
    return emptyManifest();
  }
  const cells = Array.isArray(raw.cells)
    ? (raw.cells as Array<Record<string, unknown>>).map(normalizeCell)
    : [];
  const actualMethods = Array.isArray(raw.actual_methods)
    ? (raw.actual_methods as unknown[]).map((m) => String(m))
    : Array.from(new Set(cells.map((c) => c.actualMethod))).sort();
  const alternativeMethods = Array.isArray(raw.alternative_methods)
    ? (raw.alternative_methods as unknown[]).map((m) => String(m))
    : Array.from(new Set(cells.map((c) => c.alternativeMethod))).sort();
  return {
    generatedAt: asString(raw.generated_at, new Date().toISOString()),
    actualMethods,
    alternativeMethods,
    cells,
    source: "manifest",
  };
}

export function findCell(
  manifest: CounterfactualManifest,
  actualMethod: string,
  alternativeMethod: string,
): CounterfactualCell | null {
  return (
    manifest.cells.find(
      (c) =>
        c.actualMethod === actualMethod &&
        c.alternativeMethod === alternativeMethod,
    ) ?? null
  );
}
