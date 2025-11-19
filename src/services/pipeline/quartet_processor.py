"""Quartet processor pipeline stage.

Orchestrates processing of individual file quartets: load files, validate sizes,
generate schema using AI vision, write schema file, track metrics.
"""

import time
from uuid import UUID

from src.lib.image_utils import resize_image_for_vision_api
from src.lib.logging import get_logger, log_error_with_context
from src.lib.validation import validate_file_size
from src.models.result import AIMetrics, ProcessingResult
from src.models.session import FileQuartet
from src.services.ai import get_schema_generator
from src.services.storage.session_storage import (
    load_quartet_files,
    write_schema_file,
)

logger = get_logger(__name__)


async def process_quartet(session_id: UUID, quartet: FileQuartet) -> ProcessingResult:
    """Process a single file quartet through the schema generation pipeline.

    Pipeline stages:
    1. Load quartet files (screenshot, HTML, metadata, scraped_facts)
    2. Validate file sizes
    3. Generate schema using AI vision (uses SchemaGenerator)
    4. Write schema file to storage
    5. Return processing result with metrics

    Args:
        session_id: Session UUID
        quartet: File quartet to process

    Returns:
        ProcessingResult: Result with success status, metrics, and output paths
    """
    start_time = time.time()

    logger.info(
        "quartet_processing_start",
        session_id=str(session_id),
        sequence_number=quartet.sequence_number,
        screenshot_path=quartet.screenshot_path,
    )

    try:
        # Stage 1: Load quartet files
        screenshot_bytes, html_content, metadata, scraped_facts = await load_quartet_files(
            quartet
        )

        # Stage 1.5: Resize screenshot for API compliance
        screenshot_bytes, resize_metadata = resize_image_for_vision_api(screenshot_bytes)

        logger.info(
            "screenshot_resized",
            session_id=str(session_id),
            sequence_number=quartet.sequence_number,
            original_size=(resize_metadata["original_width"], resize_metadata["original_height"]),
            new_size=(resize_metadata["new_width"], resize_metadata["new_height"]),
            resized=resize_metadata["resized"],
            file_size_bytes=resize_metadata["file_size_bytes"],
            within_api_limits=resize_metadata["within_api_limits"],
        )

        # Stage 2: Validate file sizes
        validate_file_size(len(screenshot_bytes), "screenshot")
        validate_file_size(len(html_content.encode("utf-8")), "html")

        logger.info(
            "files_validated",
            session_id=str(session_id),
            sequence_number=quartet.sequence_number,
            screenshot_size=len(screenshot_bytes),
            html_size=len(html_content),
            scraped_facts_size=len(scraped_facts),
        )

        # Stage 3: Generate schema using AI vision
        schema_generator = get_schema_generator()

        form_schema, ai_metrics = await schema_generator.generate_schema(
            screenshot_bytes, quartet.sequence_number, str(session_id), scraped_facts, metadata
        )

        # Stage 4: Write schema file
        schema_json = form_schema.model_dump_json(indent=2)
        schema_path = await write_schema_file(session_id, quartet, schema_json)

        # Update quartet with generated file path
        quartet.schema_file_path = schema_path

        logger.info(
            "schema_generation_complete",
            session_id=str(session_id),
            sequence_number=quartet.sequence_number,
            schema_file_path=schema_path,
        )

        # Stage 4.5: Transform schema to prompt format and write prompt file
        from src.services.transformers.schema_to_prompt import formschema_to_promptfile
        from src.services.storage.session_storage import write_prompt_file

        try:
            # Convert FormSchema to PromptFile
            prompt_file = formschema_to_promptfile(form_schema)
            prompt_json = prompt_file.model_dump_json(indent=2)
            prompt_path = await write_prompt_file(session_id, quartet, prompt_json)

            logger.info(
                "prompt_file_generated",
                session_id=str(session_id),
                sequence_number=quartet.sequence_number,
                prompt_file_path=prompt_path,
                sections_count=len(prompt_file.sections),
                required_fields_count=len(prompt_file.get_required_fields()),
            )
        except Exception as e:
            # Strict mode: fail entire quartet processing if prompt generation fails
            logger.error(
                "prompt_generation_failed",
                session_id=str(session_id),
                sequence_number=quartet.sequence_number,
                error=str(e),
                exc_info=True,
            )
            raise  # Re-raise to fail quartet processing

        # Stage 5: Calculate total duration and return result
        duration_ms = (time.time() - start_time) * 1000

        # Create success result
        result = ProcessingResult(
            session_id=session_id,
            sequence_number=quartet.sequence_number,
            operation="quartet_processing",
            success=True,
            duration_ms=duration_ms,
            schema_file_path=schema_path,
            ai_metrics=AIMetrics(**ai_metrics),
            metadata={
                "screenshot_size_bytes": len(screenshot_bytes),
                "screenshot_original_dimensions": f"{resize_metadata['original_width']}x{resize_metadata['original_height']}",
                "screenshot_resized_dimensions": f"{resize_metadata['new_width']}x{resize_metadata['new_height']}",
                "screenshot_was_resized": resize_metadata["resized"],
                "html_size_bytes": len(html_content),
                "scraped_facts_size_bytes": len(scraped_facts),
                "schema_sections_count": len(form_schema.sections),
                "ai_latency_ms": ai_metrics["latency_ms"],
                "ai_tokens": ai_metrics["total_tokens"],
            },
        )

        logger.info(
            "quartet_processing_complete",
            session_id=str(session_id),
            sequence_number=quartet.sequence_number,
            success=True,
            duration_ms=duration_ms,
            schema_file_path=schema_path,
        )

        return result

    except Exception as e:
        # Calculate duration even on failure
        duration_ms = (time.time() - start_time) * 1000

        # Log error with context
        log_error_with_context(
            logger,
            operation="quartet_processing",
            error=e,
            input_snapshot={
                "session_id": str(session_id),
                "sequence_number": quartet.sequence_number,
                "screenshot_path": quartet.screenshot_path,
                "html_path": quartet.html_path,
                "metadata_path": quartet.metadata_path,
                "page_id_path": quartet.page_id_path,
            },
            system_state={
                "duration_ms": duration_ms,
            },
        )

        # Create failure result
        result = ProcessingResult(
            session_id=session_id,
            sequence_number=quartet.sequence_number,
            operation="schema_generation",
            success=False,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
            error_message=str(e),
            error_context={
                "screenshot_path": quartet.screenshot_path,
                "html_path": quartet.html_path,
                "metadata_path": quartet.metadata_path,
                "page_id_path": quartet.page_id_path,
            },
        )

        logger.error(
            "quartet_processing_failed",
            session_id=str(session_id),
            sequence_number=quartet.sequence_number,
            success=False,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
            error_message=str(e),
        )

        return result
