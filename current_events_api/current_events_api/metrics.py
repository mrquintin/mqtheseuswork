"""Prometheus-compatible metrics view for the current-events API."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CurrentsMetrics:
    opinions_published_total: int = 0
    opinions_abstained_budget_total: int = 0
    opinions_abstained_insufficient_sources_total: int = 0
    followup_sessions_active: int = 0
    sse_feed_clients: int = 0
    sse_followup_clients: int = 0

    def render(self) -> str:
        lines = [
            "# HELP currents_opinions_published_total Total event opinions published",
            "# TYPE currents_opinions_published_total counter",
            f"currents_opinions_published_total {self.opinions_published_total}",
            "# HELP currents_opinions_abstained_budget_total Abstained due to budget exhaustion",
            "# TYPE currents_opinions_abstained_budget_total counter",
            f"currents_opinions_abstained_budget_total {self.opinions_abstained_budget_total}",
            "# HELP currents_opinions_abstained_insufficient_sources_total Abstained due to insufficient sources",
            "# TYPE currents_opinions_abstained_insufficient_sources_total counter",
            f"currents_opinions_abstained_insufficient_sources_total {self.opinions_abstained_insufficient_sources_total}",
            "# HELP currents_followup_sessions_active Active follow-up sessions (last 30m)",
            "# TYPE currents_followup_sessions_active gauge",
            f"currents_followup_sessions_active {self.followup_sessions_active}",
            "# HELP currents_sse_feed_clients Live feed SSE clients",
            "# TYPE currents_sse_feed_clients gauge",
            f"currents_sse_feed_clients {self.sse_feed_clients}",
            "# HELP currents_sse_followup_clients Follow-up SSE clients",
            "# TYPE currents_sse_followup_clients gauge",
            f"currents_sse_followup_clients {self.sse_followup_clients}",
        ]
        return "\n".join(lines) + "\n"
