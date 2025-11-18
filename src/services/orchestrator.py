"""Session orchestration for end-to-end processing.

Orchestrates complete session processing workflow:
1. Claim session from Redis queue
2. Load session and discover quartets
3. Process each quartet (schema generation)
4. Track aggregate metrics and results
5. Return session processing result
"""

import time
from uuid import UUID

from src.lib.logging import get_logger, log_processing_result
from src.models.result import SessionProcessingResult
from src.services.coordination import claim_next_session
from src.services.pipeline import process_quartet
from src.services.storage.session_storage import discover_quartets

logger = get_logger(__name__)


async def process_session(session_id: UUID) -> SessionProcessingResult:
    """Process a complete session: discover quartets, generate schemas, aggregate results.

    Args:
        session_id: Session UUID to process

    Returns:
        SessionProcessingResult: Aggregate results with metrics

    Raises:
        FileNotFoundError: If session doesn't exist
    """
    start_time = time.time()

    logger.info("session_processing_start", session_id=str(session_id))

    try:
        # Discover quartets in session
        quartets = await discover_quartets(session_id)

        logger.info(
            "quartets_discovered_for_session",
            session_id=str(session_id),
            quartet_count=len(quartets),
        )

        # Process each quartet
        quartet_results = []
        success_count = 0
        failure_count = 0
        total_tokens = 0

        for quartet in quartets:
            result = await process_quartet(session_id, quartet)
            quartet_results.append(result)

            if result.success:
                success_count += 1
                if result.ai_metrics:
                    total_tokens += result.ai_metrics.total_tokens
            else:
                failure_count += 1

        # Calculate aggregate metrics
        total_duration_ms = (time.time() - start_time) * 1000

        # For MVP: unique_pages = success_count (no merging yet)
        # For MVP: pages_added_to_master = 0 (no master merge yet)
        unique_pages = success_count
        pages_added_to_master = 0

        # Create session result
        session_result = SessionProcessingResult(
            session_id=session_id,
            triplets_processed=len(quartets),  # Reusing field name for backward compatibility
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
            triplets_processed=len(quartets),
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
