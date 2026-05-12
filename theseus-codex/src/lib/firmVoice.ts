/**
 * Light-touch rewrites that nudge model output toward firm voice on public
 * surfaces. Operates on already-rendered prose; preserves casing, citation
 * markers, code, and links untouched.
 *
 * The contract here is conservative: only well-defined phrasings shift, so we
 * never reword a substantive claim — only the framing verbs the model reaches
 * for when it is reciting evidence ("the sources say…") rather than asserting
 * an opinion in the firm's name.
 */

interface VoiceReplacement {
  pattern: RegExp;
  to: string;
}

const REPLACEMENTS: VoiceReplacement[] = [
  { pattern: /\bthe sources say\b/gi, to: "the firm holds" },
  { pattern: /\bthe sources suggest\b/gi, to: "the firm reads this as" },
  { pattern: /\bthe sources indicate\b/gi, to: "the firm reads this as" },
  { pattern: /\bthe sources show\b/gi, to: "the firm holds" },
  { pattern: /\baccording to the sources\b/gi, to: "in the firm's view" },
  { pattern: /\baccording to our sources\b/gi, to: "in the firm's view" },
  { pattern: /\bour sources\b/gi, to: "the firm" },
  { pattern: /\bthe source material\b/gi, to: "the firm's corpus" },
  { pattern: /\bthe sources we have\b/gi, to: "the firm's corpus" },
  { pattern: /\bbased on the sources\b/gi, to: "in the firm's view" },
];

function preserveCase(original: string, replacement: string): string {
  if (!original) return replacement;
  const first = original[0];
  if (first === first.toUpperCase() && first !== first.toLowerCase()) {
    return replacement[0].toUpperCase() + replacement.slice(1);
  }
  return replacement;
}

export function firmVoice(text: string): string {
  if (!text) return text;
  let result = text;
  for (const { pattern, to } of REPLACEMENTS) {
    result = result.replace(pattern, (match) => preserveCase(match, to));
  }
  return result;
}
