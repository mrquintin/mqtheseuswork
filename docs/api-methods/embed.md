# Method note: `POST /v1/embed`

## What it does

Encodes each input string with the configured **SentenceTransformer** (`THESEUS_EMBEDDING_MODEL_NAME`, `THESEUS_EMBEDDING_DEVICE`).

## Limits

- Up to **64** strings per request; each string **≤ 8000** characters.
- First call may **download** model weights; cold-start latency can be large.

## Reproducibility

Embedding space changes when the encoder model changes. Published work should record `X-Theseus-Git-SHA` and the embedding model id from your deployment notes.
