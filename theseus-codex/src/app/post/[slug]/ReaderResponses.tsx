/**
 * "Reader responses" appendix on a public blog post.
 *
 * The post route operates over an Upload row, but reader responses
 * are anchored to the matching `PublishedConclusion` (the response
 * form treats the upload as a target via the same id mapping the
 * `responseTargetForPost` helper produces). When no PublishedConclusion
 * exists, no responses can exist either, and we render nothing.
 *
 * Same double-opt-in rules as `c/[slug]/ReaderResponses.tsx`:
 * publish-consent on the response AND publishConfirmed on the reply.
 */

import { db } from "@/lib/db";
import { listPublicReaderResponses } from "@/lib/responseTriageApi";

type ReaderResponsesProps = {
  organizationId: string;
  /** Upload id (the public post is an Upload row). */
  postId: string;
  postSlug: string;
};

export default async function ReaderResponses({
  organizationId,
  postId,
  postSlug,
}: ReaderResponsesProps) {
  const published = await db.publishedConclusion.findFirst({
    where: {
      organizationId,
      OR: [
        { id: postId },
        { sourceConclusionId: postId },
        { sourceConclusionId: `article:${postId}` },
        { slug: postSlug },
      ],
    },
    orderBy: { publishedAt: "desc" },
    select: { id: true },
  });
  if (!published) return null;

  const entries = await listPublicReaderResponses(organizationId, published.id);
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
