export type FounderDisplayFields = {
  displayName?: string | null;
  name?: string | null;
  username?: string | null;
};

const SEEDED_PLACEHOLDER_NAME = /^Founder\s+(Alpha|Beta|Gamma|Delta|Epsilon|Zeta|Eta|Theta|Iota|Kappa)$/i;

export function isSeededFounderPlaceholder(value: string | null | undefined): boolean {
  return SEEDED_PLACEHOLDER_NAME.test((value ?? "").trim());
}

export function founderDisplayName(founder: FounderDisplayFields): string {
  const displayName = founder.displayName?.trim();
  if (displayName) return displayName;

  const name = founder.name?.trim();
  if (name && !isSeededFounderPlaceholder(name)) return name;

  const username = founder.username?.trim();
  if (username) return username;

  return "Founder";
}

export function validateDisplayNameInput(value: unknown):
  | { ok: true; value: string }
  | { ok: false; error: string } {
  if (typeof value !== "string") {
    return { ok: false, error: "Display name is required." };
  }
  if (value !== value.trim()) {
    return {
      ok: false,
      error: "Display name must not have leading or trailing whitespace.",
    };
  }
  if (value.length < 2) {
    return {
      ok: false,
      error: "Display name must be at least 2 characters.",
    };
  }
  if (value.length > 60) {
    return {
      ok: false,
      error: "Display name must be 60 characters or fewer.",
    };
  }
  return { ok: true, value };
}
