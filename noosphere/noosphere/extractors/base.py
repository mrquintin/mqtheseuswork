"""Extractor contract: typed content wrappers, the Extractor protocol,
and the small exception hierarchy every extractor speaks.

Handlers receive ``BinaryContent`` (raw bytes already fetched) and return
``ExtractedText`` (plain text + provenance). Failures are typed so the
Codex bridge can write a structured reason onto ``Upload.errorMessage``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, Union, runtime_checkable


BinarySource = Literal["db", "supabase", "local"]


@dataclass(frozen=True)
class TextContent:
    """An Upload whose text is already materialized in the DB column."""

    text: str


@dataclass(frozen=True)
class BinaryContent:
    """Bytes fetched from storage, along with the MIME + filename needed
    to pick an extractor and label the result."""

    data: bytes
    mime: str
    filename: str
    source: BinarySource


UploadContent = Union[TextContent, BinaryContent]


@dataclass(frozen=True)
class ExtractedText:
    text: str
    source_format: str
    extraction_method: str
    warnings: list[str] = field(default_factory=list)


class ExtractionFailed(Exception):
    """Extractor ran but could not produce text (corrupt file, empty
    audio, unreadable PDF, etc.)."""


class UnsupportedMimeType(Exception):
    """No extractor is registered for this MIME family."""


@runtime_checkable
class Extractor(Protocol):
    name: str
    mime_prefixes: tuple[str, ...]

    def extract(self, content: BinaryContent) -> ExtractedText: ...
