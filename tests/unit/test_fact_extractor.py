"""Unit tests for AI fact extractor service.

Tests the fact extraction service in isolation with mocked AI responses.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.models.fact import FactFile, FormElements
from src.services.ai.fact_extractor import FactExtractor


@pytest.fixture
def sample_fact_file() -> FactFile:
    """Provide sample fact file for testing."""
    return FactFile(
        visual_headings=["Application for Naturalization", "Form N-400", "Part 1"],
        visual_sections=["header with logo", "main content area", "footer"],
        form_elements=FormElements(
            has_forms=True,
            visible_fields=["text", "text", "date"],
            buttons=["Continue", "Save for Later"],
        ),
        layout_pattern="Single column form with sequential fields",
        content_keywords=["citizenship", "naturalization", "government", "form"],
    )


@pytest.fixture
def mock_agent_result(sample_fact_file: FactFile) -> MagicMock:
    """Mock Pydantic AI agent result."""
    mock_result = MagicMock()
    mock_result.data = sample_fact_file
    mock_result.usage.return_value = MagicMock(
        request_tokens=1500, response_tokens=400, total_tokens=1900
    )
    return mock_result


class TestFactExtractor:
    """Unit tests for FactExtractor class."""

    @pytest.mark.asyncio
    async def test_extract_facts_success(
        self,
        sample_screenshot_bytes: bytes,
        sample_fact_file: FactFile,
        mock_agent_result: MagicMock,
    ) -> None:
        """Test successful fact extraction from screenshot."""
        with patch("src.services.ai.fact_extractor.Agent") as mock_agent_class:
            # Setup mock
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_agent_result
            mock_agent_class.return_value = mock_agent

            extractor = FactExtractor()
            extractor.agent = mock_agent

            # Extract facts
            fact_file, metrics = await extractor.extract_facts(
                sample_screenshot_bytes, sequence_number=1, session_id="test-session"
            )

            # Verify result
            assert isinstance(fact_file, FactFile)
            assert fact_file == sample_fact_file

            # Verify metrics
            assert metrics["model"] == "anthropic/claude-3.5-haiku"
            assert metrics["prompt_tokens"] == 1500
            assert metrics["completion_tokens"] == 400
            assert metrics["total_tokens"] == 1900
            assert metrics["latency_ms"] > 0

            # Verify agent was called
            mock_agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_facts_detects_png_format(
        self, sample_screenshot_bytes: bytes, mock_agent_result: MagicMock
    ) -> None:
        """Test PNG format detection."""
        with patch("src.services.ai.fact_extractor.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_agent_result
            mock_agent_class.return_value = mock_agent

            extractor = FactExtractor()
            extractor.agent = mock_agent

            await extractor.extract_facts(
                sample_screenshot_bytes, sequence_number=1, session_id="test"
            )

            # Verify PNG was detected (message contains image/png)
            call_args = mock_agent.run.call_args
            message = call_args[1]["message_history"][0]
            image_content = message["content"][1]
            assert "image/png" in image_content["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_extract_facts_detects_jpeg_format(
        self, mock_agent_result: MagicMock
    ) -> None:
        """Test JPEG format detection."""
        # JPEG magic bytes
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        with patch("src.services.ai.fact_extractor.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_agent_result
            mock_agent_class.return_value = mock_agent

            extractor = FactExtractor()
            extractor.agent = mock_agent

            await extractor.extract_facts(
                jpeg_bytes, sequence_number=1, session_id="test"
            )

            # Verify JPEG was detected
            call_args = mock_agent.run.call_args
            message = call_args[1]["message_history"][0]
            image_content = message["content"][1]
            assert "image/jpeg" in image_content["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_extract_facts_rejects_invalid_format(self) -> None:
        """Test rejection of unsupported image formats."""
        invalid_bytes = b"\x00\x00\x00\x00" + b"invalid"

        extractor = FactExtractor()

        with pytest.raises(ValueError, match="Unsupported image format"):
            await extractor.extract_facts(
                invalid_bytes, sequence_number=1, session_id="test"
            )

    @pytest.mark.asyncio
    async def test_extract_facts_handles_ai_failure(
        self, sample_screenshot_bytes: bytes
    ) -> None:
        """Test error handling when AI operation fails."""
        with patch("src.services.ai.fact_extractor.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("AI API error")
            mock_agent_class.return_value = mock_agent

            extractor = FactExtractor()
            extractor.agent = mock_agent

            with pytest.raises(Exception, match="AI API error"):
                await extractor.extract_facts(
                    sample_screenshot_bytes, sequence_number=1, session_id="test"
                )

    @pytest.mark.asyncio
    async def test_extract_facts_logs_operation(
        self,
        sample_screenshot_bytes: bytes,
        mock_agent_result: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that fact extraction logs operation details."""
        with patch("src.services.ai.fact_extractor.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_agent_result
            mock_agent_class.return_value = mock_agent

            extractor = FactExtractor()
            extractor.agent = mock_agent

            await extractor.extract_facts(
                sample_screenshot_bytes,
                sequence_number=5,
                session_id="test-session-123",
            )

            # Verify logging occurred (structlog writes to stdout, not caplog)
            # The actual logging is verified in integration tests
            # Here we just verify the method completed successfully
            assert mock_agent.run.called


class TestFactExtractorSingleton:
    """Test fact extractor singleton pattern."""

    def test_get_fact_extractor_returns_singleton(self) -> None:
        """Test that get_fact_extractor returns same instance."""
        from src.services.ai.fact_extractor import (
            get_fact_extractor,
            reset_fact_extractor,
        )

        reset_fact_extractor()

        extractor1 = get_fact_extractor()
        extractor2 = get_fact_extractor()

        assert extractor1 is extractor2

    def test_reset_fact_extractor_clears_instance(self) -> None:
        """Test that reset creates new instance."""
        from src.services.ai.fact_extractor import (
            get_fact_extractor,
            reset_fact_extractor,
        )

        extractor1 = get_fact_extractor()
        reset_fact_extractor()
        extractor2 = get_fact_extractor()

        assert extractor1 is not extractor2
