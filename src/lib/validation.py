"""File path and size validation with security checks.

This module provides validation functions for file operations with focus on:
- Path traversal attack prevention
- File size limit enforcement
- File type validation
- Sequence number validation for file triplets
"""

import re
from pathlib import Path
from typing import Literal

from src.lib.config import get_config


class ValidationError(Exception):
    """Base class for validation errors."""

    pass


class PathTraversalError(ValidationError):
    """Raised when path traversal attack is detected."""

    pass


class FileSizeError(ValidationError):
    """Raised when file size exceeds limits."""

    pass


class FileTypeError(ValidationError):
    """Raised when file type is invalid."""

    pass


class SequenceNumberError(ValidationError):
    """Raised when sequence number is invalid."""

    pass


def validate_storage_path(path: str) -> None:
    """Validate storage path to prevent path traversal attacks.

    Args:
        path: Storage path to validate

    Raises:
        PathTraversalError: If path contains traversal attempts or invalid patterns
    """
    # Check for path traversal attempts
    if ".." in path:
        raise PathTraversalError(f"Path traversal detected: {path}")

    # Check for absolute paths
    if path.startswith("/"):
        raise PathTraversalError(f"Absolute path not allowed: {path}")

    # Check for valid path prefix (sessions/ or masters/)
    if not (path.startswith("sessions/") or path.startswith("masters/")):
        raise PathTraversalError(f"Invalid path prefix: {path}")

    # Check for null bytes
    if "\x00" in path:
        raise PathTraversalError(f"Null byte in path: {path}")

    # Normalize and verify path doesn't escape base directory
    normalized = Path(path).resolve()
    base_sessions = Path("sessions").resolve()
    base_masters = Path("masters").resolve()

    if not (
        str(normalized).startswith(str(base_sessions))
        or str(normalized).startswith(str(base_masters))
    ):
        raise PathTraversalError(f"Path escapes base directory: {path}")


def validate_file_size(
    size_bytes: int, file_type: Literal["screenshot", "html", "metadata"]
) -> None:
    """Validate file size against configured limits.

    Args:
        size_bytes: File size in bytes
        file_type: Type of file (screenshot, html, metadata)

    Raises:
        FileSizeError: If file size exceeds limit for file type
    """
    config = get_config()

    limits = {
        "screenshot": config.file_size_limits.screenshot_size_mb * 1024 * 1024,
        "html": config.file_size_limits.html_size_mb * 1024 * 1024,
        "metadata": config.file_size_limits.metadata_size_kb * 1024,
    }

    max_size = limits.get(file_type)
    if max_size is None:
        raise ValueError(f"Unknown file type: {file_type}")

    if size_bytes > max_size:
        raise FileSizeError(
            f"{file_type} size {size_bytes} bytes exceeds limit of {max_size} bytes"
        )


def validate_file_type(
    filename: str, expected_type: Literal["screenshot", "html", "metadata"]
) -> None:
    """Validate file type based on extension.

    Args:
        filename: Filename to validate
        expected_type: Expected file type

    Raises:
        FileTypeError: If file extension doesn't match expected type
    """
    valid_extensions = {
        "screenshot": {".png", ".jpg", ".jpeg"},
        "html": {".html", ".htm"},
        "metadata": {".json"},
    }

    extensions = valid_extensions.get(expected_type)
    if extensions is None:
        raise ValueError(f"Unknown expected type: {expected_type}")

    file_ext = Path(filename).suffix.lower()
    if file_ext not in extensions:
        raise FileTypeError(
            f"Invalid extension '{file_ext}' for {expected_type}, expected one of {extensions}"
        )


def validate_sequence_number(sequence_number: int) -> None:
    """Validate triplet sequence number.

    Args:
        sequence_number: Sequence number to validate (1-999)

    Raises:
        SequenceNumberError: If sequence number is out of range
    """
    if not (1 <= sequence_number <= 999):
        raise SequenceNumberError(
            f"Sequence number {sequence_number} must be between 1 and 999"
        )


def extract_sequence_number(filename: str) -> int:
    """Extract sequence number from filename with format '###-name.ext'.

    Args:
        filename: Filename to parse

    Returns:
        int: Extracted sequence number

    Raises:
        SequenceNumberError: If sequence number cannot be extracted or is invalid
    """
    # Pattern: ###-name.ext where ### is 001-999
    pattern = r"^(\d{3})-.*\.[a-zA-Z0-9]+$"
    match = re.match(pattern, filename)

    if not match:
        raise SequenceNumberError(
            f"Filename '{filename}' does not match pattern '###-name.ext'"
        )

    sequence_str = match.group(1)
    sequence_number = int(sequence_str)

    validate_sequence_number(sequence_number)
    return sequence_number


def validate_triplet_filenames(
    screenshot_filename: str, html_filename: str, metadata_filename: str
) -> int:
    """Validate that triplet files have matching sequence numbers and correct types.

    Args:
        screenshot_filename: Screenshot filename
        html_filename: HTML filename
        metadata_filename: Metadata filename

    Returns:
        int: Common sequence number

    Raises:
        SequenceNumberError: If sequence numbers don't match
        FileTypeError: If file types are invalid
    """
    # Extract sequence numbers
    screenshot_seq = extract_sequence_number(screenshot_filename)
    html_seq = extract_sequence_number(html_filename)
    metadata_seq = extract_sequence_number(metadata_filename)

    # Verify all match
    if not (screenshot_seq == html_seq == metadata_seq):
        raise SequenceNumberError(
            f"Triplet sequence numbers don't match: "
            f"screenshot={screenshot_seq}, html={html_seq}, metadata={metadata_seq}"
        )

    # Validate file types
    validate_file_type(screenshot_filename, "screenshot")
    validate_file_type(html_filename, "html")
    validate_file_type(metadata_filename, "metadata")

    return screenshot_seq


def validate_session_id(session_id_str: str) -> None:
    """Validate session ID format (should be valid UUID).

    Args:
        session_id_str: Session ID string to validate

    Raises:
        ValidationError: If session ID is not a valid UUID format
    """
    # UUID format: 8-4-4-4-12 hex digits
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    if not re.match(uuid_pattern, session_id_str.lower()):
        raise ValidationError(f"Invalid session ID format: {session_id_str}")


def validate_website_id(website_id: str) -> None:
    """Validate website ID format (domain name).

    Args:
        website_id: Website ID to validate

    Raises:
        ValidationError: If website ID is not a valid domain format
    """
    # Basic domain name validation
    domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    if not re.match(domain_pattern, website_id):
        raise ValidationError(f"Invalid website ID format: {website_id}")
