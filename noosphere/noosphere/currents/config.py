from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CURATED_PATH = Path(__file__).parent / "config_defaults" / "curated_accounts.json"
DEFAULT_KEYWORDS_PATH = Path(__file__).parent / "config_defaults" / "topic_keywords.json"


@dataclass
class IngestorConfig:
    bearer_token: str
    curated_accounts: list[str]
    topic_keywords: list[str]
    lookback_minutes: int = 15
    max_posts_per_account: int = 20
    max_posts_per_keyword_query: int = 50
    request_timeout_s: float = 15.0
    base_url: str = "https://api.twitter.com"

    @classmethod
    def from_env(cls) -> "IngestorConfig":
        bearer = os.environ.get("X_BEARER_TOKEN", "")
        curated_path = Path(os.environ.get("CURRENTS_CURATED_ACCOUNTS", str(DEFAULT_CURATED_PATH)))
        keywords_path = Path(os.environ.get("CURRENTS_TOPIC_KEYWORDS", str(DEFAULT_KEYWORDS_PATH)))
        return cls(
            bearer_token=bearer,
            curated_accounts=json.loads(curated_path.read_text()),
            topic_keywords=json.loads(keywords_path.read_text()),
            lookback_minutes=int(os.environ.get("CURRENTS_LOOKBACK_MINUTES", "15")),
        )
