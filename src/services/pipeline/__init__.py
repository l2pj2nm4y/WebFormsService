"""Pipeline stages for file processing.

Multi-stage pipeline:
1. Triplet processing - Extract facts from screenshots (legacy)
2. Quartet processing - Generate schema from screenshots (current)
3. Session merging - Merge prompts within session
4. Master merging - Merge session to master
5. Combined generation - Generate final combined prompt
"""

from src.services.pipeline.quartet_processor import process_quartet
from src.services.pipeline.triplet_processor import process_triplet

__all__ = [
    "process_triplet",
    "process_quartet",
]
