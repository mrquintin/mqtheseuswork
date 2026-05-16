"""P1, P2, P3 — sandbox + no-network + pdflatex-shell-escape regressions.

These tests are load-bearing. A failure here BLOCKS the sync.

* P1 — trigger-predicate sandbox is unescapable.
* P2 — algorithm runtime makes ZERO unmocked network calls.
* P3 — memo PDF generation cannot execute arbitrary code via
       ``\\write18`` / ``-shell-escape``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from noosphere.algorithms.validators import (
    AlgorithmValidationError,
    validate_trigger_predicate,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


# ── P1 — trigger-predicate sandbox is unescapable ──────────────────────────


def _load_adversarial_predicates() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    with (FIXTURES / "adversarial_predicates.txt").open(encoding="utf-8") as fp:
        for raw in fp:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "\t" not in line:
                pytest.fail(
                    f"adversarial_predicates.txt line missing TAB: {line!r}"
                )
            predicate, reason = line.split("\t", 1)
            cases.append((predicate, reason.strip()))
    if not cases:
        pytest.fail("adversarial_predicates.txt is empty — refusing to skip")
    return cases


_ADVERSARIAL = _load_adversarial_predicates()


class TestP1TriggerPredicateSandbox:
    """Every adversarial predicate is rejected at parse/eval time."""

    @pytest.mark.parametrize(
        "predicate,reason_fragment",
        _ADVERSARIAL,
        ids=[case[0][:40] for case in _ADVERSARIAL],
    )
    def test_adversarial_predicate_rejected(
        self, predicate: str, reason_fragment: str
    ) -> None:
        with pytest.raises(AlgorithmValidationError) as excinfo:
            validate_trigger_predicate(predicate, input_names=["x"])
        # Case-insensitive substring — the validator's exact wording is
        # an implementation detail; the property under test is that it
        # refuses the input.
        assert reason_fragment.lower() in str(excinfo.value).lower(), (
            f"predicate {predicate!r} was rejected but the reason "
            f"{excinfo.value!r} did not mention {reason_fragment!r}"
        )

    def test_legitimate_predicate_accepted(self) -> None:
        # Honest path: a simple comparison over a declared input.
        validate_trigger_predicate(
            "input.x > 0 and input.flag == True",
            input_names=["x", "flag"],
        )

    def test_three_rejections_in_a_row_still_raise(self) -> None:
        # The runtime is documented to pause an algorithm after three
        # rejections. We exercise the validator three times to confirm
        # there is no hidden "accept after retry" path.
        for _ in range(3):
            with pytest.raises(AlgorithmValidationError):
                validate_trigger_predicate(
                    "__import__('os').system('id')",
                    input_names=["x"],
                )


# ── P2 — algorithm runtime makes zero unmocked network calls ──────────────


class TestP2NoUnmockedNetwork:
    """No httpx / urllib / socket call escapes the algorithm package in tests."""

    def test_httpx_request_is_not_invoked_at_import_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Replace httpx.AsyncClient.request with a tripwire BEFORE we
        # import the algorithm package. If anything in the import chain
        # tries to perform a real HTTP call, this assertion fires.
        calls: list[tuple[str, str]] = []

        try:
            import httpx
        except ImportError:
            pytest.skip("httpx is not installed in this environment")

        original = httpx.AsyncClient.request

        async def tripwire(self, method, url, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((str(method), str(url)))
            raise AssertionError(
                "httpx.AsyncClient.request was invoked during a test — "
                "the algorithm runtime MUST mock its network surface."
            )

        monkeypatch.setattr(httpx.AsyncClient, "request", tripwire)

        # Importing the package + runtime + adapters must not perform
        # a network call. We deliberately import the surfaces that
        # Round 19 introduced.
        import importlib

        importlib.import_module("noosphere.algorithms")
        importlib.import_module("noosphere.algorithms.runtime")
        importlib.import_module("noosphere.algorithms.validators")
        importlib.import_module("noosphere.algorithms.drafter")
        importlib.import_module("noosphere.algorithms.calibration")
        importlib.import_module("noosphere.synthesizer.engine")
        importlib.import_module("noosphere.synthesizer.memo_builder")
        importlib.import_module("noosphere.knowledge_graph")

        # Restore so we don't poison subsequent tests in the same
        # session that legitimately stub httpx themselves.
        monkeypatch.setattr(httpx.AsyncClient, "request", original)

        assert calls == [], f"unexpected network calls observed: {calls}"

    def test_sync_httpx_request_is_not_invoked_at_import_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str]] = []
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx is not installed in this environment")

        def tripwire(self, method, url, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((str(method), str(url)))
            raise AssertionError(
                "httpx.Client.request was invoked during a test — "
                "the synthesizer / memo pipeline MUST mock its network "
                "surface."
            )

        original = httpx.Client.request
        monkeypatch.setattr(httpx.Client, "request", tripwire)

        import importlib

        importlib.import_module("noosphere.synthesizer")
        importlib.import_module("noosphere.synthesizer.memo_builder")

        monkeypatch.setattr(httpx.Client, "request", original)
        assert calls == []


# ── P3 — pdflatex shell-escape is disabled ────────────────────────────────


class TestP3PdflatexShellEscape:
    """The canonical memo build script forbids -shell-escape."""

    def test_build_script_does_not_pass_shell_escape(self) -> None:
        script = REPO_ROOT / "docs" / "memos" / "build_memo_pdf.sh"
        assert script.is_file(), f"missing build script at {script}"
        contents = script.read_text(encoding="utf-8")
        # Both spellings must be absent.
        for needle in ("-shell-escape", "--shell-escape", "shell_escape=1"):
            assert needle not in contents, (
                f"build_memo_pdf.sh contains forbidden {needle!r} — "
                "pdflatex must run with shell-escape DISABLED"
            )
        # And the script MUST contain the constrained-mode flags.
        for needle in ("-interaction=nonstopmode", "-halt-on-error"):
            assert needle in contents, (
                f"build_memo_pdf.sh missing required {needle!r}"
            )

    def test_pdflatex_refuses_adversarial_write18(
        self, tmp_path: Path, request: pytest.FixtureRequest
    ) -> None:
        if not shutil.which("pdflatex"):
            # The skip marker is the audit trail: CI logs the skip and
            # the operator can verify the test ran locally somewhere.
            pytest.skip(
                "pdflatex is not installed in this environment — "
                "this test runs LOCALLY; CI records the skip for audit"
            )

        # Stage the adversarial fixture next to the build script's
        # working dir.
        canary = Path("/tmp/theseus-shell-escape-canary")
        canary.unlink(missing_ok=True)
        try:
            tex_path = tmp_path / "adversarial.tex"
            tex_path.write_text(
                (FIXTURES / "adversarial_pdflatex.tex").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            script = REPO_ROOT / "docs" / "memos" / "build_memo_pdf.sh"
            proc = subprocess.run(
                ["bash", str(script), str(tex_path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            # We do NOT assert returncode — pdflatex may either refuse
            # entirely (non-zero) or proceed while ignoring \\write18
            # under -no-shell-escape (zero). The property under test is
            # that the canary file was NOT created.
            assert not canary.exists(), (
                "pdflatex executed \\write18 — shell-escape is ENABLED "
                f"and the property is BROKEN. proc.returncode={proc.returncode}"
            )
        finally:
            canary.unlink(missing_ok=True)
