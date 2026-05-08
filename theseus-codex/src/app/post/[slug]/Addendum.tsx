import {
  formatAddendumDate,
  type AddendumRecord,
} from "@/lib/addendumApi";

/**
 * Public addendum block for `/post/[slug]`.
 *
 * Spec (prompt 43): "On <date> the firm re-reviewed this article and
 * found <summary>. See the appended note." The original article body
 * is rendered above this block and is *not* mutated — the addendum
 * is visibly later content, never a stealth rewrite.
 *
 * Multiple published addenda render oldest-first so a printed page
 * reads as a chronological errata sheet.
 */

export type PostAddendaProps = {
  addenda: AddendumRecord[];
};

export default function PostAddenda({ addenda }: PostAddendaProps) {
  if (!addenda.length) return null;
  return (
    <section
      aria-labelledby="post-addenda-title"
      className="post-addenda"
      data-testid="post-addenda"
      style={{
        marginTop: "3rem",
        paddingTop: "1.5rem",
        borderTop: "1px solid var(--amber-dim)",
      }}
    >
      <h2
        id="post-addenda-title"
        className="mono"
        style={{
          color: "var(--amber)",
          fontSize: "0.7rem",
          letterSpacing: "0.28em",
          textTransform: "uppercase",
          margin: "0 0 1.5rem",
        }}
      >
        Later view · self-critique
      </h2>
      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "1.5rem",
        }}
      >
        {addenda.map((addendum) => (
          <PostAddendumBlock addendum={addendum} key={addendum.id} />
        ))}
      </ol>
    </section>
  );
}

function PostAddendumBlock({ addendum }: { addendum: AddendumRecord }) {
  const publishedAt = addendum.publishedAt ?? addendum.createdAt;
  const dateLabel = formatAddendumDate(new Date(publishedAt));
  return (
    <li
      data-testid="post-addendum"
      data-addendum-id={addendum.id}
      style={{
        border: "1px solid var(--amber-dim)",
        borderRadius: "6px",
        padding: "1.2rem 1.4rem",
        background: "rgba(212,160,23,0.04)",
      }}
    >
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.26em",
          textTransform: "uppercase",
          margin: "0 0 0.6rem",
        }}
      >
        Added {dateLabel}
      </p>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          color: "var(--parchment)",
          fontSize: "1.05rem",
          lineHeight: 1.55,
          margin: "0 0 0.8rem",
        }}
      >
        On {dateLabel} the firm re-reviewed this article and found{" "}
        <strong>{addendum.summary}</strong>. See the appended note.
      </p>
      {addendum.body ? (
        <div
          className="public-article-body"
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--parchment)",
            fontSize: "1rem",
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
          }}
        >
          {addendum.body}
        </div>
      ) : null}
    </li>
  );
}
