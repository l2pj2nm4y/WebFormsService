"""Structured logging with trace IDs and JSON output.

This module provides structured logging using structlog with support for:
- JSON formatted output for production environments
- Human-readable text output for development
- Trace ID tracking for request correlation
- AI operation metrics (prompt, model, latency, tokens, cost)
- File operation context (operation, path, size)
- Error context (operation, input snapshot, system state)
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from src.lib.config import get_config

# Context variable for trace ID propagation
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Get current trace ID or generate a new one.

    Returns:
        str: Current trace ID (UUID format)
    """
    trace_id = trace_id_var.get()
    if not trace_id:
        trace_id = str(uuid.uuid4())
        trace_id_var.set(trace_id)
    return trace_id


def set_trace_id(trace_id: str) -> None:
    """Set trace ID for current context.

    Args:
        trace_id: Trace ID to set (should be UUID format)
    """
    trace_id_var.set(trace_id)


def reset_trace_id() -> None:
    """Reset trace ID (generates new UUID on next get_trace_id call)."""
    trace_id_var.set("")


def add_trace_id(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add trace ID to log event.

    Args:
        logger: Logger instance
        method_name: Method name being called
        event_dict: Event dictionary

    Returns:
        EventDict: Event dictionary with trace_id added
    """
    event_dict["trace_id"] = get_trace_id()
    return event_dict


def add_timestamp(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add ISO timestamp to log event.

    Args:
        logger: Logger instance
        method_name: Method name being called
        event_dict: Event dictionary

    Returns:
        EventDict: Event dictionary with timestamp added
    """
    event_dict["timestamp"] = structlog.processors.TimeStamper(fmt="iso")(
        logger, method_name, event_dict
    )["timestamp"]
    return event_dict


def configure_logging() -> None:
    """Configure structured logging based on application configuration.

    Sets up structlog with appropriate processors for JSON or text output,
    trace ID tracking, and standardized log formatting.
    """
    config = get_config()

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.logging.level),
    )

    # Determine processors based on log format
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_trace_id,
        add_timestamp,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if config.logging.format == "json":
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Human-readable text output for development
        processors.extend(
            [
                structlog.dev.ConsoleRenderer(
                    colors=True,
                    exception_formatter=structlog.dev.plain_traceback,
                )
            ]
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (defaults to calling module name)

    Returns:
        BoundLogger: Configured logger instance
    """
    return structlog.get_logger(name)


def log_ai_operation(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: float,
    cost_usd: float | None = None,
    prompt_preview: str | None = None,
) -> None:
    """Log AI operation with standardized metrics.

    Args:
        logger: Logger instance
        operation: Operation name (fact_extraction, prompt_generation, etc.)
        model: Model identifier
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        total_tokens: Total tokens used
        latency_ms: Operation latency in milliseconds
        cost_usd: Optional cost in USD
        prompt_preview: Optional prompt preview (first 100 chars)
    """
    logger.info(
        "ai_operation",
        operation=operation,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        prompt_preview=prompt_preview[:100] if prompt_preview else None,
    )


def log_file_operation(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    path: str,
    size_bytes: int | None = None,
    duration_ms: float | None = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Log file operation with context.

    Args:
        logger: Logger instance
        operation: Operation name (read, write, delete, etc.)
        path: File path
        size_bytes: Optional file size in bytes
        duration_ms: Optional operation duration in milliseconds
        success: Whether operation succeeded
        error: Optional error message
    """
    logger.info(
        "file_operation",
        operation=operation,
        path=path,
        size_bytes=size_bytes,
        duration_ms=duration_ms,
        success=success,
        error=error,
    )


def log_processing_result(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    session_id: str,
    triplets_processed: int,
    success_count: int,
    failure_count: int,
    total_tokens: int,
    total_cost_usd: float | None = None,
    duration_ms: float | None = None,
) -> None:
    """Log processing result with statistics.

    Args:
        logger: Logger instance
        operation: Operation name (session_processing, batch_processing, etc.)
        session_id: Session identifier
        triplets_processed: Number of triplets processed
        success_count: Number of successful operations
        failure_count: Number of failed operations
        total_tokens: Total AI tokens used
        total_cost_usd: Optional total cost in USD
        duration_ms: Optional total duration in milliseconds
    """
    logger.info(
        "processing_result",
        operation=operation,
        session_id=session_id,
        triplets_processed=triplets_processed,
        success_count=success_count,
        failure_count=failure_count,
        success_rate=(success_count / triplets_processed * 100) if triplets_processed > 0 else 0,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        duration_ms=duration_ms,
    )


def log_error_with_context(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    error: Exception,
    input_snapshot: dict[str, Any] | None = None,
    system_state: dict[str, Any] | None = None,
) -> None:
    """Log error with rich context for troubleshooting.

    Args:
        logger: Logger instance
        operation: Operation that failed
        error: Exception that occurred
        input_snapshot: Optional snapshot of input data
        system_state: Optional system state information
    """
    logger.error(
        "operation_failed",
        operation=operation,
        error_type=type(error).__name__,
        error_message=str(error),
        input_snapshot=input_snapshot,
        system_state=system_state,
        exc_info=True,
    )
