import Link from "next/link";

import type { PublicationSignatureStatus } from "@/lib/publicationService";

/**
 * Banner that surfaces a published conclusion's cryptographic signature
 * status. Three states:
 *
 *   - verified   → green: signed canonical hash matches the live row.
 *   - unsigned   → muted: no signature has been minted yet (CLI hasn't run).
 *   - mismatch   → RED: the live row no longer hashes to what was signed,
 *                  i.e. either the database has been mutated or the
 *                  signature is stale. Per spec we surface this loudly,
 *                  we do not silently hide.
 *
 * The web app cannot mint signatures (it has no private key); a fresh
 * signature is produced via the noosphere CLI:
 *
 *   noosphere ledger sign-publication <slug>
 *
 * The /proof page documents the scheme.
 */
export default function SignatureBanner({
  status,
  slug,
  version,
}: {
  status: PublicationSignatureStatus;
  slug: string;
  version: number;
}) {
  if (status.state === "verified") {
    const sig = status.signature;
    return (
      <div
        className="mt-4 rounded border border-emerald-700/60 bg-emerald-900/10 px-3 py-2 text-xs"
        role="status"
        aria-label="Cryptographic signature verified"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="font-medium text-emerald-700 dark:text-emerald-300">
            ✓ Cryptographically signed
          </span>
          <Link className="underline opacity-70 hover:opacity-100" href="/proof">
            How verification works
          </Link>
        </div>
        <dl className="mt-1 grid grid-cols-1 gap-x-4 gap-y-0.5 text-[11px] opacity-80 sm:grid-cols-3">
          <div>
            <dt className="inline opacity-60">Key </dt>
            <dd className="inline font-mono">{sig.keyFingerprint}</dd>
          </div>
          <div>
            <dt className="inline opacity-60">Hash </dt>
            <dd className="inline font-mono">{sig.canonicalHash.slice(0, 16)}…</dd>
          </div>
          <div>
            <dt className="inline opacity-60">Signed </dt>
            <dd className="inline">{sig.signedAt}</dd>
          </div>
        </dl>
        <div className="mt-1 text-[11px] opacity-70">
          Verify independently:{" "}
          <code className="font-mono">
            noosphere ledger verify-publication {slug}
            {version !== sig.version ? ` --version ${sig.version}` : ""}
          </code>
        </div>
      </div>
    );
  }

  if (status.state === "unsigned") {
    return (
      <div
        className="mt-4 rounded border border-stone-500/40 bg-stone-500/5 px-3 py-2 text-xs opacity-80"
        role="status"
        aria-label="Awaiting cryptographic signature"
      >
        <span className="font-medium">Signature pending.</span>{" "}
        This publication has not yet been signed by the firm's publication key. See{" "}
        <Link className="underline" href="/proof">
          /proof
        </Link>{" "}
        for the signing scheme.
      </div>
    );
  }

  return (
    <div
      className="mt-4 rounded border-2 border-red-600 bg-red-900/15 px-3 py-2 text-xs"
      role="alert"
      aria-label="Cryptographic signature mismatch"
    >
      <div className="font-semibold text-red-700 dark:text-red-300">
        ✗ Signature does not match the live record.
      </div>
      <p className="mt-1 opacity-90">
        Either this page was mutated after signing, or the signature is stale (canonical inputs
        changed). Both are bugs the firm wants to know about. See{" "}
        <Link className="underline" href="/proof">
          /proof
        </Link>{" "}
        for re-verification instructions.
      </p>
      <dl className="mt-1 grid grid-cols-1 gap-x-4 gap-y-0.5 text-[11px] font-mono opacity-80 sm:grid-cols-2">
        <div>
          <dt className="inline opacity-60">signed </dt>
          <dd className="inline">{status.signedHash.slice(0, 24)}…</dd>
        </div>
        <div>
          <dt className="inline opacity-60">live   </dt>
          <dd className="inline">{status.expectedHash.slice(0, 24)}…</dd>
        </div>
      </dl>
    </div>
  );
}
