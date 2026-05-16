"""Cross-source knowledge graph (Round 19 prompt 13).

A *projection* over the firm's principle / algorithm / memo / source /
contradiction tables: the authoritative rows live elsewhere; this
package builds a typed graph view of how those rows relate.

Public surface:

* :func:`build_for_org` — full graph for one org.
* :func:`incremental_update` — compute deltas for one domain event.
* :class:`KnowledgeGraphBuilder` — class form of the same.
* :func:`reason_about_edge` — agent reasoning over an edge.
"""

from noosphere.knowledge_graph.builder import (  # noqa: F401
    KnowledgeGraphBuilder,
    build_for_org,
    incremental_update,
)
from noosphere.knowledge_graph.agent_reasoner import reason_about_edge  # noqa: F401
