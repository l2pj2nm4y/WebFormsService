"""Triplet processor pipeline stage.

Orchestrates processing of individual file triplets: load files, extract facts,
write fact files, track metrics.
"""

import time
from uuid import UUID

from src.lib.logging import get_logger, log_error_with_context
from src.lib.validation import validate_file_size
from src.models.result import AIMetrics, ProcessingResult
from src.models.session import FileTriplet
from src.services.ai import get_fact_extractor
from src.services.storage.session_storage import load_triplet_files, write_fact_file

logger = get_logger(__name__)


async def process_triplet(session_id: UUID, triplet: FileTriplet) -> ProcessingResult:
    """Process a single file triplet through the fact extraction pipeline.

    Pipeline stages:
    1. Load triplet files (screenshot, HTML, metadata)
    2. Validate file sizes
    3. Extract facts using AI vision
    4. Write fact file to storage
    5. Return processing result with metrics

    Args:
        session_id: Session UUID
        triplet: File triplet to process

    Returns:
        ProcessingResult: Result with success status, metrics, and output paths
    """
    start_time = time.time()

    logger.info(
        "triplet_processing_start",
        session_id=str(session_id),
        sequence_number=triplet.sequence_number,
        screenshot_path=triplet.screenshot_path,
    )

    try:
        # Stage 1: Load triplet files
        screenshot_bytes, html_content, metadata = await load_triplet_files(triplet)

        # Stage 2: Validate file sizes
        validate_file_size(len(screenshot_bytes), "screenshot")
        validate_file_size(len(html_content.encode("utf-8")), "html")

        logger.info(
            "files_validated",
            session_id=str(session_id),
            sequence_number=triplet.sequence_number,
            screenshot_size=len(screenshot_bytes),
            html_size=len(html_content),
        )

        # Stage 3: Extract facts using AI
        fact_extractor = get_fact_extractor()

        fact_file, ai_metrics = await fact_extractor.extract_facts(
            screenshot_bytes, triplet.sequence_number, str(session_id)
        )

        # Stage 4: Write fact file
        fact_json = fact_file.model_dump_json(indent=2)
        fact_path = await write_fact_file(session_id, triplet, fact_json)

        # Update triplet with generated file path
        triplet.fact_file_path = fact_path

        # Calculate total duration
        duration_ms = (time.time() - start_time) * 1000

        # Create success result
        result = ProcessingResult(
            session_id=session_id,
            sequence_number=triplet.sequence_number,
            operation="fact_extraction",
            success=True,
            duration_ms=duration_ms,
            fact_file_path=fact_path,
            ai_metrics=AIMetrics(**ai_metrics),
            metadata={
                "screenshot_size_bytes": len(screenshot_bytes),
                "html_size_bytes": len(html_content),
                "visual_headings_count": len(fact_file.visual_headings),
                "has_forms": fact_file.form_elements.has_forms,
                "form_fields_count": len(fact_file.form_elements.visible_fields),
            },
        )

        logger.info(
            "triplet_processing_complete",
            session_id=str(session_id),
            sequence_number=triplet.sequence_number,
            success=True,
            duration_ms=duration_ms,
            fact_file_path=fact_path,
        )

        return result

    except Exception as e:
        # Calculate duration even on failure
        duration_ms = (time.time() - start_time) * 1000

        # Log error with context
        log_error_with_context(
            logger,
            operation="triplet_processing",
            error=e,
            input_snapshot={
                "session_id": str(session_id),
                "sequence_number": triplet.sequence_number,
                "screenshot_path": triplet.screenshot_path,
                "html_path": triplet.html_path,
                "metadata_path": triplet.metadata_path,
            },
            system_state={
                "duration_ms": duration_ms,
            },
        )

        # Create failure result
        result = ProcessingResult(
            session_id=session_id,
            sequence_number=triplet.sequence_number,
            operation="fact_extraction",
            success=False,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
            error_message=str(e),
            error_context={
                "screenshot_path": triplet.screenshot_path,
                "html_path": triplet.html_path,
                "metadata_path": triplet.metadata_path,
            },
        )

        logger.error(
            "triplet_processing_failed",
            session_id=str(session_id),
            sequence_number=triplet.sequence_number,
            success=False,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
            error_message=str(e),
        )

        return result
