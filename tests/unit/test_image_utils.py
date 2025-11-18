"""Unit tests for image utilities module.

Tests image resizing functionality for vision API compliance.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from src.lib.image_utils import (
    ImageResizeError,
    resize_image_for_vision_api,
    validate_image_dimensions,
)


def create_test_image(width: int, height: int, format: str = "PNG") -> bytes:
    """Create a test image with specified dimensions."""
    img = Image.new("RGB", (width, height), color="red")
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    return buffer.getvalue()


class TestResizeImageForVisionAPI:
    """Unit tests for resize_image_for_vision_api function."""

    def test_resize_large_image(self) -> None:
        """Test that large images are resized to target dimension."""
        # Create 3000x2000 image (aspect ratio 3:2)
        large_image = create_test_image(3000, 2000)

        resized_bytes, metadata = resize_image_for_vision_api(
            large_image, target_dimension=1568
        )

        # Verify resize occurred
        assert metadata["resized"] is True
        assert metadata["original_width"] == 3000
        assert metadata["original_height"] == 2000

        # Verify aspect ratio maintained (3:2)
        # Longest dimension should be 1568
        assert metadata["new_width"] == 1568
        assert metadata["new_height"] == 1045  # 1568 * (2/3) ≈ 1045

        # Verify within API limits
        assert metadata["within_api_limits"] is True
        assert metadata["new_width"] <= 8000
        assert metadata["new_height"] <= 8000

    def test_no_resize_for_small_image(self) -> None:
        """Test that images within target dimension are not resized."""
        # Create 800x600 image (smaller than target 1568)
        small_image = create_test_image(800, 600)

        resized_bytes, metadata = resize_image_for_vision_api(
            small_image, target_dimension=1568
        )

        # Verify NO resize occurred
        assert metadata["resized"] is False
        assert metadata["original_width"] == 800
        assert metadata["original_height"] == 600
        assert metadata["new_width"] == 800
        assert metadata["new_height"] == 600

        # Still within API limits
        assert metadata["within_api_limits"] is True

    def test_resize_preserves_aspect_ratio_portrait(self) -> None:
        """Test aspect ratio preservation for portrait orientation."""
        # Create 1000x2000 image (aspect ratio 1:2, portrait)
        portrait_image = create_test_image(1000, 2000)

        resized_bytes, metadata = resize_image_for_vision_api(
            portrait_image, target_dimension=1568
        )

        # Verify resize occurred
        assert metadata["resized"] is True

        # Verify aspect ratio maintained (1:2)
        # Height (longer dimension) should be 1568
        assert metadata["new_height"] == 1568
        assert metadata["new_width"] == 784  # 1568 * (1/2)

    def test_resize_preserves_aspect_ratio_landscape(self) -> None:
        """Test aspect ratio preservation for landscape orientation."""
        # Create 2000x1000 image (aspect ratio 2:1, landscape)
        landscape_image = create_test_image(2000, 1000)

        resized_bytes, metadata = resize_image_for_vision_api(
            landscape_image, target_dimension=1568
        )

        # Verify resize occurred
        assert metadata["resized"] is True

        # Verify aspect ratio maintained (2:1)
        # Width (longer dimension) should be 1568
        assert metadata["new_width"] == 1568
        assert metadata["new_height"] == 784  # 1568 * (1/2)

    def test_jpeg_format_handling(self) -> None:
        """Test JPEG format is preserved and handled correctly."""
        # Create JPEG image
        jpeg_image = create_test_image(2000, 1500, format="JPEG")

        resized_bytes, metadata = resize_image_for_vision_api(
            jpeg_image, target_dimension=1568
        )

        # Verify format metadata
        assert metadata["original_format"] == "JPEG"
        assert metadata["resized"] is True

        # Verify image is valid JPEG
        resized_img = Image.open(io.BytesIO(resized_bytes))
        assert resized_img.format in ["JPEG", "PNG"]

    def test_png_format_handling(self) -> None:
        """Test PNG format is preserved and handled correctly."""
        # Create PNG image
        png_image = create_test_image(2000, 1500, format="PNG")

        resized_bytes, metadata = resize_image_for_vision_api(
            png_image, target_dimension=1568
        )

        # Verify format metadata
        assert metadata["original_format"] == "PNG"
        assert metadata["resized"] is True

        # Verify image is valid PNG
        resized_img = Image.open(io.BytesIO(resized_bytes))
        assert resized_img.format == "PNG"

    def test_quality_parameter(self) -> None:
        """Test quality parameter affects output size."""
        test_image = create_test_image(2000, 1500, format="JPEG")

        # Resize with high quality
        high_quality_bytes, high_metadata = resize_image_for_vision_api(
            test_image, quality=95
        )

        # Resize with low quality
        low_quality_bytes, low_metadata = resize_image_for_vision_api(
            test_image, quality=50
        )

        # Verify lower quality produces smaller file
        assert low_metadata["file_size_bytes"] < high_metadata["file_size_bytes"]

        # Both should have same dimensions
        assert low_metadata["new_width"] == high_metadata["new_width"]
        assert low_metadata["new_height"] == high_metadata["new_height"]

    def test_custom_target_dimension(self) -> None:
        """Test custom target dimension parameter."""
        test_image = create_test_image(4000, 3000)

        # Resize to custom target of 2000px
        resized_bytes, metadata = resize_image_for_vision_api(
            test_image, target_dimension=2000
        )

        # Verify resize to custom target (longest dimension = 2000)
        assert metadata["resized"] is True
        assert metadata["new_width"] == 2000
        assert metadata["new_height"] == 1500  # 2000 * (3/4)

    def test_invalid_image_data(self) -> None:
        """Test error handling for invalid image data."""
        invalid_data = b"not an image"

        with pytest.raises(ImageResizeError) as exc_info:
            resize_image_for_vision_api(invalid_data)

        assert "Invalid image format" in str(exc_info.value)

    def test_file_size_within_limits(self) -> None:
        """Test file size is within API limits after resize."""
        # Create large image
        large_image = create_test_image(5000, 5000)

        resized_bytes, metadata = resize_image_for_vision_api(large_image)

        # Verify file size is reasonable (should be well under 5MB for 1568x1568)
        assert metadata["file_size_bytes"] < 5 * 1024 * 1024  # 5MB limit
        assert metadata["within_api_limits"] is True

    def test_metadata_completeness(self) -> None:
        """Test that all required metadata fields are present."""
        test_image = create_test_image(2000, 1500)

        resized_bytes, metadata = resize_image_for_vision_api(test_image)

        # Verify all required metadata fields
        assert "original_width" in metadata
        assert "original_height" in metadata
        assert "new_width" in metadata
        assert "new_height" in metadata
        assert "original_format" in metadata
        assert "file_size_bytes" in metadata
        assert "resized" in metadata
        assert "within_api_limits" in metadata

    def test_edge_case_exact_target_size(self) -> None:
        """Test image exactly at target dimension."""
        # Create image exactly 1568x1568
        exact_image = create_test_image(1568, 1568)

        resized_bytes, metadata = resize_image_for_vision_api(
            exact_image, target_dimension=1568
        )

        # Should not resize (already at target)
        assert metadata["resized"] is False
        assert metadata["new_width"] == 1568
        assert metadata["new_height"] == 1568


class TestValidateImageDimensions:
    """Unit tests for validate_image_dimensions function."""

    def test_valid_dimensions(self) -> None:
        """Test validation passes for valid dimensions."""
        # Should not raise for dimensions within limits
        validate_image_dimensions(1920, 1080)
        validate_image_dimensions(7999, 7999)

    def test_exceeds_width_limit(self) -> None:
        """Test validation fails when width exceeds limit."""
        with pytest.raises(ValueError) as exc_info:
            validate_image_dimensions(8001, 1080, max_dimension=8000)

        assert "exceed API limit" in str(exc_info.value)

    def test_exceeds_height_limit(self) -> None:
        """Test validation fails when height exceeds limit."""
        with pytest.raises(ValueError) as exc_info:
            validate_image_dimensions(1920, 8001, max_dimension=8000)

        assert "exceed API limit" in str(exc_info.value)

    def test_zero_dimensions(self) -> None:
        """Test validation fails for zero dimensions."""
        with pytest.raises(ValueError) as exc_info:
            validate_image_dimensions(0, 1080)

        assert "Invalid image dimensions" in str(exc_info.value)

    def test_negative_dimensions(self) -> None:
        """Test validation fails for negative dimensions."""
        with pytest.raises(ValueError) as exc_info:
            validate_image_dimensions(1920, -1080)

        assert "Invalid image dimensions" in str(exc_info.value)

    def test_custom_max_dimension(self) -> None:
        """Test validation with custom max dimension."""
        # Should pass with higher limit
        validate_image_dimensions(9000, 9000, max_dimension=10000)

        # Should fail with lower limit
        with pytest.raises(ValueError):
            validate_image_dimensions(5000, 5000, max_dimension=4000)
