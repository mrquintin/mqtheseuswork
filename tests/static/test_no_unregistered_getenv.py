"""Drift gate: every new ``os.getenv`` / ``os.environ.get`` call names
a variable that is either in ``noosphere.core.env_validation.REGISTRY``
or in the legacy allowlist below.

Adding a new env var in a future round must add a row to the
registry, not extend the legacy allowlist (the allowlist is frozen
for vars that pre-date the registry).
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    REPO_ROOT / "noosphere" / "noosphere",
    REPO_ROOT / "current_events_api" / "current_events_api",
)


def _load_registry_names() -> set[str]:
    noosphere_src = REPO_ROOT / "noosphere"
    if str(noosphere_src) not in sys.path:
        sys.path.insert(0, str(noosphere_src))
    from noosphere.core.env_validation import REGISTRY
    return {r.var_name for r in REGISTRY}


# Legacy env vars that pre-date the validation registry. New additions
# MUST go in the registry, not here — CI fails on any new env var that
# is in neither set. Keeping this list explicit makes the drift gate
# meaningful while avoiding a 300-row registry migration in one shot.
LEGACY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "ALGORITHMS_BUDGET_PATH",
        "ALGORITHMS_IDEMPOTENCY_WINDOW_S",
        "ALGORITHMS_MAX_DRAFTS_PER_RUN",
        "ALGORITHMS_ORGANIZATION_ID",
        "ALGORITHMS_ORG_ID",
        "ALPACA_API_BASE",
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
        "ALPACA_DATA_BASE",
        "ALPACA_IS_PAPER",
        "ALPACA_KEY_ID",
        "ALPACA_REQUEST_TIMEOUT_S",
        "APPDATA",
        "ARTICLES_DISPATCH_MARKER_PATH",
        "ARTICLES_POSTMORTEM_MIN_STAKE_USD",
        "CODEX_DATABASE_URL",
        "CURRENTS_BUDGET_PATH",
        "CURRENTS_CORS_ORIGINS",
        "CURRENTS_HAIKU_MODEL",
        "CURRENTS_INGEST_ORG_ID",
        "CURRENTS_LOG_LEVEL",
        "CURRENTS_MARKET_CONTRADICTION_CEILING",
        "CURRENTS_MARKET_LIQUIDITY_FLOOR_USD",
        "CURRENTS_MARKET_NLI_THRESHOLD",
        "CURRENTS_MAX_EVENTS_PER_CYCLE",
        "CURRENTS_METRICS_TOKEN",
        "CURRENTS_MIN_SIGNIFICANCE_SCORE",
        "CURRENTS_ORG_ID",
        "CURRENTS_STATUS_MAX_AGE_SECONDS",
        "CURRENTS_STATUS_PATH",
        "CURRENTS_X_BASE_URL",
        "CURRENTS_X_CURATED_ACCOUNTS",
        "CURRENTS_X_DISCOVERY_ENABLED",
        "CURRENTS_X_DISCOVERY_LOCALE",
        "CURRENTS_X_DISCOVERY_MAX_CANDIDATES",
        "CURRENTS_X_DISCOVERY_QUERY",
        "CURRENTS_X_INGESTION_DISABLED",
        "CURRENTS_X_MIN_IMPRESSIONS",
        "CURRENTS_X_MIN_LIKES",
        "CURRENTS_X_MIN_RETWEETS",
        "CURRENTS_X_REQUEST_TIMEOUT_S",
        "CURRENTS_X_SEARCH_QUERIES",
        "DIALECTIC_ORG_ID",
        "DIRECT_URL",
        "EMBED_BACKFILL_MARKER_PATH",
        "EMPTY",
        "EQUITIES_ACCEPTED_SYMBOLS",
        "EQUITIES_BUDGET_HOURLY_COMPLETION_TOKENS",
        "EQUITIES_BUDGET_HOURLY_PROMPT_TOKENS",
        "EQUITIES_BUDGET_PATH",
        "EQUITIES_LIVE_TRADING_ENABLED",
        "EQUITIES_MAX_DAILY_LOSS_USD",
        "EQUITIES_MAX_STAKE_USD",
        "FORECASTS_BUDGET_HOURLY_COMPLETION_TOKENS",
        "FORECASTS_BUDGET_HOURLY_PROMPT_TOKENS",
        "FORECASTS_BUDGET_PATH",
        "FORECASTS_INGEST_INTERVAL_S",
        "FORECASTS_KALSHI_CATEGORIES",
        "FORECASTS_KALSHI_MAX_PER_CYCLE",
        "FORECASTS_LIVE_ORDER_POLL_TIMEOUT_S",
        "FORECASTS_LIVE_ORDER_TYPE",
        "FORECASTS_LOG_LEVEL",
        "FORECASTS_OPERATOR_CSRF_TOKEN",
        "FORECASTS_ORG_ID",
        "FORECASTS_POLYMARKET_CATEGORIES",
        "FORECASTS_POLYMARKET_MAX_PER_CYCLE",
        "FORECASTS_RECENT_PREDICTION_WINDOW_S",
        "FORECASTS_RESOLUTION_STATUS_MAX_AGE_SECONDS",
        "FORECASTS_RESOLUTION_STATUS_PATH",
        "FORECASTS_STATUS_MAX_AGE_SECONDS",
        "FORECASTS_STATUS_PATH",
        "GTC",
        "INFO",
        "KALSHI_API_BASE",
        "KALSHI_PRIVATE_KEY_PEM",
        "KNOWLEDGE_GRAPH_ORG_ID",
        "LOGNAME",
        "LOG_LEVEL",
        "NOOSPHERE_DATA_DIR",
        "NOOSPHERE_DB_SPANS",
        "NOOSPHERE_ENABLE_OCR",
        "NOOSPHERE_ORGANIZATION_SLUG",
        "NOOSPHERE_FORCE_OPENAI_WHISPER",
        "NOOSPHERE_MAX_UPLOAD_BYTES",
        "NOOSPHERE_SKIP_AUTH",
        "NOOSPHERE_VERIFY_TLS",
        "NOOSPHERE_WHISPER_COMPUTE_TYPE",
        "NOOSPHERE_WHISPER_MODEL",
        "OPENAI_API_KEY",
        "POLYMARKET_CHAIN_ID",
        "POLYMARKET_CLOB_BASE",
        "POLYMARKET_DEFAULT_NEG_RISK",
        "POLYMARKET_DEFAULT_TICK_SIZE",
        "POLYMARKET_FUNDER_ADDRESS",
        "POLYMARKET_GAMMA_BASE",
        "POLYMARKET_SIGNATURE_TYPE",
        "ROBINHOOD_DEVICE_TOKEN",
        "ROBINHOOD_ENABLED",
        "ROBINHOOD_MFA_SEED",
        "ROBINHOOD_PASSWORD",
        "ROBINHOOD_PIP_CHOICE",
        "ROBINHOOD_REQUEST_TIMEOUT_S",
        "ROBINHOOD_USERNAME",
        "S3_BUCKET",
        "S3_ENDPOINT_URL",
        "S3_REGION",
        "STORAGE_BACKEND",
        "STORAGE_LOCAL_ROOT",
        "SUBSTACK_FROM_EMAIL",
        "SUBSTACK_PUBLISH_EMAIL",
        "SUBSTACK_SMTP_HOST",
        "SUBSTACK_SMTP_PASS",
        "SUBSTACK_SMTP_STARTTLS",
        "SUBSTACK_SMTP_USER",
        "SUPABASE_AUDIO_BUCKET",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_URL",
        "SYNTHESIZER_BUDGET_PATH",
        "THESEUS_AUTO_COHERENCE_IN_TESTS",
        "THESEUS_AUTO_EMBED_IN_TESTS",
        "THESEUS_CODEX_DATABASE_URL",
        "THESEUS_CROSS_MODEL_BUDGET",
        "THESEUS_CROSS_MODEL_ROOT",
        "THESEUS_DATABASE_URL",
        "THESEUS_DATA_DIR",
        "THESEUS_ENV",
        "THESEUS_GIT_SHA",
        "THESEUS_LEDGER_MIRROR_DIR",
        "THESEUS_LEDGER_SIGNING_KEY_PATH",
        "THESEUS_LEDGER_VERIFICATION_KEYS_DIR",
        "THESEUS_LOG_BACKUP_COUNT",
        "THESEUS_LOG_DIR",
        "THESEUS_LOG_FILE",
        "THESEUS_LOG_LEVEL",
        "THESEUS_LOG_MAX_BYTES",
        "THESEUS_MODE",
        "THESEUS_PUBLICATION_KEY_DIR",
        "THESEUS_PUBLIC_CALIBRATION_PATH",
        "THESEUS_REVALIDATE_BASE_URL",
        "THESEUS_REVALIDATE_SECRET",
        "THESEUS_REVIEW_WEEK_KEY_DIR",
        "THESEUS_SCALED_COHERENCE_AUTO",
        "THESEUS_SKIP_BOOT_CHECK",
        "THESEUS_SPANS_FILE",
        "THESEUS_SUBSTACK_CLIENT_MOCK",
        "THESEUS_SUBSTACK_FORMATTER_MOCK",
        "THESEUS_SUBSTACK_POSTING_ENABLED",
        "THESEUS_SYNTHESIS_MAX_WORKERS",
        "THESEUS_X_CLIENT_MOCK",
        "THESEUS_X_POSTING_ENABLED",
        "USER",
        "X_API_OAUTH_TOKEN_URL",
        "X_API_TWEET_URL",
        "X_BEARER_TOKEN",
        "X_BOT_OAUTH_ACCESS_TOKEN",
        "X_BOT_OAUTH_CLIENT_ID",
        "X_BOT_OAUTH_CLIENT_SECRET",
        "X_BOT_OAUTH_REFRESH_TOKEN",
    }
)


_ENV_CALL_RE = re.compile(
    r"""(?:os\.getenv|os\.environ\.get|os\.environ)\s*[\(\[]\s*["']([A-Z_][A-Z0-9_]*)["']"""
)


def _scan_env_vars() -> set[str]:
    found: set[str] = set()
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in _ENV_CALL_RE.finditer(text):
                found.add(match.group(1))
    return found


def test_no_unregistered_getenv() -> None:
    used = _scan_env_vars()
    registry = _load_registry_names()
    allowed = registry | LEGACY_ALLOWLIST
    unregistered = sorted(used - allowed)
    assert not unregistered, (
        "These env vars are used in the codebase but appear in neither "
        "noosphere.core.env_validation.REGISTRY nor the LEGACY_ALLOWLIST: "
        f"{unregistered}\n\n"
        "Fix: add a row to noosphere/noosphere/core/env_validation.py REGISTRY."
    )


def test_registry_vars_consumed_somewhere_or_documented() -> None:
    """A registry row that is *never* read anywhere is dead config —
    flag it so we don't accumulate phantom requirements.

    Soft assertion: we allow some new rows to land before code that
    reads them does — the gate is that every row is mentioned either
    in a Python file or in the operator doc, not strictly in os.getenv.
    """
    registry = _load_registry_names()
    found = _scan_env_vars()
    doc_text = (
        REPO_ROOT / "docs" / "operator" / "ENV_VARIABLES.md"
    ).read_text(encoding="utf-8")
    orphans = [
        name
        for name in registry
        if name not in found and name not in doc_text
    ]
    assert not orphans, f"Registry rows neither consumed nor documented: {orphans}"
