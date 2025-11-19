"""Pipeline stages for file processing.

Multi-stage pipeline:
1. Quartet processing - Generate schema from screenshots
2. Session merging - Merge prompts within session
3. Master merging - Merge session to master
4. Combined generation - Generate final combined prompt
"""

from src.services.pipeline.quartet_processor import process_quartet

__all__ = [
    "process_quartet",
]
