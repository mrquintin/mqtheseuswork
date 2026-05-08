import fs from "node:fs";
import path from "node:path";

import yaml from "js-yaml";

export type FailureSeverity = "low" | "medium" | "high";

export interface FailureModeCitation {
  title: string;
  url?: string;
  note?: string;
}

export interface FailureMode {
  name: string;
  description: string;
  worked_example: string;
  trigger_conditions: string;
  mitigation: string;
  severity: FailureSeverity;
  citations: FailureModeCitation[];
  public: boolean;
}

export interface FailureCatalog {
  method: string;
  failures?: "deliberately-empty";
  justification?: string;
  modes: FailureMode[];
}

export interface MatchedFailureMode extends FailureMode {
  matchScore: number;
  method: string;
}

const CATALOG_SUFFIX = ".FAILURES.yaml";

/**
 * Catalogs live alongside the Python method modules. Resolution walks
 * upward from the Next.js app root until a `noosphere/noosphere/methods`
 * directory is found. Production deployments pin the location via
 * `NOOSPHERE_METHODS_DIR`.
 */
function resolveMethodsDir(): string | null {
  const env = process.env.NOOSPHERE_METHODS_DIR;
  if (env && fs.existsSync(env)) return env;

  let cur = process.cwd();
  for (let i = 0; i < 6; i += 1) {
    const candidate = path.join(cur, "noosphere", "noosphere", "methods");
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  return null;
}

let _cache: Map<string, FailureCatalog> | null = null;

function loadCatalogs(): Map<string, FailureCatalog> {
  if (_cache) return _cache;
  const dir = resolveMethodsDir();
  const out = new Map<string, FailureCatalog>();
  if (!dir) {
    _cache = out;
    return out;
  }
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(CATALOG_SUFFIX));
  for (const file of files) {
    const method = file.slice(0, -CATALOG_SUFFIX.length);
    try {
      const raw = fs.readFileSync(path.join(dir, file), "utf-8");
      const parsed = yaml.load(raw) as Partial<FailureCatalog> | undefined;
      if (!parsed || typeof parsed !== "object") continue;
      const catalog: FailureCatalog = {
        method: parsed.method ?? method,
        failures: parsed.failures,
        justification: parsed.justification,
        modes: Array.isArray(parsed.modes)
          ? parsed.modes.map((m) => ({
              name: String(m.name ?? ""),
              description: String(m.description ?? ""),
              worked_example: String(m.worked_example ?? ""),
              trigger_conditions: String(m.trigger_conditions ?? ""),
              mitigation: String(m.mitigation ?? ""),
              severity: (m.severity ?? "medium") as FailureSeverity,
              citations: Array.isArray(m.citations) ? m.citations : [],
              public: Boolean(m.public),
            }))
          : [],
      };
      out.set(catalog.method, catalog);
    } catch {
      // Skip catalogs that fail to parse on the TS side; the Python
      // CI gate is the source of truth for catalog validity.
    }
  }
  _cache = out;
  return out;
}

export function getCatalog(method: string): FailureCatalog | null {
  return loadCatalogs().get(method) ?? null;
}

export function listCatalogs(): FailureCatalog[] {
  return Array.from(loadCatalogs().values()).sort((a, b) =>
    a.method.localeCompare(b.method),
  );
}

/**
 * Mirror of the Python `_lexical_match_score`. Used here for filtering
 * the on-screen list to "matched" modes when the persisted Python
 * cache isn't available; the frontend match score is advisory only —
 * the audited match decision lives in the Python cache.
 */
function lexicalScore(trigger: string, conclusionText: string): number {
  const tokens = (s: string): Set<string> =>
    new Set(
      s
        .split(/\s+/)
        .map((t) => t.toLowerCase().replace(/[.,;:!?]+$/g, "").replace(/^[.,;:!?]+/g, ""))
        .filter((t) => t.length > 3),
    );
  const a = tokens(trigger);
  const b = tokens(conclusionText);
  if (a.size === 0) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter += 1;
  return inter / Math.max(1, a.size);
}

export function matchModesForConclusion(
  methodNames: string[],
  conclusionText: string,
  threshold = 0.15,
): MatchedFailureMode[] {
  const out: MatchedFailureMode[] = [];
  const seen = new Set<string>();
  for (const method of methodNames) {
    if (seen.has(method)) continue;
    seen.add(method);
    const catalog = getCatalog(method);
    if (!catalog || catalog.failures === "deliberately-empty") continue;
    for (const mode of catalog.modes) {
      const score = lexicalScore(mode.trigger_conditions, conclusionText);
      if (score >= threshold) {
        out.push({ ...mode, matchScore: score, method });
      }
    }
  }
  // Surface high-severity matches first; helps the founder see what
  // has to be acknowledged before everything else.
  const order: Record<FailureSeverity, number> = { high: 0, medium: 1, low: 2 };
  return out.sort((a, b) => {
    const sev = order[a.severity] - order[b.severity];
    if (sev !== 0) return sev;
    return b.matchScore - a.matchScore;
  });
}

export function publicModesForMethod(method: string): FailureMode[] {
  const catalog = getCatalog(method);
  if (!catalog || catalog.failures === "deliberately-empty") return [];
  return catalog.modes.filter((m) => m.public);
}
