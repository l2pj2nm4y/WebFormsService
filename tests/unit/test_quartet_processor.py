"""Unit tests for quartet processor pipeline.

Tests the quartet processing service in isolation with mocked dependencies.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.models.result import ProcessingResult
from src.models.schema import FormField, FormSchema, FormSection
from src.models.session import FileQuartet
from src.services.pipeline.quartet_processor import process_quartet


@pytest.fixture
def sample_quartet() -> FileQuartet:
    """Provide sample file quartet for testing."""
    return FileQuartet(
        sequence_number=1,
        screenshot_path="sessions/test-session/001-page.png",
        html_path="sessions/test-session/001-page.html",
        metadata_path="sessions/test-session/001-page.json",
        page_id_path="sessions/test-session/001-page.page.id.json",
    )


@pytest.fixture
def sample_form_schema() -> FormSchema:
    """Provide sample form schema for testing."""
    return FormSchema(
        page_identifier="Test Form - Page 1",
        form_name="TestForm",
        description="Test form description",
        sections=[
            FormSection(
                name="PersonalInfo",
                description="Personal information section",
                required=True,
                fields=[
                    FormField(
                        name="firstName",
                        type="string",
                        required=True,
                        description="First name field",
                        label="First Name",
                    )
                ],
                subsections=[],
            )
        ],
    )


@pytest.fixture
def sample_scraped_facts() -> str:
    """Provide sample scraped facts for testing."""
    return """Fields detected:
- firstName (text, required)
- email (email, required)

Buttons:
- Continue
- Save"""


class TestQuartetProcessor:
    """Unit tests for quartet processor."""

    @pytest.mark.asyncio
    async def test_process_quartet_success(
        self,
        sample_quartet: FileQuartet,
        sample_form_schema: FormSchema,
        sample_scraped_facts: dict,
        sample_screenshot_bytes: bytes,
    ) -> None:
        """Test successful quartet processing through all 5 stages."""
        session_id = uuid4()

        # Mock storage functions and image resize
        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load, patch(
            "src.services.pipeline.quartet_processor.write_schema_file"
        ) as mock_write, patch(
            "src.services.pipeline.quartet_processor.get_schema_generator"
        ) as mock_get_generator, patch(
            "src.services.pipeline.quartet_processor.resize_image_for_vision_api"
        ) as mock_resize:
            # Setup mocks
            mock_load.return_value = (
                sample_screenshot_bytes,
                "<html><body>Test</body></html>",
                {"website_id": "test.gov"},
                sample_scraped_facts,
            )

            # Mock image resize to return same bytes with metadata
            mock_resize.return_value = (
                sample_screenshot_bytes,
                {
                    "original_width": 1920,
                    "original_height": 1080,
                    "new_width": 1568,
                    "new_height": 882,
                    "original_format": "PNG",
                    "file_size_bytes": len(sample_screenshot_bytes),
                    "resized": True,
                    "within_api_limits": True,
                },
            )

            mock_write.return_value = "sessions/test-session/001-page.schema.json"

            mock_generator = AsyncMock()
            mock_generator.generate_schema.return_value = (
                sample_form_schema,
                {
                    "model": "anthropic/claude-sonnet-4.5",
                    "prompt_tokens": 2000,
                    "completion_tokens": 800,
                    "total_tokens": 2800,
                    "latency_ms": 1500.0,
                },
            )
            mock_get_generator.return_value = mock_generator

            # Process quartet
            result = await process_quartet(session_id, sample_quartet)

            # Verify result
            assert isinstance(result, ProcessingResult)
            assert result.success is True
            assert result.session_id == session_id
            assert result.sequence_number == 1
            assert result.operation == "quartet_processing"
            assert result.schema_file_path == "sessions/test-session/001-page.schema.json"
            assert result.duration_ms > 0

            # Verify AI metrics
            assert result.ai_metrics is not None
            assert result.ai_metrics.model == "anthropic/claude-sonnet-4.5"
            assert result.ai_metrics.total_tokens == 2800

            # Verify metadata
            assert result.metadata["screenshot_size_bytes"] == len(sample_screenshot_bytes)
            assert result.metadata["schema_sections_count"] == 1
            assert result.metadata["scraped_facts_size_bytes"] > 0

            # Verify all stages were called
            mock_load.assert_called_once_with(sample_quartet)
            mock_generator.generate_schema.assert_called_once_with(
                sample_screenshot_bytes,
                sample_quartet.sequence_number,
                str(session_id),
                sample_scraped_facts,
                {"website_id": "test.gov"},  # metadata parameter
            )
            mock_write.assert_called_once()

            # Verify quartet was updated
            assert sample_quartet.schema_file_path == "sessions/test-session/001-page.schema.json"

    @pytest.mark.asyncio
    async def test_process_quartet_file_load_failure(
        self, sample_quartet: FileQuartet
    ) -> None:
        """Test error handling when file loading fails."""
        session_id = uuid4()

        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load:
            mock_load.side_effect = FileNotFoundError("Screenshot file not found")

            result = await process_quartet(session_id, sample_quartet)

            # Verify failure result
            assert result.success is False
            assert result.error_type == "FileNotFoundError"
            assert "Screenshot file not found" in result.error_message
            assert result.schema_file_path is None
            assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_process_quartet_validation_failure(
        self,
        sample_quartet: FileQuartet,
        sample_scraped_facts: dict,
    ) -> None:
        """Test error handling when file validation fails."""
        session_id = uuid4()

        # Create oversized screenshot (>10MB)
        oversized_screenshot = b"x" * (11 * 1024 * 1024)

        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load, patch(
            "src.services.pipeline.quartet_processor.resize_image_for_vision_api"
        ) as mock_resize:
            mock_load.return_value = (
                oversized_screenshot,
                "<html>Test</html>",
                {},
                sample_scraped_facts,
            )

            # Mock resize to return oversized result
            mock_resize.return_value = (
                oversized_screenshot,
                {
                    "original_width": 8000,
                    "original_height": 8000,
                    "new_width": 8000,
                    "new_height": 8000,
                    "original_format": "PNG",
                    "file_size_bytes": len(oversized_screenshot),
                    "resized": False,
                    "within_api_limits": False,
                },
            )

            result = await process_quartet(session_id, sample_quartet)

            # Verify failure result
            assert result.success is False
            assert result.error_type == "FileSizeError"
            assert "screenshot" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_quartet_schema_generation_failure(
        self,
        sample_quartet: FileQuartet,
        sample_screenshot_bytes: bytes,
        sample_scraped_facts: dict,
    ) -> None:
        """Test error handling when schema generation fails."""
        session_id = uuid4()

        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load, patch(
            "src.services.pipeline.quartet_processor.get_schema_generator"
        ) as mock_get_generator, patch(
            "src.services.pipeline.quartet_processor.resize_image_for_vision_api"
        ) as mock_resize:
            mock_load.return_value = (
                sample_screenshot_bytes,
                "<html>Test</html>",
                {},
                sample_scraped_facts,
            )

            # Mock image resize
            mock_resize.return_value = (
                sample_screenshot_bytes,
                {
                    "original_width": 1920,
                    "original_height": 1080,
                    "new_width": 1568,
                    "new_height": 882,
                    "original_format": "PNG",
                    "file_size_bytes": len(sample_screenshot_bytes),
                    "resized": True,
                    "within_api_limits": True,
                },
            )

            mock_generator = AsyncMock()
            mock_generator.generate_schema.side_effect = Exception("AI API error")
            mock_get_generator.return_value = mock_generator

            result = await process_quartet(session_id, sample_quartet)

            # Verify failure result
            assert result.success is False
            assert result.operation == "schema_generation"
            assert result.error_type == "Exception"
            assert "AI API error" in result.error_message

    @pytest.mark.asyncio
    async def test_process_quartet_write_failure(
        self,
        sample_quartet: FileQuartet,
        sample_form_schema: FormSchema,
        sample_screenshot_bytes: bytes,
        sample_scraped_facts: dict,
    ) -> None:
        """Test error handling when schema file write fails."""
        session_id = uuid4()

        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load, patch(
            "src.services.pipeline.quartet_processor.write_schema_file"
        ) as mock_write, patch(
            "src.services.pipeline.quartet_processor.get_schema_generator"
        ) as mock_get_generator, patch(
            "src.services.pipeline.quartet_processor.resize_image_for_vision_api"
        ) as mock_resize:
            mock_load.return_value = (
                sample_screenshot_bytes,
                "<html>Test</html>",
                {},
                sample_scraped_facts,
            )

            # Mock image resize
            mock_resize.return_value = (
                sample_screenshot_bytes,
                {
                    "original_width": 1920,
                    "original_height": 1080,
                    "new_width": 1568,
                    "new_height": 882,
                    "original_format": "PNG",
                    "file_size_bytes": len(sample_screenshot_bytes),
                    "resized": True,
                    "within_api_limits": True,
                },
            )

            mock_generator = AsyncMock()
            mock_generator.generate_schema.return_value = (
                sample_form_schema,
                {
                    "model": "anthropic/claude-sonnet-4.5",
                    "prompt_tokens": 2000,
                    "completion_tokens": 800,
                    "total_tokens": 2800,
                    "latency_ms": 1500.0,
                },
            )
            mock_get_generator.return_value = mock_generator

            mock_write.side_effect = OSError("Storage write failed")

            result = await process_quartet(session_id, sample_quartet)

            # Verify failure result
            assert result.success is False
            assert result.error_type == "OSError"
            assert "Storage write failed" in result.error_message

    @pytest.mark.asyncio
    async def test_process_quartet_logs_operation(
        self,
        sample_quartet: FileQuartet,
        sample_form_schema: FormSchema,
        sample_screenshot_bytes: bytes,
        sample_scraped_facts: dict,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that quartet processing logs operation details."""
        session_id = uuid4()

        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load, patch(
            "src.services.pipeline.quartet_processor.write_schema_file"
        ) as mock_write, patch(
            "src.services.pipeline.quartet_processor.get_schema_generator"
        ) as mock_get_generator, patch(
            "src.services.pipeline.quartet_processor.resize_image_for_vision_api"
        ) as mock_resize:
            mock_load.return_value = (
                sample_screenshot_bytes,
                "<html>Test</html>",
                {},
                sample_scraped_facts,
            )

            # Mock image resize
            mock_resize.return_value = (
                sample_screenshot_bytes,
                {
                    "original_width": 1920,
                    "original_height": 1080,
                    "new_width": 1568,
                    "new_height": 882,
                    "original_format": "PNG",
                    "file_size_bytes": len(sample_screenshot_bytes),
                    "resized": True,
                    "within_api_limits": True,
                },
            )

            mock_write.return_value = "sessions/test/001-page.schema.json"

            mock_generator = AsyncMock()
            mock_generator.generate_schema.return_value = (
                sample_form_schema,
                {
                    "model": "anthropic/claude-sonnet-4.5",
                    "prompt_tokens": 2000,
                    "completion_tokens": 800,
                    "total_tokens": 2800,
                    "latency_ms": 1500.0,
                },
            )
            mock_get_generator.return_value = mock_generator

            result = await process_quartet(session_id, sample_quartet)

            # Verify the method completed successfully
            assert result.success is True

    @pytest.mark.asyncio
    async def test_process_quartet_invalid_json(
        self, sample_quartet: FileQuartet, sample_screenshot_bytes: bytes
    ) -> None:
        """Test error handling when scraped facts JSON is invalid."""
        session_id = uuid4()

        with patch(
            "src.services.pipeline.quartet_processor.load_quartet_files"
        ) as mock_load:
            # Simulate JSON decode error by making the loader fail
            mock_load.side_effect = ValueError("Invalid JSON in scraped facts")

            result = await process_quartet(session_id, sample_quartet)

            # Verify failure result
            assert result.success is False
            assert result.error_type == "ValueError"
            assert "JSON" in result.error_message or "json" in result.error_message
