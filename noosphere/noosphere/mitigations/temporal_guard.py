"""Temporal provenance: untrusted rows must not silently assert historical effective_at."""


def dialectic_may_set_effective_at(obj: dict) -> bool:
    """
    Only allow explicit backdated / historical ``effective_at`` from Dialectic JSONL
    when a human marks attestation (policy hook; ingestion still ignores the field
    until the store schema wires it through).
    """
    return bool(obj.get("effective_at_human_attested")) is True
