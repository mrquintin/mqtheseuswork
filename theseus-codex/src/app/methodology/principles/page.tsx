import { permanentRedirect } from "next/navigation";

/**
 * Retired URL — the firm's canonical principles index moved to
 * `/principles` in Round 21. This page survives only to send any
 * historical deep-link there with a 308 (permanent redirect), so
 * external linkers and search engines re-anchor cleanly. The 308 is
 * the App-Router equivalent of the constraint's "old path 301s to the
 * new": `permanentRedirect` emits 308 (permanent + method-preserving),
 * which is the modern replacement for 301 for HTML navigation.
 *
 * Do not put any rendering logic in this file. If a new public
 * methodology index is ever needed, choose a different route — this
 * URL is reserved for the redirect.
 */
export default function RetiredPublicPrinciplesIndex(): never {
  permanentRedirect("/principles");
}
