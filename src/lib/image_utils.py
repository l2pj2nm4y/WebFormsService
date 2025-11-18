"""Image processing utilities for vision API compliance.

Provides functions for resizing and validating images to meet AI vision API requirements,
particularly Anthropic's 8000x8000 pixel limit and 5MB file size constraints.
"""

import io
from pathlib import Path
from typing import TypedDict

from PIL import Image

from src.lib.logging import get_logger

logger = get_logger(__name__)


class ResizeMetadata(TypedDict):
    """Metadata about image resize operation."""

    original_width: int
    original_height: int
    new_width: int
    new_height: int
    original_format: str | None
    file_size_bytes: int
    resized: bool
    within_api_limits: bool


class ImageResizeError(Exception):
    """Exception raised for image resize errors."""

    pass


def resize_image_for_vision_api(
    image_bytes: bytes,
    target_dimension: int = 1568,
    max_dimension: int = 8000,
    quality: int = 95,
    max_file_size_bytes: int = 5 * 1024 * 1024,  # 5MB
) -> tuple[bytes, ResizeMetadata]:
    """Resize image to optimal dimensions for Anthropic Vision API.

    Resizes images to target dimension while maintaining aspect ratio
    and ensuring compliance with API limits (8000x8000 pixels, 5MB file size).

    Args:
        image_bytes: Raw image bytes (PNG or JPEG)
        target_dimension: Optimal dimension for best API performance (default 1568px)
        max_dimension: Maximum allowed dimension (default 8000px for Anthropic)
        quality: JPEG/PNG quality for saving (1-100, default 95)
        max_file_size_bytes: Maximum file size in bytes (default 5MB)

    Returns:
        tuple[bytes, ResizeMetadata]: Resized image bytes and metadata

    Raises:
        ImageResizeError: If image processing fails
    """
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(image_bytes))
        original_size = (img.width, img.height)
        original_format = img.format

        logger.debug(
            "processing_image",
            width=img.width,
            height=img.height,
            format=original_format,
        )

        # Determine if resize needed
        needs_resize = img.width > target_dimension or img.height > target_dimension

        if needs_resize:
            # Use thumbnail for optimal quality and aspect ratio preservation
            # LANCZOS provides best quality for downscaling
            img.thumbnail((target_dimension, target_dimension), Image.Resampling.LANCZOS)

            logger.info(
                "image_resized",
                original_size=original_size,
                new_size=(img.width, img.height),
                target=target_dimension,
            )
        else:
            logger.debug(
                "image_within_target",
                size=original_size,
                target=target_dimension,
            )

        # Convert to bytes
        output_buffer = io.BytesIO()

        # Determine save format (preserve original or use PNG for unknown)
        save_format = original_format if original_format in ["PNG", "JPEG"] else "PNG"

        # Save with optimization
        save_kwargs = {"optimize": True, "quality": quality}

        if save_format == "PNG":
            save_kwargs["compress_level"] = 9

        img.save(output_buffer, format=save_format, **save_kwargs)
        resized_bytes = output_buffer.getvalue()

        # Create metadata
        metadata: ResizeMetadata = {
            "original_width": original_size[0],
            "original_height": original_size[1],
            "new_width": img.width,
            "new_height": img.height,
            "original_format": original_format,
            "file_size_bytes": len(resized_bytes),
            "resized": needs_resize,
            "within_api_limits": (
                img.width <= max_dimension
                and img.height <= max_dimension
                and len(resized_bytes) <= max_file_size_bytes
            ),
        }

        # Log warning if still exceeds limits
        if not metadata["within_api_limits"]:
            logger.warning(
                "image_exceeds_api_limits",
                width=img.width,
                height=img.height,
                file_size_mb=len(resized_bytes) / (1024 * 1024),
                max_dimension=max_dimension,
                max_file_size_mb=max_file_size_bytes / (1024 * 1024),
            )

        return resized_bytes, metadata

    except Image.UnidentifiedImageError as e:
        raise ImageResizeError(f"Invalid image format: {e}") from e
    except OSError as e:
        raise ImageResizeError(f"Failed to process image: {e}") from e
    except Exception as e:
        raise ImageResizeError(f"Unexpected error during resize: {e}") from e


def validate_image_dimensions(
    width: int, height: int, max_dimension: int = 8000
) -> None:
    """Validate image dimensions against API limits.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        max_dimension: Maximum allowed dimension (default 8000px)

    Raises:
        ValueError: If dimensions exceed limits
    """
    if width > max_dimension or height > max_dimension:
        raise ValueError(
            f"Image dimensions {width}x{height} exceed API limit of {max_dimension}x{max_dimension}"
        )

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image dimensions: {width}x{height}")
