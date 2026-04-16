/** URL-safe slug for public conclusion paths (stable across minor text edits). */
export function publicationSlugFromText(text: string, maxLen = 72): string {
  const base = text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, maxLen);
  return base || "conclusion";
}
