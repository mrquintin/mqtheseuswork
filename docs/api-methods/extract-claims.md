# Method note: `POST /v1/extract-claims`

## What it does

Runs the same **LLM-backed JSON claim extractor** used inside Noosphere (`ClaimExtractor`), on a **single text span** supplied by the researcher. Output is a list of structured claims (text, type, hedges, evidence pointers).

## Limitations

- **No document structure**: headings, footnotes, and tables are flattened to plain text in the request body.
- **No cache**: the researcher API uses `store=None`, so repeated identical requests still invoke the model.
- **LLM variance**: model and temperature follow `THESEUS_*` / provider defaults; version strings appear in response headers alongside `X-Theseus-Git-SHA`.

## Safety

This endpoint must not receive personal data you are not allowed to process. The acceptable-use policy applies.
