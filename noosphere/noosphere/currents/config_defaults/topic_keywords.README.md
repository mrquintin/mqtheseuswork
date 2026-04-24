# Topic-keyword search queries

Populate `topic_keywords.json` with query strings for X's `/2/tweets/search/recent` endpoint. Examples:
- `"capital allocation venture"` — broad topic
- `"\"methodological yield\""` — exact phrase

Match topics to the firm's active Noosphere conclusions. Queries that return posts with no Noosphere coverage will be abstained on by the relevance gate (prompt 03); they just waste API quota.

An empty list disables the keyword-search path entirely.
