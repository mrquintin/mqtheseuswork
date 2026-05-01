from __future__ import annotations

from noosphere.cli_commands.embed_backfill import run_backfill
from noosphere.config import get_settings
from noosphere.embedding_pipeline import _embedding_id, embed_and_store
from noosphere.models import Conclusion
from noosphere.store import Store, StoredConclusion, StoredEmbedding
from sqlmodel import select


class FakeEmbeddingClient:
    model_name = "fake-embed"

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(len(text)), float(index), 1.0] for index, text in enumerate(texts)]


class FailingEmbeddingClient:
    model_name = "fake-embed"

    def encode(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("503 Service Unavailable")


def _file_store(tmp_path) -> tuple[str, Store]:
    db_url = f"sqlite:///{tmp_path / 'embeddings.db'}"
    return db_url, Store.from_database_url(db_url)


def test_embed_and_store_is_idempotent(monkeypatch, tmp_path) -> None:
    db_url, st = _file_store(tmp_path)
    monkeypatch.setenv("THESEUS_DATABASE_URL", db_url)
    monkeypatch.setenv("THESEUS_AUTO_EMBED_IN_TESTS", "1")
    get_settings.cache_clear()
    fake = FakeEmbeddingClient()
    monkeypatch.setattr("noosphere.embedding_pipeline._get_embedding_client", lambda: fake)

    conclusion = Conclusion(id="conclusion_embed_unit", text="Automatic embeddings should be idempotent.")
    try:
        assert embed_and_store(conclusion) is True
        assert embed_and_store(conclusion) is True
    finally:
        get_settings.cache_clear()

    model_name = st.active_embedding_model_name()
    vector = st.get_embedding_vector(_embedding_id("conclusion", conclusion.id, model_name))
    assert vector == [float(len(conclusion.text)), 0.0, 1.0]
    assert fake.calls == 1


def test_embed_and_store_tolerates_provider_503(monkeypatch, tmp_path, caplog) -> None:
    db_url, st = _file_store(tmp_path)
    monkeypatch.setenv("THESEUS_DATABASE_URL", db_url)
    monkeypatch.setenv("THESEUS_AUTO_EMBED_IN_TESTS", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "noosphere.embedding_pipeline._get_embedding_client",
        lambda: FailingEmbeddingClient(),
    )

    conclusion = Conclusion(id="conclusion_embed_503", text="The provider is temporarily unavailable.")
    try:
        assert embed_and_store(conclusion) is False
    finally:
        get_settings.cache_clear()

    with st.session() as s:
        assert len(s.exec(select(StoredEmbedding)).all()) == 0
    assert "503 Service Unavailable" in caplog.text


def test_put_conclusion_writes_embedding(monkeypatch, tmp_path) -> None:
    _db_url, st = _file_store(tmp_path)
    monkeypatch.setenv("THESEUS_AUTO_EMBED_IN_TESTS", "1")
    fake = FakeEmbeddingClient()
    monkeypatch.setattr("noosphere.embedding_pipeline._get_embedding_client", lambda: fake)

    conclusion = Conclusion(id="conclusion_embed_integration", text="A freshly created conclusion becomes explorable.")
    st.put_conclusion(conclusion)

    model_name = st.active_embedding_model_name()
    vector = st.get_embedding_vector(_embedding_id("conclusion", conclusion.id, model_name))
    assert vector == [float(len(conclusion.text)), 0.0, 1.0]


def test_embed_backfill_embeds_unembedded_corpus(tmp_path) -> None:
    _db_url, st = _file_store(tmp_path)
    with st.session() as s:
        for index in range(100):
            conclusion = Conclusion(
                id=f"conclusion_backfill_{index}",
                text=f"Backfill conclusion {index} should receive an embedding.",
            )
            s.add(StoredConclusion(id=conclusion.id, payload_json=conclusion.model_dump_json()))
        s.commit()

    report = run_backfill(store=st, max_per_run=1000, client=FakeEmbeddingClient())

    assert report.count == 100
    assert report.remaining == 0
    with st.session() as s:
        assert len(s.exec(select(StoredEmbedding)).all()) == 100
