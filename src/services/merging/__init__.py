"""Schema merging services for combining FormSchemas across sessions.

This package provides intelligent schema merging with:
- Hierarchical field identity (section path + field name + type)
- Temporal management (retention policies, version tracking)
- Page matching (identify duplicate pages for merging)
- Orchestration (end-to-end merge workflows)
"""

from src.services.merging.merge_orchestrator import MergeOrchestrator
from src.services.merging.page_matcher import PageMatch, PageMatcher
from src.services.merging.schema_merger import (
    HierarchicalIdentityComputer,
    SchemaMerger,
    SchemaVersion,
)

__all__ = [
    "HierarchicalIdentityComputer",
    "MergeOrchestrator",
    "PageMatch",
    "PageMatcher",
    "SchemaMerger",
    "SchemaVersion",
]
