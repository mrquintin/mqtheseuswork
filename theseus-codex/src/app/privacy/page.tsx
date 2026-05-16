import {
  RETENTION_POLICIES,
  formatTtl,
  type RetentionPolicy,
} from "@/lib/retentionApi";

/**
 * Public /privacy page.
 *
 * Generated from the retention policy table — there is no hand-written
 * prose here that can drift from runner behavior. Each policy renders
 * its own paragraph; the build step
 * `scripts/check_privacy_page_consistency.py` fails the deploy if the
 * Python policy table and the TS mirror disagree on any field that
 * shows up below.
 */

export const dynamic = "force-static";
export const metadata = {
  title: "Privacy & Data Retention",
};

function actionLabel(p: RetentionPolicy): string {
  switch (p.action) {
    case "delete":
      return "deletion";
    case "rollup_and_delete":
      return "aggregation, then deletion of raw rows";
    case "archive":
      return "archival with a tombstone marker";
    case "delete_with_confirmation":
      return "deletion with founder confirmation";
    case "keep_while_source_exists":
      return "retention while the source document exists";
  }
}

function overrideLabel(p: RetentionPolicy): string {
  switch (p.override) {
    case "unrestricted":
      return "the founder can adjust this lifecycle freely";
    case "confirm_required":
      return "the founder must confirm each deletion individually";
    case "locked":
      return "this lifecycle is locked: it cannot be auto-executed or shortened";
  }
}

export default function PrivacyPage() {
  return (
    <main className="public-container mx-auto max-w-3xl px-6 py-12 leading-relaxed">
      <h1 className="text-3xl font-semibold mb-2">Privacy & Data Retention</h1>
      <p className="text-sm mb-8" style={{ color: "var(--public-muted)" }}>
        Generated from the firm&apos;s machine-readable retention policy.
        Behavior in code is bound to the prose below.
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-medium mb-3">What we keep, and for how long</h2>
        <p className="mb-6">
          The firm holds the following classes of data. Each row below
          shows the retention period, what happens at the end of that
          period, and the founder&apos;s authority to override it.
        </p>
        <div className="overflow-x-auto" tabIndex={0}>
          <table className="w-full border-collapse text-sm" data-testid="retention-table">
            <thead>
              <tr className="border-b border-gray-300 text-left">
                <th className="py-2 pr-4">Class</th>
                <th className="py-2 pr-4">Retention</th>
                <th className="py-2 pr-4">At end of life</th>
                <th className="py-2 pr-4">Override</th>
              </tr>
            </thead>
            <tbody>
              {RETENTION_POLICIES.map((p) => (
                <tr
                  key={p.key}
                  data-policy-key={p.key}
                  className="border-b border-gray-200 align-top"
                >
                  <td className="py-2 pr-4 font-medium">{p.label}</td>
                  <td className="py-2 pr-4" data-field="ttl">
                    {formatTtl(p)}
                  </td>
                  <td className="py-2 pr-4">{actionLabel(p)}</td>
                  <td className="py-2 pr-4">{overrideLabel(p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-medium mb-3">How each class is handled</h2>
        {RETENTION_POLICIES.map((p) => (
          <div
            key={p.key}
            data-policy-key={p.key}
            className="mb-5"
          >
            <h3 className="font-medium">{p.label}</h3>
            <p className="text-sm text-gray-700" data-field="summary">
              {p.privacySummary}
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--public-muted)" }}>
              Basis: {p.legalBasis}.
            </p>
          </div>
        ))}
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-medium mb-3">Data subject requests</h2>
        <p className="mb-3">
          You can ask for a complete report of what the firm holds about
          you, or request deletion. The firm provides a JSON
          &quot;everything we have&quot; report and, on confirmation, a
          deletion plan that walks every class above.
        </p>
        <p className="text-sm text-gray-700">
          Send the request to{" "}
          <a className="underline" href="mailto:privacy@theseus.example">
            privacy@theseus.example
          </a>
          . Identify yourself by email or ORCID. The request runs against
          the same retention table shown above; nothing is held back.
        </p>
      </section>

      <p className="text-xs mt-12" style={{ color: "var(--public-muted)" }}>
        This page is generated from{" "}
        <code>noosphere/decay/retention_policies.py</code>. If the
        machine-readable policy and this page disagree, the deploy
        build fails.
      </p>
    </main>
  );
}
