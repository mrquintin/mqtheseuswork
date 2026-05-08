import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { activePublicationKeyFingerprint } from "@/lib/publicationService";

export const dynamic = "force-dynamic";
export const revalidate = 300;

export const metadata: Metadata = {
  title: "Proof — how Theseus signs its publications",
  description:
    "Every public Theseus publication carries an Ed25519 signature over a canonical hash of its inputs. This page describes the scheme and how anyone can re-verify a publication.",
};

export default async function ProofPage() {
  const [founder, activeFingerprint] = await Promise.all([
    getFounder(),
    activePublicationKeyFingerprint(),
  ]);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="mx-auto max-w-3xl px-4 py-10 leading-relaxed">
        <h1 className="text-2xl font-semibold">Proof</h1>
        <p className="mt-2 text-sm opacity-80">
          Every public Theseus publication carries a cryptographic provenance trail. A reader who
          asks <em>"is this what Theseus actually said, on this date, with this evidence base?"</em>{" "}
          should be able to answer it without taking our word for it. This page is the contract.
        </p>

        <h2 className="mt-8 text-lg font-semibold">What gets signed</h2>
        <p className="mt-2 text-sm">
          At the moment a conclusion or article transitions to <em>published</em>, the noosphere
          CLI computes a SHA-256 over a canonical encoding of:
        </p>
        <ul className="mt-2 ml-5 list-disc text-sm">
          <li>the conclusion text (Markdown, normalized for whitespace)</li>
          <li>the methodology profile id(s) attached to it</li>
          <li>the citation set</li>
          <li>both discounted and stated confidence</li>
          <li>the methodology quality score (MQS, prompt 01) at the time of publication</li>
          <li>the publication timestamp, slug, and version</li>
        </ul>
        <p className="mt-2 text-sm">
          The hash is then signed with an Ed25519 key the firm controls. Both the canonical input
          and the signature are persisted alongside the published row, and served verbatim from
          a public endpoint:
        </p>
        <pre className="mt-2 overflow-x-auto rounded bg-stone-900/10 p-3 font-mono text-xs">
          <code>GET /api/public/signature/&lt;slug&gt;?version=&lt;n&gt;</code>
        </pre>

        <h2 className="mt-8 text-lg font-semibold">Canonicalization rules</h2>
        <p className="mt-2 text-sm">
          For the verifier to land on the exact same hash bytes as the signer, the canonicalizer
          is code-defined and identical on both sides
          (<code className="font-mono text-xs">noosphere/ledger/canonicalize.py</code> and the TS
          mirror in <code className="font-mono text-xs">publicationService.ts</code>):
        </p>
        <ul className="mt-2 ml-5 list-disc text-sm">
          <li>Markdown is Unicode-NFC-normalized; CRLF and CR collapse to LF.</li>
          <li>Trailing whitespace is stripped from every line.</li>
          <li>Runs of three or more blank lines collapse to one blank line.</li>
          <li>Leading and trailing blank lines are stripped.</li>
          <li>JSON is encoded with sorted keys and tight separators.</li>
          <li>Floats are rounded to 6 decimal places.</li>
          <li>Citations are sorted by (format, block) so reorder is invisible but adds/removes are not.</li>
          <li>Timestamps are rendered as second-precision ISO-8601 Z (UTC).</li>
        </ul>

        <h2 className="mt-8 text-lg font-semibold">Key management &amp; rotation</h2>
        <p className="mt-2 text-sm">
          Private signing keys never live in this web app. They live on the operator's machine
          under <code className="font-mono text-xs">~/.theseus/keys/publication/</code>. New {/* pragma: signing-key-allowed — public /proof page describes the path; no import. */}
          publications are signed with the active key. Older keys remain in the keyring so
          historical material continues to verify; rotation generates a fresh active key without
          invalidating anything previously signed. A key can be revoked, in which case
          publications signed <em>after</em> the revocation timestamp fail verification, but
          publications signed before it remain valid (the historical record stays trustworthy).
        </p>
        <div className="mt-3 rounded border border-stone-500/40 bg-stone-500/5 p-3 text-xs">
          <div className="opacity-70">Active publication key fingerprint</div>
          <div className="font-mono text-sm">
            {activeFingerprint ?? <span className="opacity-50">not yet generated</span>}
          </div>
        </div>

        <h2 className="mt-8 text-lg font-semibold">How to verify a publication yourself</h2>
        <p className="mt-2 text-sm">
          Install the noosphere CLI from the firm's package, then run:
        </p>
        <pre className="mt-2 overflow-x-auto rounded bg-stone-900/10 p-3 font-mono text-xs">
          <code>{`noosphere ledger verify-publication <slug>
noosphere ledger verify-publication <slug> --from-url https://<host>/api/public/signature/<slug>`}</code>
        </pre>
        <p className="mt-2 text-sm">
          The CLI fetches the signature, recomputes the canonical hash from the live database
          row, and checks the Ed25519 signature against the keyring. A mismatch means either the
          database has been mutated since signing, or the signature is stale (canonical inputs
          changed and the publication needs to be re-signed). Either is a bug the firm wants to
          know about; we surface it with a red banner on the publication page rather than
          silently hiding the failure.
        </p>

        <h2 className="mt-8 text-lg font-semibold">Source</h2>
        <p className="mt-2 text-sm">
          Canonicalizer:{" "}
          <code className="font-mono text-xs">noosphere/noosphere/ledger/canonicalize.py</code>
          {" · "}
          Signing primitives:{" "}
          <code className="font-mono text-xs">
            noosphere/noosphere/ledger/publication_signing.py
          </code>
          {" · "}
          Web mirror:{" "}
          <code className="font-mono text-xs">theseus-codex/src/lib/publicationService.ts</code>
        </p>

        <p className="mt-8 text-xs opacity-60">
          <Link className="underline" href="/">
            ← Back to the firm's published record
          </Link>
        </p>
      </main>
    </>
  );
}
