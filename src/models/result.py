"""ProcessingResult data model for operation outcomes.

Models for tracking success/failure status, metrics, and context for processing operations.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIMetrics(BaseModel):
    """AI operation metrics for token usage and cost tracking."""

    model: str = Field(..., description="Model identifier used")
    prompt_tokens: int = Field(..., description="Number of prompt tokens", ge=0)
    completion_tokens: int = Field(..., description="Number of completion tokens", ge=0)
    total_tokens: int = Field(..., description="Total tokens used", ge=0)
    latency_ms: float = Field(..., description="Operation latency in milliseconds", ge=0)
    cost_usd: float | None = Field(default=None, description="Cost in USD if available")


class ProcessingResult(BaseModel):
    """Outcome of processing a file triplet or session.

    Tracks success/failure status, generated output paths, metrics, and error information
    for observability and debugging.
    """

    session_id: UUID = Field(..., description="Session identifier")
    sequence_number: int | None = Field(
        default=None, description="Triplet sequence number (if applicable)", ge=1, le=999
    )
    operation: Literal[
        "fact_extraction",
        "prompt_generation",
        "triplet_processing",
        "session_merge",
        "master_merge",
        "combined_generation",
    ] = Field(..., description="Operation performed")
    success: bool = Field(..., description="Whether operation succeeded")
    duration_ms: float = Field(..., description="Operation duration in milliseconds", ge=0)
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When operation completed"
    )

    # Output file paths (if successful)
    fact_file_path: str | None = Field(
        default=None, description="Generated fact file path"
    )
    prompt_file_path: str | None = Field(
        default=None, description="Generated prompt file path"
    )
    combined_prompt_path: str | None = Field(
        default=None, description="Combined prompt file path"
    )

    # Metrics
    ai_metrics: AIMetrics | None = Field(
        default=None, description="AI operation metrics if applicable"
    )

    # Error information (if failed)
    error_type: str | None = Field(default=None, description="Error type if failed")
    error_message: str | None = Field(default=None, description="Error message if failed")
    error_context: dict[str, Any] = Field(
        default_factory=dict, description="Error context for debugging"
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional operation metadata"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "sequence_number": 1,
                "operation": "fact_extraction",
                "success": True,
                "duration_ms": 2341.5,
                "timestamp": "2025-01-06T12:34:56Z",
                "fact_file_path": "sessions/550e8400-e29b-41d4-a716-446655440000/001-page.facts.json",
                "ai_metrics": {
                    "model": "anthropic/claude-3.5-haiku",
                    "prompt_tokens": 1523,
                    "completion_tokens": 421,
                    "total_tokens": 1944,
                    "latency_ms": 2100.3,
                    "cost_usd": 0.0019,
                },
                "metadata": {
                    "screenshot_size_bytes": 2458912,
                    "visual_headings_count": 3,
                },
            }
        }
    )


class SessionProcessingResult(BaseModel):
    """Aggregate result of processing an entire session.

    Summarizes all triplet processing results with statistics and outcomes.
    """

    session_id: UUID = Field(..., description="Session identifier")
    triplets_processed: int = Field(..., description="Number of triplets processed", ge=0)
    success_count: int = Field(
        ..., description="Number of successful operations", ge=0
    )
    failure_count: int = Field(..., description="Number of failed operations", ge=0)
    total_duration_ms: float = Field(
        ..., description="Total processing duration in milliseconds", ge=0
    )
    total_tokens: int = Field(..., description="Total AI tokens used", ge=0)
    total_cost_usd: float | None = Field(
        default=None, description="Total cost in USD if available"
    )
    unique_pages: int = Field(
        ..., description="Number of unique pages identified", ge=0
    )
    pages_added_to_master: int = Field(
        ..., description="Number of new pages added to master", ge=0
    )
    combined_prompt_path: str | None = Field(
        default=None, description="Path to generated combined prompt"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When session processing completed"
    )
    triplet_results: list[ProcessingResult] = Field(
        default_factory=list, description="Individual triplet processing results"
    )

    def success_rate(self) -> float:
        """Calculate success rate percentage.

        Returns:
            float: Success rate (0-100)
        """
        if self.triplets_processed == 0:
            return 0.0
        return (self.success_count / self.triplets_processed) * 100

    def average_duration_ms(self) -> float:
        """Calculate average processing duration per triplet.

        Returns:
            float: Average duration in milliseconds
        """
        if self.triplets_processed == 0:
            return 0.0
        return self.total_duration_ms / self.triplets_processed

    def average_tokens_per_triplet(self) -> float:
        """Calculate average tokens used per triplet.

        Returns:
            float: Average tokens per triplet
        """
        if self.triplets_processed == 0:
            return 0.0
        return self.total_tokens / self.triplets_processed
