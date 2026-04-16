"""Deliberate registry bypass — used as a lint-test fixture."""
from noosphere.methods._legacy.nli_scorer import NLIScorer


def bypass_call():
    scorer = NLIScorer()
    return scorer
