/**
 * "Reader responses" appendix on a published conclusion page.
 *
 * Renders only entries where (a) the responder explicitly consented to
 * publication on the form, and (b) the founder confirmed a public
 * reply on the workspace. Anything missing either confirmation is not
 * shown — symmetric double opt-in protects against unilateral
 * publication from either side.
 *
 * The component is a server component and pulls its own data so the
 * conclusion page doesn't have to know about the triage tables.
 */

import { listPublicReaderResponses } from "@/lib/responseTriageApi";
import { resolvePublicOrganizationId } from "@/lib/conclusionsRead";

type ReaderResponsesProps = {
  publishedConclusionId: string;
};

export default async function ReaderResponses({ publishedConclusionId }: ReaderResponsesProps) {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return null;
  const entries = await listPublicReaderResponses(organizationId, publishedConclusionId);
  if (entries.length === 0) return null;

  return (
    <section
      aria-labelledby="reader-responses-heading"
      style={{
        borderTop: "1px solid var(--stroke)",
        marginTop: "3rem",
        paddingTop: "2rem",
      }}
    >
      <h2
        id="reader-responses-heading"
        style={{
          color: "var(--amber)",
          fontFamily: "'Cinzel Decorative', serif",
          fontSize: "1.1rem",
          letterSpacing: "0.22em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        From the responses
      </h2>
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.22em",
          margin: "0.4rem 0 1.4rem",
          textTransform: "uppercase",
        }}
      >
        Reader response · firm reply
      </p>
      <ol style={{ display: "grid", gap: "1.4rem", listStyle: "none", margin: 0, padding: 0 }}>
        {entries.map((entry) => (
          <li
            key={entry.responseId}
            style={{
              borderLeft: "2px solid var(--amber-dim)",
              paddingLeft: "1rem",
            }}
          >
            <p
              className="mono"
              style={{
                color: "var(--amber-dim)",
                fontSize: "0.6rem",
                letterSpacing: "0.18em",
                margin: 0,
                textTransform: "uppercase",
              }}
            >
              {entry.responderLabel} · {entry.repliedAt.toISOString().slice(0, 10)}
            </p>
            <p
              style={{
                color: "var(--parchment)",
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                lineHeight: 1.55,
                margin: "0.4rem 0 0.7rem",
                whiteSpace: "pre-wrap",
              }}
            >
              {entry.responseBody}
            </p>
            {entry.responseCitationUrl ? (
              <p style={{ margin: "0 0 0.6rem" }}>
                <a
                  className="mono"
                  href={entry.responseCitationUrl}
                  rel="noreferrer"
                  target="_blank"
                  style={{
                    color: "var(--amber-dim)",
                    fontSize: "0.65rem",
                    textDecoration: "none",
                  }}
                >
                  {entry.responseCitationUrl}
                </a>
              </p>
            ) : null}
            <p
              className="mono"
              style={{
                color: "var(--amber-dim)",
                fontSize: "0.6rem",
                letterSpacing: "0.18em",
                margin: "0.4rem 0 0.2rem",
                textTransform: "uppercase",
              }}
            >
              Theseus
            </p>
            <p
              style={{
                color: "var(--parchment)",
                fontFamily: "'EB Garamond', serif",
                lineHeight: 1.55,
                margin: 0,
                whiteSpace: "pre-wrap",
              }}
            >
              {entry.replyBody}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
