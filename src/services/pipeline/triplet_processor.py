"""Triplet processor pipeline stage.

Orchestrates processing of individual file triplets: load files, extract facts,
write fact files, track metrics.
"""

import json
import time
from uuid import UUID

from src.lib.logging import get_logger, log_error_with_context
from src.lib.validation import validate_file_size
from src.models.result import AIMetrics, ProcessingResult
from src.models.session import FileTriplet
from src.services.ai import get_fact_extractor, get_prompt_generator
from src.services.html import get_form_parser
from src.services.storage.session_storage import (
    load_triplet_files,
    write_fact_file,
    write_prompt_file,
)

logger = get_logger(__name__)


async def process_triplet(session_id: UUID, triplet: FileTriplet) -> ProcessingResult:
    """Process a single file triplet through the fact extraction and prompt generation pipeline.

    Pipeline stages:
    1. Load triplet files (screenshot, HTML, metadata)
    2. Validate file sizes
    3. Extract facts using AI vision
    4. Write fact file to storage
    5. Parse HTML to extract form fields
    6. Generate prompt file using AI
    7. Write prompt file to storage
    8. Return processing result with metrics

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

        logger.info(
            "fact_extraction_complete",
            session_id=str(session_id),
            sequence_number=triplet.sequence_number,
            fact_file_path=fact_path,
        )

        # Stage 5: Parse HTML to extract form fields
        form_parser = get_form_parser()
        form_fields = form_parser.parse_html(html_content)

        logger.info(
            "html_parsing_complete",
            session_id=str(session_id),
            sequence_number=triplet.sequence_number,
            form_field_count=len(form_fields),
        )

        # Stage 6: Generate prompt file using AI
        prompt_generator = get_prompt_generator()

        prompt_data, prompt_ai_metrics = await prompt_generator.generate_prompt(
            screenshot_bytes, form_fields, triplet.sequence_number, str(session_id)
        )

        # Stage 7: Write prompt file
        prompt_json = json.dumps(prompt_data, indent=2)
        prompt_path = await write_prompt_file(session_id, triplet, prompt_json)

        # Update triplet with prompt file path
        triplet.prompt_file_path = prompt_path

        logger.info(
            "prompt_generation_complete",
            session_id=str(session_id),
            sequence_number=triplet.sequence_number,
            prompt_file_path=prompt_path,
        )

        # Calculate total duration
        duration_ms = (time.time() - start_time) * 1000

        # Create success result
        result = ProcessingResult(
            session_id=session_id,
            sequence_number=triplet.sequence_number,
            operation="triplet_processing",
            success=True,
            duration_ms=duration_ms,
            fact_file_path=fact_path,
            prompt_file_path=prompt_path,
            ai_metrics=AIMetrics(**ai_metrics),
            metadata={
                "screenshot_size_bytes": len(screenshot_bytes),
                "html_size_bytes": len(html_content),
                "page_headings_count": len(fact_file.page_headings),
                "form_headings_count": len(fact_file.form_headings),
                "navigation_buttons_count": len(fact_file.navigation_buttons),
                "form_field_count": len(form_fields),
                "fact_ai_latency_ms": ai_metrics["latency_ms"],
                "prompt_ai_latency_ms": prompt_ai_metrics["latency_ms"],
                "fact_ai_tokens": ai_metrics["total_tokens"],
                "prompt_ai_tokens": prompt_ai_metrics["total_tokens"],
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
