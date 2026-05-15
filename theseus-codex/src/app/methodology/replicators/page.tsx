import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { loadReplicators, type ReplicatorRow } from "@/lib/replicators";

export const metadata: Metadata = {
  title: "Methodology · researchers who have replicated us",
  description:
    "Outside researchers who have run the firm's replication harness end-to-end and produced a signed reproducibility certificate. The certificate certifies that the harness reproduced the firm's published numbers on the researcher's hardware — it does not vouch for the underlying claims.",
  openGraph: {
    title: "Researchers who have replicated Theseus",
    description:
      "Signed reproducibility certificates from outside replications of the firm's empirical claims.",
    type: "website",
  },
};

export const dynamic = "force-static";

export default async function ReplicatorsPage() {
  const founder = await getFounder();
  const { rows, filteredCount, filterReasons } = loadReplicators();
  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <section className="public-section">
          <p
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--public-muted, #888)",
            }}
          >
            <Link href="/methodology">Methodology</Link>
            <span aria-hidden> · </span>
            <Link href="/methodology/replicate">Replicate</Link>
            <span aria-hidden> · </span>
            <span>Replicators</span>
          </p>
          <h1 className="public-title">Researchers who have replicated us</h1>
          <p className="public-lede">
            Each row below is an outside researcher who ran the firm's
            replication harness end-to-end and whose numbers matched
            the firm's recorded numbers within the published
            tolerance. Each row corresponds to a signed
            reproducibility certificate emitted by{" "}
            <code>python -m replication.lib.verify ... --emit-certificate</code>{" "}
            and counter-signed with the firm's publication key.
          </p>
        </section>

        <section className="public-section">
          <h2>What a certificate certifies, and what it doesn't</h2>
          <p>
            A certificate is narrow on purpose. It certifies, only,{" "}
            <strong>that the harness reproduced the firm's
            published numbers on the named researcher's hardware</strong>
            . It does <em>not</em> certify that the firm's numbers are
            correct; the firm can be wrong, and an outside replication
            of a wrong number is still a valid certificate of "we
            matched what was published". It does not certify the
            replicator's identity — names and affiliations are claimed
            by the replicator, and the firm gates the public row
            behind explicit consent but does not perform identity
            verification.
          </p>
          <p className="public-muted">
            If a certificate's claims are wrong, the corresponding row
            here is wrong with it; the certificate is a snapshot of
            agreement, not an oracle. The right escalation for a
            doubted certificate is to{" "}
            <Link href="/methodology/replicate">run the harness</Link>{" "}
            yourself and see whether your numbers agree.
          </p>
        </section>

        <section className="public-section">
          <h2>The list</h2>
          {rows.length === 0 ? (
            <EmptyState />
          ) : (
            <ReplicatorTable rows={rows} />
          )}
          {filteredCount > 0 && (
            <details
              style={{
                marginTop: "1.5rem",
                fontSize: "0.85rem",
                color: "var(--public-muted, #888)",
              }}
            >
              <summary>
                {filteredCount} certificate
                {filteredCount === 1 ? "" : "s"} filtered from the
                public list (consent, schema, or signature). Click for
                reasons.
              </summary>
              <ul style={{ marginTop: "0.5rem" }}>
                {filterReasons.map((reason, i) => (
                  <li key={i}>
                    <code style={{ fontSize: "0.78rem" }}>{reason}</code>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>

        <section className="public-section">
          <h2>How a row gets here</h2>
          <ol>
            <li>
              A researcher clones the repo and runs{" "}
              <code>make all</code> from <code>replication/</code>.
            </li>
            <li>
              <code>make verify PRIOR_RUN=...</code> returns verdict{" "}
              <code>match</code> against one of the firm's recorded
              baseline runs.
            </li>
            <li>
              The researcher (or the firm, on the researcher's
              behalf) calls{" "}
              <code>
                python -m replication.lib.verify ...
                --emit-certificate
              </code>
              , supplying the researcher's name, affiliation, and the{" "}
              <code>--consent-public</code> flag if they consent to
              be listed here.
            </li>
            <li>
              The firm reviews the unsigned certificate, signs it
              with the publication key, and commits it under{" "}
              <code>replication/certificates/</code>.
            </li>
            <li>
              The next build of this page picks it up. There is no
              moderation step beyond the signature: the firm either
              signs the certificate or doesn't.
            </li>
          </ol>
        </section>

        <section className="public-section">
          <h2>Verifying a certificate yourself</h2>
          <p>
            Every row carries the canonical hash (truncated, full
            value in the JSON file) and the fingerprint of the
            signing key. To verify a certificate end-to-end without
            trusting this page:
          </p>
          <pre style={preStyle}>{`# from the repo root
python -m replication.lib.certificate verify \\
    replication/certificates/<row id>.json
# exits 0 iff the canonical bytes hash to the recorded hash and
# the Ed25519 signature verifies against the firm's verify key.`}</pre>
          <p className="public-muted">
            The firm's verify key for the active fingerprint is
            published alongside the keyring rotation log; see{" "}
            <Link href="/methodology/replicate">/methodology/replicate</Link>{" "}
            for the canonical pointer.
          </p>
        </section>

        <section className="public-section">
          <h2>Related</h2>
          <ul style={{ listStyle: "none", padding: 0 }}>
            <li>
              <Link href="/methodology/replicate">
                Methodology · Replicate · how to run the harness yourself
              </Link>
            </li>
            <li>
              <Link href="/methodology/benchmark/qh">
                Quintin Hypothesis Benchmark · the numbers being
                replicated
              </Link>
            </li>
          </ul>
        </section>
      </main>
    </>
  );
}

function EmptyState() {
  return (
    <div
      style={{
        border: "1px dashed var(--public-muted, #555)",
        padding: "1.25rem",
        borderRadius: "4px",
        fontSize: "0.95rem",
      }}
    >
      <p style={{ margin: 0 }}>
        No certified replications have been published yet. The page is
        live — it will populate as soon as the firm signs the first
        certificate. If you have already run the harness and seen{" "}
        <code>match</code>, please{" "}
        <Link href="/methodology/replicate">submit your run</Link>.
      </p>
    </div>
  );
}

function ReplicatorTable({ rows }: { rows: ReplicatorRow[] }) {
  return (
    <table className="public-table">
      <thead>
        <tr>
          <th>Researcher</th>
          <th>Affiliation</th>
          <th>Benchmark</th>
          <th>Runner</th>
          <th>Models</th>
          <th>Det.</th>
          <th>Signed</th>
          <th>Hash</th>
          <th>Key</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.name}</td>
            <td>{row.affiliation || <span className="public-muted">—</span>}</td>
            <td>
              <code>{row.benchmarkVersion}</code>
            </td>
            <td>
              <code>{row.runner}</code>
            </td>
            <td>
              <code>{row.models.join(", ")}</code>
            </td>
            <td>{row.deterministic ? "✓" : "—"}</td>
            <td>
              <time dateTime={row.signedAt}>{row.signedAt.slice(0, 10)}</time>
            </td>
            <td>
              <code style={{ fontSize: "0.78rem" }}>{row.canonicalHashShort}…</code>
            </td>
            <td>
              <code style={{ fontSize: "0.78rem" }}>{row.keyFingerprint}</code>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const preStyle: React.CSSProperties = {
  background: "var(--public-bg-soft, #1a1a1a)",
  color: "var(--public-fg, #eee)",
  padding: "1rem",
  borderRadius: "4px",
  fontSize: "0.82rem",
  lineHeight: 1.5,
  overflowX: "auto",
};
