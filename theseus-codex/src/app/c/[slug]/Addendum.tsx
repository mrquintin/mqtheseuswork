import {
  formatAddendumDate,
  type AddendumRecord,
} from "@/lib/addendumApi";

/**
 * Public addendum block for `/c/[slug]` (the firm's reasoned
 * conclusions). Sibling of `app/post/[slug]/Addendum.tsx` — the two
 * files are separate so each route can tune its visual treatment to
 * the surrounding page chrome without one accidentally importing the
 * other's CSS contract.
 *
 * Spec (prompt 43): "On <date> the firm re-reviewed this article and
 * found <summary>. See the appended note." Original conclusion text
 * is immutable; addenda render below as visibly later content.
 */

export type ConclusionAddendaProps = {
  addenda: AddendumRecord[];
};

export default function ConclusionAddenda({ addenda }: ConclusionAddendaProps) {
  if (!addenda.length) return null;
  return (
    <section
      aria-labelledby="conclusion-addenda-title"
      className="public-section conclusion-addenda"
      data-testid="conclusion-addenda"
    >
      <h2 id="conclusion-addenda-title" className="mono">
        Later view · self-critique
      </h2>
      <ol
        className="conclusion-addenda-list"
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
        }}
      >
        {addenda.map((addendum) => (
          <ConclusionAddendumBlock addendum={addendum} key={addendum.id} />
        ))}
      </ol>
    </section>
  );
}

function ConclusionAddendumBlock({ addendum }: { addendum: AddendumRecord }) {
  const publishedAt = addendum.publishedAt ?? addendum.createdAt;
  const dateLabel = formatAddendumDate(new Date(publishedAt));
  return (
    <li
      className="public-card"
      data-testid="conclusion-addendum"
      data-addendum-id={addendum.id}
    >
      <p className="public-muted mono" style={{ marginBottom: "0.4rem" }}>
        Added {dateLabel}
      </p>
      <p style={{ marginTop: 0 }}>
        On {dateLabel} the firm re-reviewed this article and found{" "}
        <strong>{addendum.summary}</strong>. See the appended note.
      </p>
      {addendum.body ? (
        <div
          className="public-article-body"
          style={{ whiteSpace: "pre-wrap" }}
        >
          {addendum.body}
        </div>
      ) : null}
    </li>
  );
}
