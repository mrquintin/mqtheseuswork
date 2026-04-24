import type { PublicOpinion } from "@/lib/currentsTypes";
import { STANCE_LABEL } from "@/lib/stanceStyles";
import { FollowupChat } from "./FollowupChat";

// Server-safe. Displays metadata and uncertainty notes, and anchors the
// `#ask` region where prompt 13 will mount the follow-up chat component.
export function AuditTrail({ op }: { op: PublicOpinion }) {
  return (
    <section
      aria-label="Audit trail"
      data-testid="audit-trail"
      style={{
        background: "var(--currents-bg-elevated)",
        border: "1px solid var(--currents-border)",
        borderRadius: 3,
        padding: "1rem 1.1rem",
      }}
    >
      <h3
        style={{
          margin: "0 0 0.8rem",
          fontSize: "0.78rem",
          color: "var(--currents-parchment-dim)",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          fontWeight: 600,
        }}
      >
        Audit trail
      </h3>

      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          rowGap: "0.45rem",
          columnGap: "0.9rem",
          margin: 0,
          fontSize: "0.85rem",
          color: "var(--currents-parchment)",
        }}
      >
        <dt style={metaLabel}>Opinion id</dt>
        <dd style={metaValue}>
          <code>{op.id}</code>
        </dd>

        <dt style={metaLabel}>Event id</dt>
        <dd style={metaValue}>
          <code>{op.event_id}</code>
        </dd>

        <dt style={metaLabel}>Author</dt>
        <dd style={metaValue}>
          @{op.event_author_handle}
          {" · "}
          <a
            href={op.event_source_url}
            target="_blank"
            rel="noopener nofollow ugc"
          >
            source
          </a>
        </dd>

        <dt style={metaLabel}>Captured</dt>
        <dd style={metaValue}>
          <time dateTime={op.event_captured_at}>{op.event_captured_at}</time>
        </dd>

        <dt style={metaLabel}>Generated</dt>
        <dd style={metaValue}>
          <time dateTime={op.generated_at}>{op.generated_at}</time>
        </dd>

        <dt style={metaLabel}>Stance</dt>
        <dd style={metaValue}>{STANCE_LABEL[op.stance]}</dd>

        <dt style={metaLabel}>Confidence</dt>
        <dd style={metaValue}>{op.confidence.toFixed(2)}</dd>

        {op.topic_hint ? (
          <>
            <dt style={metaLabel}>Topic</dt>
            <dd style={metaValue}>{op.topic_hint}</dd>
          </>
        ) : null}

        <dt style={metaLabel}>Citations</dt>
        <dd style={metaValue}>{op.citations.length}</dd>

        {op.revoked ? (
          <>
            <dt style={metaLabel}>Status</dt>
            <dd style={{ ...metaValue, color: "var(--currents-amber, #c79a3a)" }}>
              Revoked
            </dd>
          </>
        ) : null}
      </dl>

      {op.uncertainty_notes.length > 0 ? (
        <div
          data-testid="uncertainty-notes"
          style={{
            marginTop: "1rem",
            padding: "0.7rem 0.85rem",
            background: "var(--currents-surface)",
            border: "1px solid var(--currents-border)",
            borderLeft: "3px solid var(--currents-amber, #c79a3a)",
            borderRadius: 3,
          }}
        >
          <div
            style={{
              fontSize: "0.72rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--currents-parchment-dim)",
              marginBottom: "0.35rem",
            }}
          >
            Uncertainty notes
          </div>
          <ul
            style={{
              margin: 0,
              paddingLeft: "1.1rem",
              fontSize: "0.84rem",
              color: "var(--currents-parchment-dim)",
              fontStyle: "italic",
              lineHeight: 1.5,
            }}
          >
            {op.uncertainty_notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div
        id="ask"
        data-testid="ask-anchor"
        style={{
          marginTop: "1.25rem",
          paddingTop: "1rem",
          borderTop: "1px solid var(--currents-border)",
        }}
      >
        <h4
          style={{
            margin: "0 0 0.4rem",
            fontSize: "0.78rem",
            color: "var(--currents-parchment-dim)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            fontWeight: 600,
          }}
        >
          Ask a follow-up
        </h4>
        <FollowupChat opinionId={op.id} />
      </div>
    </section>
  );
}

const metaLabel: React.CSSProperties = {
  fontSize: "0.72rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "var(--currents-parchment-dim)",
  margin: 0,
};

const metaValue: React.CSSProperties = {
  margin: 0,
  fontSize: "0.85rem",
  color: "var(--currents-parchment)",
  wordBreak: "break-word",
};
