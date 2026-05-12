type SourceChunk = {
  id: string;
  index: number;
  text: string;
  headingHint: string | null;
};

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function excerpt(text: string, max = 120): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 3).trimEnd()}...`;
}

export default function SourceStructurePanel({
  chunks,
}: {
  chunks: SourceChunk[];
}) {
  const totalWords = chunks.reduce((count, chunk) => count + wordCount(chunk.text), 0);
  const sections = chunks.filter((chunk) => chunk.headingHint?.trim()).slice(0, 6);
  const sample = sections.length ? sections : chunks.slice(0, 4);

  return (
    <section className="portal-card transcript-source-structure" aria-labelledby="source-structure-title">
      <div className="transcript-methodology-head">
        <div>
          <h2 className="mono" id="source-structure-title">
            Source structure
          </h2>
          <p>
            {chunks.length} chunks / {totalWords.toLocaleString()} words
            {sections.length > 0 ? ` / ${sections.length} headings` : " / no headings detected"}
          </p>
        </div>
        <span className="mono">{sections.length} sections</span>
      </div>
      {sample.length ? (
        <ol className="transcript-source-structure-list">
          {sample.map((chunk) => (
            <li key={chunk.id}>
              <a href={`#chunk-${chunk.id}`}>
                <span className="mono">[{chunk.index + 1}]</span>
                <strong>{chunk.headingHint || excerpt(chunk.text, 64)}</strong>
              </a>
            </li>
          ))}
        </ol>
      ) : (
        <p className="transcript-related-empty">No stable source chunks have been generated yet.</p>
      )}
    </section>
  );
}
