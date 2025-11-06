"""Core library utilities.

This package contains:
- Configuration management (config.py)
- Structured logging (logging.py)
- File path and size validation (validation.py)
"""

from src.lib.config import Config, get_config, reset_config
from src.lib.logging import (
    configure_logging,
    get_logger,
    get_trace_id,
    log_ai_operation,
    log_error_with_context,
    log_file_operation,
    log_processing_result,
    reset_trace_id,
    set_trace_id,
)
from src.lib.validation import (
    FileSizeError,
    FileTypeError,
    PathTraversalError,
    SequenceNumberError,
    ValidationError,
    extract_sequence_number,
    validate_file_size,
    validate_file_type,
    validate_sequence_number,
    validate_session_id,
    validate_storage_path,
    validate_triplet_filenames,
    validate_website_id,
)

__all__ = [
    # Config
    "Config",
    "get_config",
    "reset_config",
    # Logging
    "configure_logging",
    "get_logger",
    "get_trace_id",
    "set_trace_id",
    "reset_trace_id",
    "log_ai_operation",
    "log_file_operation",
    "log_processing_result",
    "log_error_with_context",
    # Validation
    "ValidationError",
    "PathTraversalError",
    "FileSizeError",
    "FileTypeError",
    "SequenceNumberError",
    "validate_storage_path",
    "validate_file_size",
    "validate_file_type",
    "validate_sequence_number",
    "extract_sequence_number",
    "validate_triplet_filenames",
    "validate_session_id",
    "validate_website_id",
]
