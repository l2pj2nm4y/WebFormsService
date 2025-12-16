"""Unit tests for parallel quartet processing in orchestrator.

Tests the parallel processing capabilities including:
- Parallel vs sequential processing behavior
- Concurrency limit enforcement
- Result correctness and ordering
- Performance improvements
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.models.result import AIMetrics, ProcessingResult, SessionProcessingResult
from src.models.schema import FormField, FormSchema, FormSection
from src.models.session import FileQuartet
from src.services.orchestrator import (
    _process_quartets_parallel,
    _process_quartets_sequential,
    process_session,
)


@pytest.fixture
def sample_quartets() -> list[FileQuartet]:
    """Provide sample file quartets for testing."""
    return [
        FileQuartet(
            sequence_number=i,
            screenshot_path=f"sessions/test-session/{i:03d}-page.png",
            html_path=f"sessions/test-session/{i:03d}-page.html",
            metadata_path=f"sessions/test-session/{i:03d}-page.json",
            page_id_path=f"sessions/test-session/{i:03d}-page.page.id.json",
        )
        for i in range(1, 11)  # 10 quartets
    ]


@pytest.fixture
def sample_processing_result() -> ProcessingResult:
    """Provide sample processing result."""
    return ProcessingResult(
        session_id=uuid4(),
        sequence_number=1,
        operation="quartet_processing",
        success=True,
        duration_ms=1000.0,
        schema_file_path="sessions/test/001-page.schema.json",
        ai_metrics=AIMetrics(
            model="anthropic/claude-sonnet-4.5",
            prompt_tokens=2000,
            completion_tokens=800,
            total_tokens=2800,
            latency_ms=1000.0,
        ),
        metadata={
            "screenshot_size_bytes": 1024,
            "html_size_bytes": 512,
            "scraped_facts_size_bytes": 256,
            "schema_sections_count": 1,
        },
    )


class TestParallelProcessing:
    """Tests for parallel quartet processing."""

    @pytest.mark.asyncio
    async def test_process_quartets_parallel_success(
        self, sample_quartets: list[FileQuartet], sample_processing_result: ProcessingResult
    ) -> None:
        """Test successful parallel processing of all quartets."""
        session_id = uuid4()

        with patch("src.services.orchestrator.process_quartet") as mock_process, patch(
            "src.services.orchestrator.get_config"
        ) as mock_get_config:
            # Setup config mock
            mock_config = AsyncMock()
            mock_config.processing.quartet_concurrency = 5
            mock_get_config.return_value = mock_config

            # Setup process_quartet mock to return success
            async def mock_process_quartet(sid, quartet):
                # Simulate AI processing delay
                await asyncio.sleep(0.1)
                result = ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=True,
                    duration_ms=100.0,
                    schema_file_path=f"sessions/test/{quartet.sequence_number:03d}-page.schema.json",
                    ai_metrics=AIMetrics(
                        model="anthropic/claude-sonnet-4.5",
                        prompt_tokens=2000,
                        completion_tokens=800,
                        total_tokens=2800,
                        latency_ms=100.0,
                    ),
                )
                return result

            mock_process.side_effect = mock_process_quartet

            # Execute parallel processing
            start_time = time.time()
            results = await _process_quartets_parallel(session_id, sample_quartets)
            duration = time.time() - start_time

            # Verify all quartets were processed
            assert len(results) == 10
            assert all(r.success for r in results)

            # Verify results are in correct order
            for i, result in enumerate(results, start=1):
                assert result.sequence_number == i

            # Verify parallel execution (should be faster than sequential)
            # With 10 quartets @ 0.1s each and concurrency=5:
            # Parallel: ~0.2s (2 batches of 5)
            # Sequential: ~1.0s (10 * 0.1s)
            assert duration < 0.5  # Should complete in under 0.5s (well under 1.0s sequential)

            # Verify process_quartet was called for each quartet
            assert mock_process.call_count == 10

    @pytest.mark.asyncio
    async def test_process_quartets_parallel_respects_concurrency_limit(
        self, sample_quartets: list[FileQuartet]
    ) -> None:
        """Test that parallel processing respects concurrency limit."""
        session_id = uuid4()
        max_concurrent = 0  # Track max concurrent executions
        current_concurrent = 0  # Track current concurrent executions
        lock = asyncio.Lock()

        with patch("src.services.orchestrator.process_quartet") as mock_process, patch(
            "src.services.orchestrator.get_config"
        ) as mock_get_config:
            # Setup config mock with concurrency limit of 3
            mock_config = AsyncMock()
            mock_config.processing.quartet_concurrency = 3
            mock_get_config.return_value = mock_config

            # Setup process_quartet mock to track concurrency
            async def mock_process_quartet(sid, quartet):
                nonlocal max_concurrent, current_concurrent

                async with lock:
                    current_concurrent += 1
                    max_concurrent = max(max_concurrent, current_concurrent)

                await asyncio.sleep(0.05)  # Simulate processing

                async with lock:
                    current_concurrent -= 1

                return ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=True,
                    duration_ms=50.0,
                )

            mock_process.side_effect = mock_process_quartet

            # Execute parallel processing
            await _process_quartets_parallel(session_id, sample_quartets)

            # Verify concurrency limit was respected
            assert max_concurrent <= 3
            assert max_concurrent > 1  # Verify actual parallelism occurred

    @pytest.mark.asyncio
    async def test_process_quartets_sequential(
        self, sample_quartets: list[FileQuartet]
    ) -> None:
        """Test sequential processing of quartets."""
        session_id = uuid4()

        with patch("src.services.orchestrator.process_quartet") as mock_process:
            # Setup process_quartet mock
            async def mock_process_quartet(sid, quartet):
                await asyncio.sleep(0.05)
                return ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=True,
                    duration_ms=50.0,
                )

            mock_process.side_effect = mock_process_quartet

            # Execute sequential processing
            start_time = time.time()
            results = await _process_quartets_sequential(session_id, sample_quartets)
            duration = time.time() - start_time

            # Verify all quartets were processed
            assert len(results) == 10
            assert all(r.success for r in results)

            # Verify results are in correct order
            for i, result in enumerate(results, start=1):
                assert result.sequence_number == i

            # Verify sequential execution (should take ~0.5s for 10 * 0.05s)
            assert duration >= 0.4  # Should be close to sequential time

    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_same_results(
        self, sample_quartets: list[FileQuartet]
    ) -> None:
        """Test that parallel and sequential produce identical results."""
        session_id = uuid4()

        with patch("src.services.orchestrator.process_quartet") as mock_process, patch(
            "src.services.orchestrator.get_config"
        ) as mock_get_config:
            # Setup config mock
            mock_config = AsyncMock()
            mock_config.processing.quartet_concurrency = 5
            mock_get_config.return_value = mock_config

            # Setup consistent mock response
            async def mock_process_quartet(sid, quartet):
                return ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=True,
                    duration_ms=100.0,
                    schema_file_path=f"sessions/test/{quartet.sequence_number:03d}-page.schema.json",
                )

            mock_process.side_effect = mock_process_quartet

            # Execute both methods
            parallel_results = await _process_quartets_parallel(session_id, sample_quartets)

            # Reset mock for sequential test
            mock_process.reset_mock()
            mock_process.side_effect = mock_process_quartet

            sequential_results = await _process_quartets_sequential(session_id, sample_quartets)

            # Verify same number of results
            assert len(parallel_results) == len(sequential_results)

            # Verify results are identical (same order, same content)
            for parallel, sequential in zip(parallel_results, sequential_results):
                assert parallel.sequence_number == sequential.sequence_number
                assert parallel.success == sequential.success
                assert parallel.schema_file_path == sequential.schema_file_path


class TestProcessSession:
    """Tests for process_session with parallel processing."""

    @pytest.mark.asyncio
    async def test_process_session_parallel_enabled(
        self, sample_quartets: list[FileQuartet], test_storage_dir
    ) -> None:
        """Test process_session uses parallel processing when enabled."""
        session_id = uuid4()

        with patch(
            "src.services.orchestrator.discover_quartets"
        ) as mock_discover, patch(
            "src.services.orchestrator.process_quartet"
        ) as mock_process, patch(
            "src.services.orchestrator.get_config"
        ) as mock_get_config:
            # Setup config mock with parallel enabled
            mock_config = AsyncMock()
            mock_config.processing.enable_parallel_processing = True
            mock_config.processing.quartet_concurrency = 5
            mock_get_config.return_value = mock_config

            # Setup mocks
            mock_discover.return_value = sample_quartets

            async def mock_process_quartet(sid, quartet):
                return ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=True,
                    duration_ms=100.0,
                    ai_metrics=AIMetrics(
                        model="anthropic/claude-sonnet-4.5",
                        prompt_tokens=2000,
                        completion_tokens=800,
                        total_tokens=2800,
                        latency_ms=100.0,
                    ),
                )

            mock_process.side_effect = mock_process_quartet

            # Execute process_session
            result = await process_session(session_id)

            # Verify result
            assert isinstance(result, SessionProcessingResult)
            assert result.quartets_processed == 10
            assert result.success_count == 10
            assert result.failure_count == 0
            assert result.total_tokens == 28000  # 10 * 2800

    @pytest.mark.asyncio
    async def test_process_session_parallel_disabled(
        self, sample_quartets: list[FileQuartet], test_storage_dir
    ) -> None:
        """Test process_session uses sequential processing when disabled."""
        session_id = uuid4()

        with patch(
            "src.services.orchestrator.discover_quartets"
        ) as mock_discover, patch(
            "src.services.orchestrator.process_quartet"
        ) as mock_process, patch(
            "src.services.orchestrator.get_config"
        ) as mock_get_config:
            # Setup config mock with parallel disabled
            mock_config = AsyncMock()
            mock_config.processing.enable_parallel_processing = False
            mock_get_config.return_value = mock_config

            # Setup mocks
            mock_discover.return_value = sample_quartets

            async def mock_process_quartet(sid, quartet):
                return ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=True,
                    duration_ms=100.0,
                )

            mock_process.side_effect = mock_process_quartet

            # Execute process_session
            result = await process_session(session_id)

            # Verify result
            assert isinstance(result, SessionProcessingResult)
            assert result.quartets_processed == 10
            assert result.success_count == 10

    @pytest.mark.asyncio
    async def test_process_session_handles_failures(
        self, sample_quartets: list[FileQuartet], test_storage_dir
    ) -> None:
        """Test process_session correctly handles mixed success/failure results."""
        session_id = uuid4()

        with patch(
            "src.services.orchestrator.discover_quartets"
        ) as mock_discover, patch(
            "src.services.orchestrator.process_quartet"
        ) as mock_process, patch(
            "src.services.orchestrator.get_config"
        ) as mock_get_config:
            # Setup config mock
            mock_config = AsyncMock()
            mock_config.processing.enable_parallel_processing = True
            mock_config.processing.quartet_concurrency = 5
            mock_get_config.return_value = mock_config

            # Setup mocks
            mock_discover.return_value = sample_quartets

            # Make every other quartet fail
            async def mock_process_quartet(sid, quartet):
                success = quartet.sequence_number % 2 == 1
                return ProcessingResult(
                    session_id=sid,
                    sequence_number=quartet.sequence_number,
                    operation="quartet_processing",
                    success=success,
                    duration_ms=100.0,
                    error_type=None if success else "TestError",
                    error_message=None if success else "Test failure",
                    ai_metrics=AIMetrics(
                        model="anthropic/claude-sonnet-4.5",
                        prompt_tokens=2000,
                        completion_tokens=800,
                        total_tokens=2800,
                        latency_ms=100.0,
                    )
                    if success
                    else None,
                )

            mock_process.side_effect = mock_process_quartet

            # Execute process_session
            result = await process_session(session_id)

            # Verify result counts
            assert result.quartets_processed == 10
            assert result.success_count == 5  # Odd numbers succeed
            assert result.failure_count == 5  # Even numbers fail
            assert result.success_rate() == 50.0  # Returns percentage, not decimal
            assert result.total_tokens == 14000  # 5 successes * 2800
