/**
 * Permanent 308 aliases for renamed public routes.
 *
 * When a public URL is renamed during a naming-convention pass (see
 * `docs/architecture/Naming_Conventions.md`), the old path is kept
 * alive as a 308 redirect so that external links, bookmarks, and
 * crawler indices keep working. 308 (Permanent Redirect) — not 301 —
 * because we want the redirect to preserve the request method, and
 * we want browsers and intermediaries to remember it.
 *
 * The middleware (`src/middleware.ts`) consults this table on every
 * request *before* running auth, so aliased paths resolve cleanly
 * even for unauthenticated visitors landing from an external link.
 *
 * Keep this table append-only. Removing an entry breaks a URL that
 * the firm has implicitly promised to keep redirecting forever.
 */

export type UrlAlias = {
  /**
   * Source path or path pattern. Two forms are supported:
   *
   *   - Literal: `"/old/path"` — matches only this exact pathname.
   *   - Single-param: `"/old/:slug"` — matches one path segment after
   *     the prefix; the captured segment is substituted into
   *     `destination` wherever the same `:name` appears.
   *
   * Wildcards beyond one segment are intentionally not supported —
   * if you need them, prefer Next.js's `redirects()` table in
   * `next.config.ts`. This table is for the narrow case of public
   * routes renamed by a convention pass.
   */
  source: string;
  /** Destination path; may reference any `:name` from `source`. */
  destination: string;
  /** Free-form reason (renamed in convention pass, retired, etc.). */
  reason: string;
};

export const URL_ALIASES: readonly UrlAlias[] = [
  // Round 17 drift: some links and one earlier doc revision referred
  // to the methodology detail page as `/methodology/[name]`. The
  // canonical route is `/methodology/[method]` (the conceptual noun
  // — see Naming_Conventions.md, "URLs"). Keep the old path alive
  // for any external references that still point at it.
  //
  // Note: Next.js's filesystem router never actually served
  // `/methodology/[name]` from `src/app`; the alias exists because
  // earlier prompt material and one round of generated docs leaked
  // the wrong slug into the firm's public surfaces. Removing the
  // alias is safe only after we've audited every outbound link
  // (RSS, email digests, the academic citation set) for it.
  // No-op until / unless `[name]` actually appears in the wild —
  // recorded here as the alias contract for the methodology page.
  // (Intentionally empty entry list: nothing was actively renamed in
  // this pass. Append entries here in the form below as future
  // renames land.)
] as const;

/**
 * Resolve a request pathname against the alias table.
 *
 * Returns the new path if `pathname` matches an alias, or `null` if
 * no alias applies. The match is exact for literal sources, and
 * segment-bounded for single-param sources (so `/old/foo` matches
 * `"/old/:slug"` but `/old/foo/bar` does not).
 */
export function resolveUrlAlias(
  pathname: string,
  aliases: readonly UrlAlias[] = URL_ALIASES,
): string | null {
  for (const alias of aliases) {
    const resolved = matchAlias(pathname, alias);
    if (resolved !== null) return resolved;
  }
  return null;
}

function matchAlias(pathname: string, alias: UrlAlias): string | null {
  const { source, destination } = alias;

  // Literal: no `:` in the source — must be an exact match.
  if (!source.includes("/:")) {
    return pathname === source ? destination : null;
  }

  // Single-param. Split into segments and require equal segment counts.
  const sourceSegments = source.split("/");
  const pathSegments = pathname.split("/");
  if (sourceSegments.length !== pathSegments.length) return null;

  const captures: Record<string, string> = {};
  for (let i = 0; i < sourceSegments.length; i++) {
    const s = sourceSegments[i];
    const p = pathSegments[i];
    if (s.startsWith(":")) {
      // Empty path segment (e.g. trailing slash) does not match a param.
      if (!p) return null;
      captures[s.slice(1)] = p;
      continue;
    }
    if (s !== p) return null;
  }

  // Substitute captures into destination.
  return destination.replace(/:([A-Za-z_][A-Za-z0-9_]*)/g, (_, name: string) => {
    const value = captures[name];
    if (value === undefined) {
      throw new Error(
        `urlAliases: destination references :${name} that is not captured by source "${source}"`,
      );
    }
    return value;
  });
}

/**
 * For tests: assert the alias table is well-formed. Surfaces config
 * bugs (a `:slug` in `destination` that isn't in `source`) at test
 * time rather than at request time.
 */
export function validateAliasTable(
  aliases: readonly UrlAlias[] = URL_ALIASES,
): void {
  for (const alias of aliases) {
    const sourceParams = new Set(
      Array.from(alias.source.matchAll(/:([A-Za-z_][A-Za-z0-9_]*)/g)).map((m) => m[1]),
    );
    for (const match of alias.destination.matchAll(/:([A-Za-z_][A-Za-z0-9_]*)/g)) {
      const name = match[1];
      if (!sourceParams.has(name)) {
        throw new Error(
          `urlAliases: alias "${alias.source}" → "${alias.destination}" references :${name} which is not captured`,
        );
      }
    }
  }
}
