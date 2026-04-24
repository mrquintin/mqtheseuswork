"""docgen — compile versioned, signed MethodDoc bundles."""

from noosphere.docgen.ast_diff import ASTChange, diff_sources, has_behavior_change, summarize_changes
from noosphere.docgen.changelog import (
    ChangelogEntry,
    ChangelogValidationError,
    format_changelog,
    generate_changelog,
)
from noosphere.docgen.compiler import TEMPLATE_VERSION, compile_method_doc
from noosphere.docgen.examples import ExamplesBuilder, narrate_example, narrate_invocations

__all__ = [
    "ASTChange",
    "ChangelogEntry",
    "ChangelogValidationError",
    "ExamplesBuilder",
    "TEMPLATE_VERSION",
    "compile_method_doc",
    "diff_sources",
    "format_changelog",
    "generate_changelog",
    "has_behavior_change",
    "narrate_example",
    "narrate_invocations",
    "summarize_changes",
]
