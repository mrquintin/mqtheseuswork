"use client";

import AsciiSigil from "@/components/AsciiSigil";

/**
 * Thin client-component shim so the server-rendered conclusion detail page
 * can pass an `<AsciiSigil />` to its `<PageHelp />` banner. `AsciiSigil`
 * itself is a client component (uses rAF + canvas), and `PageHelp`'s
 * `sigil` prop accepts a plain ReactNode. This file just bridges the two.
 */
export default function ConclusionSigil() {
  return <AsciiSigil shape="dodec" cols={24} rows={10} size={128} speed={0.8} />;
}
