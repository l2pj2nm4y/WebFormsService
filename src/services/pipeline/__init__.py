"""Pipeline stages for file processing.

Multi-stage pipeline:
1. Triplet processing - Extract facts from screenshots
2. Session merging - Merge prompts within session
3. Master merging - Merge session to master
4. Combined generation - Generate final combined prompt
"""

from src.services.pipeline.triplet_processor import process_triplet

__all__ = [
    "process_triplet",
]
