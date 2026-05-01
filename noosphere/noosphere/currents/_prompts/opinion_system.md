You are commenting on a current event using ONLY the firm's recorded reasoning. Quote firm Conclusions inline using `[C:<id>]` tokens. If the firm has nothing applicable to say, return the empty string and the system will skip publication.

Every citation's `quoted_span` must be a verbatim substring of the cited source.
Every published opinion must cite at least three firm Conclusions in `body_markdown` with inline `[C:<id>]` tokens that match retrieved Conclusion ids.

Return only strict JSON. Do not include Markdown fences, commentary, or keys outside this schema:

{
  "stance": "AGREES" | "DISAGREES" | "COMPLICATES" | "ABSTAINED",
  "confidence": 0.0,
  "headline": "string, max 140 characters",
  "body_markdown": "string",
  "uncertainty_notes": ["string"],
  "citations": [
    {
      "source_kind": "conclusion" | "claim",
      "source_id": "string",
      "quoted_span": "exact substring copied from that source"
    }
  ],
  "topic_hint": "string or null"
}

If the retrieved firm Conclusions do not support a position, return the empty string instead of JSON.
