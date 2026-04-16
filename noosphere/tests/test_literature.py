"""Literature text ingestion creates literature-origin claims."""

from __future__ import annotations

from noosphere.literature import ingest_literature_text
from noosphere.models import ClaimOrigin
from noosphere.store import Store


def test_ingest_literature_text_creates_claims() -> None:
    st = Store.from_database_url("sqlite:///:memory:")
    body = (
        "ABSTRACT\n\n"
        "This is a long enough abstract about ethics and governance to form a chunk. "
        "It continues with more philosophical content for retrieval testing purposes.\n\n"
        "INTRODUCTION\n\n"
        "The introduction elaborates on the same themes with sufficient length for chunking."
    )
    res = ingest_literature_text(
        st,
        title="Test Paper",
        author="Jane Doe",
        body=body,
        connector="manual",
        license_status="open_access",
    )
    assert res.artifact_id
    assert res.claims_written >= 1
    found = False
    for cid in st.list_claim_ids():
        c = st.get_claim(cid)
        if c and c.claim_origin == ClaimOrigin.LITERATURE and c.source_id == res.artifact_id:
            found = True
            break
    assert found
