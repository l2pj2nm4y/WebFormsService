"""Session orchestration for end-to-end processing.

Orchestrates complete session processing workflow:
1. Claim session from Redis queue
2. Load session and discover quartets
3. Process each quartet (schema generation)
4. Merge schemas by page similarity
5. Track aggregate metrics and results
6. Return session processing result
"""

import asyncio
import time
from pathlib import Path
from uuid import UUID

from src.lib.config import get_config
from src.lib.logging import get_logger, log_processing_result
from src.models.result import ProcessingResult, SessionProcessingResult
from src.models.session import FileQuartet
from src.services.coordination import claim_next_session
from src.services.pipeline import merge_session_schemas, process_quartet
from src.services.storage.session_storage import discover_quartets

logger = get_logger(__name__)


async def _process_quartets_parallel(
    session_id: UUID, quartets: list[FileQuartet]
) -> list[ProcessingResult]:
    """Process quartets in parallel with controlled concurrency.

    Args:
        session_id: Session UUID
        quartets: List of quartets to process

    Returns:
        list[ProcessingResult]: Results for all quartets (in same order as input)
    """
    config = get_config()
    concurrency = config.processing.quartet_concurrency

    logger.info(
        "parallel_processing_start",
        session_id=str(session_id),
        quartet_count=len(quartets),
        max_concurrency=concurrency,
    )

    # Create semaphore to limit concurrent operations
    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_semaphore(quartet: FileQuartet) -> ProcessingResult:
        """Process a single quartet with semaphore-controlled concurrency."""
        async with semaphore:
            logger.debug(
                "quartet_processing_acquired_slot",
                session_id=str(session_id),
                sequence_number=quartet.sequence_number,
            )
            result = await process_quartet(session_id, quartet)
            logger.debug(
                "quartet_processing_released_slot",
                session_id=str(session_id),
                sequence_number=quartet.sequence_number,
                success=result.success,
            )
            return result

    # Process all quartets in parallel with semaphore limiting concurrency
    results = await asyncio.gather(
        *[process_with_semaphore(quartet) for quartet in quartets],
        return_exceptions=False,  # Let exceptions propagate
    )

    logger.info(
        "parallel_processing_complete",
        session_id=str(session_id),
        quartet_count=len(quartets),
        max_concurrency=concurrency,
    )

    return results


async def _process_quartets_sequential(
    session_id: UUID, quartets: list[FileQuartet]
) -> list[ProcessingResult]:
    """Process quartets sequentially (original behavior).

    Args:
        session_id: Session UUID
        quartets: List of quartets to process

    Returns:
        list[ProcessingResult]: Results for all quartets (in same order as input)
    """
    logger.info(
        "sequential_processing_start",
        session_id=str(session_id),
        quartet_count=len(quartets),
    )

    results = []
    for quartet in quartets:
        result = await process_quartet(session_id, quartet)
        results.append(result)

    logger.info(
        "sequential_processing_complete",
        session_id=str(session_id),
        quartet_count=len(quartets),
    )

    return results


async def process_session(
    session_id: UUID,
    quartet_limit: int | None = None,
    debug_dir: Path | str | None = None,
) -> SessionProcessingResult:
    """Process a complete session: discover quartets, generate schemas, aggregate results.

    Args:
        session_id: Session UUID to process
        quartet_limit: Optional limit on number of quartets to process (for debugging)
        debug_dir: Directory to write page matching debug files. If None, no debug output.

    Returns:
        SessionProcessingResult: Aggregate results with metrics

    Raises:
        FileNotFoundError: If session doesn't exist
    """
    start_time = time.time()

    logger.info("session_processing_start", session_id=str(session_id))

    try:
        # Get configuration
        config = get_config()

        # Discover quartets in session
        quartets = await discover_quartets(session_id)
        total_discovered = len(quartets)

        # Apply quartet limit if specified (for debugging)
        if quartet_limit is not None and quartet_limit > 0:
            quartets = quartets[:quartet_limit]
            logger.info(
                "quartet_limit_applied",
                session_id=str(session_id),
                total_discovered=total_discovered,
                processing_count=len(quartets),
                limit=quartet_limit,
            )

        logger.info(
            "quartets_discovered_for_session",
            session_id=str(session_id),
            quartet_count=len(quartets),
            parallel_processing_enabled=config.processing.enable_parallel_processing,
        )

        # Process quartets (parallel or sequential based on config)
        if config.processing.enable_parallel_processing:
            quartet_results = await _process_quartets_parallel(session_id, quartets)
        else:
            quartet_results = await _process_quartets_sequential(session_id, quartets)

        # Aggregate metrics from results
        success_count = 0
        failure_count = 0
        total_tokens = 0

        for result in quartet_results:
            if result.success:
                success_count += 1
                if result.ai_metrics:
                    total_tokens += result.ai_metrics.total_tokens
            else:
                failure_count += 1

        # Merge schemas if any quartets succeeded
        merge_result = None
        unique_pages = 0

        if success_count > 0:
            logger.info(
                "session_merge_start",
                session_id=str(session_id),
                successful_quartets=success_count,
            )

            merge_result = await merge_session_schemas(
                session_id=session_id,
                form_similarity_threshold=0.8,
                page_similarity_threshold=0.5,
                retention_days=30,
                debug_dir=debug_dir,
            )

            if merge_result.success and merge_result.metadata:
                unique_pages = merge_result.metadata.get("page_groups_count", 0)

                logger.info(
                    "session_merge_complete",
                    session_id=str(session_id),
                    source_schemas=merge_result.metadata.get("source_schema_count", 0),
                    unique_pages=unique_pages,
                    merged_schemas_saved=merge_result.metadata.get("merged_schemas_saved", 0),
                )
            else:
                logger.warning(
                    "session_merge_failed",
                    session_id=str(session_id),
                    error=merge_result.error_message if merge_result else "Unknown error",
                )
                # Fall back to success_count if merge fails
                unique_pages = success_count

        # Calculate aggregate metrics
        total_duration_ms = (time.time() - start_time) * 1000

        # For MVP: pages_added_to_master = 0 (no master merge yet)
        pages_added_to_master = 0

        # Create session result
        session_result = SessionProcessingResult(
            session_id=session_id,
            quartets_processed=len(quartets),  # Reusing field name for backward compatibility
            success_count=success_count,
            failure_count=failure_count,
            total_duration_ms=total_duration_ms,
            total_tokens=total_tokens,
            total_cost_usd=None,  # OpenRouter doesn't always provide cost
            unique_pages=unique_pages,
            pages_added_to_master=pages_added_to_master,
            triplet_results=quartet_results,  # Reusing field name for backward compatibility
        )

        # Log processing result
        log_processing_result(
            logger,
            operation="session_processing",
            session_id=str(session_id),
            quartets_processed=len(quartets),
            success_count=success_count,
            failure_count=failure_count,
            total_tokens=total_tokens,
            duration_ms=total_duration_ms,
        )

        logger.info(
            "session_processing_complete",
            session_id=str(session_id),
            quartets_processed=len(quartets),
            success_count=success_count,
            failure_count=failure_count,
            success_rate=session_result.success_rate(),
            total_duration_ms=total_duration_ms,
            avg_duration_ms=session_result.average_duration_ms(),
        )

        return session_result

    except Exception as e:
        total_duration_ms = (time.time() - start_time) * 1000

        logger.error(
            "session_processing_failed",
            session_id=str(session_id),
            error_type=type(e).__name__,
            error_message=str(e),
            duration_ms=total_duration_ms,
            exc_info=True,
        )

        raise


async def process_next_session() -> SessionProcessingResult | None:
    """Claim and process next session from queue.

    Returns:
        SessionProcessingResult | None: Result if session was processed, None if queue empty
    """
    logger.info("claiming_next_session")

    # Claim next session from Redis queue
    session_id = await claim_next_session()

    if not session_id:
        logger.info("queue_empty", message="No sessions in queue")
        return None

    logger.info("session_claimed", session_id=str(session_id))

    # Process the session
    return await process_session(session_id)
