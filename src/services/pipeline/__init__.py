"""Pipeline stages for file processing.

Multi-stage pipeline:
1. Quartet processing - Generate schema from screenshots
2. Session merging - Merge schemas within session by page similarity
3. Master merging - Merge session to master
4. Combined generation - Generate final combined prompt
"""

from src.services.pipeline.quartet_processor import process_quartet
from src.services.pipeline.session_merger import merge_session_schemas

__all__ = [
    "process_quartet",
    "merge_session_schemas",
]
