"use client";

/**
 * ProvenanceFilter — the four-checkbox / four-slider control that
 * sits at the top of the Oracle page (prompt 09).
 *
 * The checkboxes are the founder-visible interface to which provenance
 * buckets the synthesizer pulls from. The sliders sit under an
 * "Advanced" disclosure (collapsed by default) so the founder doesn't
 * have to think about weights to use the Oracle — the defaults ship a
 * sane mix (proprietary 2×, endorsed 1×, studied 0.5×, opposing 0.1×).
 *
 * Each checkbox label shows a count of available sources of that
 * provenance so the founder sees exactly what they're querying. The
 * counts are passed in from the parent because they come from the
 * Oracle API (`GET /v1/oracle/provenance-counts`).
 */
import { useState } from "react";

export type ProvenanceKindStr =
  | "PROPRIETARY"
  | "ENDORSED_EXTERNAL"
  | "STUDIED_EXTERNAL"
  | "OPPOSING_EXTERNAL";

export interface ProvenanceFilterValue {
  include_proprietary: boolean;
  include_endorsed_external: boolean;
  include_studied_external: boolean;
  include_opposing_external: boolean;
  proprietary_weight: number;
  endorsed_external_weight: number;
  studied_external_weight: number;
  opposing_external_weight: number;
}

export const DEFAULT_PROVENANCE_FILTER: ProvenanceFilterValue = {
  include_proprietary: true,
  include_endorsed_external: true,
  include_studied_external: false,
  include_opposing_external: false,
  proprietary_weight: 2.0,
  endorsed_external_weight: 1.0,
  studied_external_weight: 0.5,
  opposing_external_weight: 0.1,
};

interface KindMeta {
  kind: ProvenanceKindStr;
  label: string;
  includeKey: keyof ProvenanceFilterValue;
  weightKey: keyof ProvenanceFilterValue;
  blurb: string;
}

const KINDS: KindMeta[] = [
  {
    kind: "PROPRIETARY",
    label: "Proprietary",
    includeKey: "include_proprietary",
    weightKey: "proprietary_weight",
    blurb: "Material the firm authored.",
  },
  {
    kind: "ENDORSED_EXTERNAL",
    label: "Endorsed external",
    includeKey: "include_endorsed_external",
    weightKey: "endorsed_external_weight",
    blurb: "Outside writing the firm stands behind.",
  },
  {
    kind: "STUDIED_EXTERNAL",
    label: "Studied external",
    includeKey: "include_studied_external",
    weightKey: "studied_external_weight",
    blurb: "Reference / test-case material — not endorsed.",
  },
  {
    kind: "OPPOSING_EXTERNAL",
    label: "Opposing external",
    includeKey: "include_opposing_external",
    weightKey: "opposing_external_weight",
    blurb: "Material we disagree with, kept for argument value.",
  },
];

interface Props {
  value: ProvenanceFilterValue;
  onChange: (next: ProvenanceFilterValue) => void;
  counts: Partial<Record<ProvenanceKindStr, number>>;
}

export default function ProvenanceFilter({ value, onChange, counts }: Props) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const set = <K extends keyof ProvenanceFilterValue>(
    key: K,
    next: ProvenanceFilterValue[K],
  ) => onChange({ ...value, [key]: next });

  return (
    <fieldset
      style={{
        border: "1px solid var(--stroke)",
        borderRadius: "4px",
        padding: "1rem 1.1rem",
        background: "rgba(212, 160, 23, 0.035)",
      }}
    >
      <legend
        className="mono"
        style={{
          fontSize: "0.65rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--amber)",
          padding: "0 0.4rem",
        }}
      >
        Sources
      </legend>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {KINDS.map((meta) => {
          const checked = Boolean(value[meta.includeKey]);
          const count = counts[meta.kind] ?? 0;
          return (
            <label
              key={meta.kind}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.6rem",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => set(meta.includeKey, e.target.checked)}
                style={{ marginTop: "0.3rem" }}
              />
              <span style={{ flex: 1 }}>
                <strong style={{ color: "var(--parchment)" }}>
                  {meta.label}
                </strong>{" "}
                <span
                  className="mono"
                  style={{
                    color: "var(--parchment-dim)",
                    fontSize: "0.75rem",
                  }}
                >
                  · {count} {count === 1 ? "source" : "sources"}
                </span>
                <div
                  style={{
                    color: "var(--parchment-dim)",
                    fontSize: "0.85rem",
                  }}
                >
                  {meta.blurb}
                </div>
              </span>
            </label>
          );
        })}
      </div>

      <button
        type="button"
        onClick={() => setAdvancedOpen((v) => !v)}
        className="mono"
        style={{
          marginTop: "1rem",
          fontSize: "0.6rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "pointer",
        }}
      >
        {advancedOpen ? "− Hide weights" : "+ Show weights"}
      </button>

      {advancedOpen && (
        <div
          style={{
            marginTop: "0.8rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.45rem",
          }}
        >
          {KINDS.map((meta) => {
            const weight = Number(value[meta.weightKey]);
            return (
              <label
                key={meta.kind}
                style={{
                  display: "grid",
                  gridTemplateColumns: "11rem 1fr 3rem",
                  gap: "0.6rem",
                  alignItems: "center",
                  fontSize: "0.85rem",
                  color: "var(--parchment)",
                }}
              >
                <span>{meta.label} weight</span>
                <input
                  type="range"
                  min={0}
                  max={5}
                  step={0.1}
                  value={weight}
                  onChange={(e) =>
                    set(meta.weightKey, Number(e.target.value))
                  }
                />
                <span
                  className="mono"
                  style={{ color: "var(--parchment-dim)" }}
                >
                  {weight.toFixed(1)}×
                </span>
              </label>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}
