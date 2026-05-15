import {
  URL_ALIASES,
  resolveUrlAlias,
  validateAliasTable,
  type UrlAlias,
} from "@/lib/urlAliases";

describe("urlAliases module", () => {
  it("ships a well-formed alias table (every destination capture is bound)", () => {
    expect(() => validateAliasTable()).not.toThrow();
  });

  it("returns null for paths that have no alias", () => {
    expect(resolveUrlAlias("/")).toBeNull();
    expect(resolveUrlAlias("/dashboard")).toBeNull();
    expect(resolveUrlAlias("/methodology")).toBeNull();
    expect(resolveUrlAlias("/methodology/falsification")).toBeNull();
  });
});

describe("resolveUrlAlias — literal and single-param matching", () => {
  // A self-contained fixture table so the unit test exercises the
  // matcher independently of whatever URL_ALIASES happens to hold at
  // the moment.
  const fixtures: readonly UrlAlias[] = [
    {
      source: "/methodology/[name]",
      destination: "/methodology/[method]",
      reason: "historical Round 17 drift — kept for inbound link safety",
    },
    {
      source: "/old/literal",
      destination: "/new/literal",
      reason: "literal-only rename",
    },
    {
      source: "/old/:slug",
      destination: "/new/:slug",
      reason: "param rename",
    },
    {
      source: "/swapped/:left/:right",
      destination: "/swapped/:right/:left",
      reason: "param reorder",
    },
  ];

  it("rewrites literal aliases exactly", () => {
    expect(resolveUrlAlias("/old/literal", fixtures)).toBe("/new/literal");
  });

  it("does not match a literal when the path has trailing segments", () => {
    expect(resolveUrlAlias("/old/literal/extra", fixtures)).toBeNull();
  });

  it("substitutes a single captured param", () => {
    expect(resolveUrlAlias("/old/falsification", fixtures)).toBe(
      "/new/falsification",
    );
  });

  it("does not match if segment counts differ", () => {
    expect(resolveUrlAlias("/old", fixtures)).toBeNull();
    expect(resolveUrlAlias("/old/a/b", fixtures)).toBeNull();
  });

  it("rejects empty path segments for params", () => {
    expect(resolveUrlAlias("/old/", fixtures)).toBeNull();
  });

  it("supports multi-param substitution and reordering", () => {
    expect(resolveUrlAlias("/swapped/alpha/beta", fixtures)).toBe(
      "/swapped/beta/alpha",
    );
  });

  it("treats the [name] → [method] case as a faithful rewrite", () => {
    // The bracketed form is treated as a literal segment, not a
    // capture — `[name]` is the literal Next.js dynamic-segment
    // directory name as it appeared on disk historically. Matching is
    // exact-segment.
    expect(resolveUrlAlias("/methodology/[name]", fixtures)).toBe(
      "/methodology/[method]",
    );
  });
});

describe("validateAliasTable — config errors surface at test time", () => {
  it("throws when destination references a param that source does not capture", () => {
    const bad: UrlAlias[] = [
      {
        source: "/a/literal",
        destination: "/b/:missing",
        reason: "intentionally broken for the test",
      },
    ];
    expect(() => validateAliasTable(bad)).toThrow(/missing/);
  });

  it("accepts a destination that omits a captured param (dropping a segment is allowed)", () => {
    const ok: UrlAlias[] = [
      {
        source: "/a/:slug",
        destination: "/b",
        reason: "drop the slug intentionally",
      },
    ];
    expect(() => validateAliasTable(ok)).not.toThrow();
  });
});

describe("URL_ALIASES contract", () => {
  it("every entry uses absolute paths (starts with /)", () => {
    for (const alias of URL_ALIASES) {
      expect(alias.source.startsWith("/")).toBe(true);
      expect(alias.destination.startsWith("/")).toBe(true);
    }
  });

  it("no alias is a no-op (source !== destination)", () => {
    for (const alias of URL_ALIASES) {
      expect(alias.source).not.toBe(alias.destination);
    }
  });

  it("every alias carries a non-empty reason for the rename", () => {
    for (const alias of URL_ALIASES) {
      expect(alias.reason.trim().length).toBeGreaterThan(0);
    }
  });
});
