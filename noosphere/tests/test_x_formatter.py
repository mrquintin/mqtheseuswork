from __future__ import annotations

from noosphere.social.x_formatter import format_for_x, weighted_x_length


SOURCE_URL = "https://x.com/source/status/1234567890"


def test_formatter_accepts_exact_280_weighted_boundary() -> None:
    text = "a" * 256
    payload = format_for_x({"body_markdown": text}, SOURCE_URL)

    assert payload is not None
    assert payload["body"].endswith(SOURCE_URL)
    assert weighted_x_length(payload["body"]) == 280


def test_formatter_counts_urls_by_tco_budget_not_raw_url_length() -> None:
    long_url = "https://x.com/source/status/" + "9" * 80
    assert weighted_x_length(f"ok {long_url}") == 2 + 1 + 23


def test_formatter_counts_multibyte_characters_as_characters() -> None:
    text = "Revision is the point 🚀"
    payload = format_for_x({"body_markdown": text}, SOURCE_URL)

    assert payload is not None
    assert weighted_x_length(payload["body"]) == len(text) + 1 + 23


def test_formatter_uses_rewrite_pass_when_initial_body_is_too_long() -> None:
    payload = format_for_x(
        {"body_markdown": "This argument is too diffuse. " * 20},
        SOURCE_URL,
        rewrite_fn=lambda _text, _budget: "The load-bearing claim survives compression.",
    )

    assert payload is not None
    assert payload["body"] == (
        "The load-bearing claim survives compression. "
        "https://x.com/source/status/1234567890"
    )
    assert weighted_x_length(payload["body"]) <= 280


def test_formatter_returns_none_when_rewrite_still_does_not_fit() -> None:
    payload = format_for_x(
        {"body_markdown": "This argument is too diffuse. " * 20},
        SOURCE_URL,
        rewrite_fn=lambda _text, _budget: "x" * 400,
    )

    assert payload is None


def test_formatter_rejects_non_https_source_url() -> None:
    assert format_for_x({"body_markdown": "A claim."}, "http://x.com/a/status/1") is None
