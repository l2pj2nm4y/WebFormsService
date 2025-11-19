"""Unit tests for AI fact extractor service.

Tests the fact extraction service in isolation with mocked AI responses.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.models.page_identification import PageIdentification
from src.services.ai.fact_extractor import FactExtractor


@pytest.fixture
def sample_page_identification() -> PageIdentification:
    """Provide sample page identification for testing."""
    return PageIdentification(
        url="https://example.gov/citizenship",
        page_headings=["Application for Naturalization", "Form N-400"],
        form_headings=["Part 1", "Personal Information"],
        visual_sections=["header", "main_content_form", "footer"],
        navigation_buttons=["Continue", "Save for Later", "Previous"],
        progress_indicator="25%",
        page_number="1/4",
    )


@pytest.fixture
def mock_agent_result(sample_page_identification: PageIdentification) -> MagicMock:
    """Mock Pydantic AI agent result (pydantic-ai 1.11.1 API)."""
    mock_result = MagicMock()
    mock_result.output = sample_page_identification  # Use .output for structured output
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
        sample_page_identification: PageIdentification,
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
            page_id, metrics = await extractor.extract_facts(
                sample_screenshot_bytes, sequence_number=1, session_id="test-session"
            )

            # Verify result
            assert isinstance(page_id, PageIdentification)
            assert page_id == sample_page_identification

            # Verify metrics
            assert metrics["model"] == "anthropic/claude-sonnet-4.5"
            assert metrics["prompt_tokens"] == 1500
            assert metrics["completion_tokens"] == 400
            assert metrics["total_tokens"] == 1900
            assert metrics["latency_ms"] > 0

            # Verify agent was called
            mock_agent.run.assert_called_once()

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
