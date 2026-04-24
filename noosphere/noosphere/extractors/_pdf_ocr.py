"""OCR fallback for scanned PDFs via ``ocrmypdf``.

ocrmypdf wraps tesseract and ghostscript into a single CLI that takes
a PDF in, produces a re-OCRed PDF out, and (with ``--sidecar``) writes
the recognized text to a plain .txt. We only need the sidecar.

No timeout is enforced here — a 400-page scan legitimately takes
minutes. The CLI layer that drives ingest is responsible for surfacing
an in-progress state to the user; this module just runs the job to
completion or raises.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class OcrUnavailable(RuntimeError):
    """Raised when ``ocrmypdf`` is not installed / not on PATH."""


def ocr_to_text(data: bytes, *, language: str = "eng") -> str:
    if not shutil.which("ocrmypdf"):
        raise OcrUnavailable(
            "ocrmypdf is not in PATH; install ocrmypdf to enable OCR "
            "(macOS: `brew install ocrmypdf`, Debian: `apt install ocrmypdf`)."
        )
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.pdf"
        dst = Path(d) / "out.pdf"
        sidecar = Path(d) / "out.txt"
        src.write_bytes(data)
        # --force-ocr: re-OCR even when pypdf thought it found text,
        #   which is safer on mixed PDFs (half-digital, half-scanned).
        # --sidecar: emit the recognized text as plain UTF-8 next to
        #   the re-OCRed PDF. We discard the PDF and keep only the text.
        subprocess.run(
            [
                "ocrmypdf",
                "--force-ocr",
                "--sidecar", str(sidecar),
                "--language", language,
                "--quiet",
                str(src),
                str(dst),
            ],
            check=True,
        )
        return sidecar.read_text(encoding="utf-8")
