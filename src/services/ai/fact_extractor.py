"""AI-powered fact extraction from screenshots.

Extracts page identification characteristics using vision-capable AI models
for similarity-based page matching.
"""

import base64
import time
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from src.lib.config import get_config
from src.lib.logging import get_logger, log_ai_operation
from src.models.fact import FactFile

logger = get_logger(__name__)

# System prompt for fact extraction
FACT_EXTRACTION_SYSTEM_PROMPT = """You are an expert at analyzing webpage screenshots to extract identification facts for page matching.

Your task is to analyze the provided screenshot and extract structured information that uniquely identifies this page.

Focus on:
1. **Visual Headings**: Main headings, titles, or labels visible at the top or prominent positions (up to 5)
2. **Visual Sections**: Describe the layout sections you can see (header, main content, sidebar, footer, navigation, etc.)
3. **Form Elements**: Identify if there are forms, what types of input fields are visible, and button labels
4. **Layout Pattern**: Describe the overall page layout and structure
5. **Content Keywords**: 3-5 key terms that describe the page's purpose or content

Prioritize stable visual elements over dynamic content. Focus on what makes this page recognizable across different form-filling sessions.

Output must be valid JSON matching the FactFile schema."""


class FactExtractor:
    """AI-powered fact extraction service."""

    def __init__(self) -> None:
        """Initialize fact extractor with configuration."""
        config = get_config()

        # Create Pydantic AI agent with OpenRouter provider
        model = OpenAIChatModel(
            config.ai.fact_model,
            provider="openrouter",
        )

        self.agent: Agent[None, FactFile] = Agent(
            model=model,
            output_type=FactFile,
            system_prompt=FACT_EXTRACTION_SYSTEM_PROMPT,
        )

        self.model_name = config.ai.fact_model

    async def extract_facts(
        self, screenshot_bytes: bytes, sequence_number: int, session_id: str
    ) -> tuple[FactFile, dict[str, Any]]:
        """Extract facts from screenshot using AI vision.

        Args:
            screenshot_bytes: Screenshot image bytes
            sequence_number: Triplet sequence number
            session_id: Session identifier for logging

        Returns:
            tuple[FactFile, dict]: Fact file and metrics dictionary

        Raises:
            ValueError: If AI response is invalid
            Exception: If AI operation fails
        """
        start_time = time.time()

        try:
            # Encode screenshot to base64
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # Determine image type (PNG or JPEG)
            if screenshot_bytes.startswith(b"\x89PNG"):
                image_type = "image/png"
            elif screenshot_bytes.startswith(b"\xff\xd8\xff"):
                image_type = "image/jpeg"
            else:
                raise ValueError("Unsupported image format (expected PNG or JPEG)")

            # Create vision message
            prompt = "Analyze this webpage screenshot and extract the facts as specified."

            # Run AI agent with vision
            result = await self.agent.run(
                prompt,
                message_history=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image_type};base64,{screenshot_b64}"
                                },
                            },
                        ],
                    }
                ],
            )

            fact_file = result.data

            # Calculate metrics
            latency_ms = (time.time() - start_time) * 1000

            # Extract token usage from result
            usage = result.usage()
            metrics = {
                "model": self.model_name,
                "prompt_tokens": usage.request_tokens or 0,
                "completion_tokens": usage.response_tokens or 0,
                "total_tokens": usage.total_tokens or 0,
                "latency_ms": latency_ms,
                "cost_usd": None,  # OpenRouter doesn't always provide cost
            }

            # Log operation
            log_ai_operation(
                logger,
                operation="fact_extraction",
                model=self.model_name,
                prompt_tokens=metrics["prompt_tokens"],
                completion_tokens=metrics["completion_tokens"],
                total_tokens=metrics["total_tokens"],
                latency_ms=latency_ms,
                prompt_preview=f"Screenshot analysis for sequence {sequence_number}",
            )

            logger.info(
                "fact_extraction_complete",
                session_id=session_id,
                sequence_number=sequence_number,
                visual_headings_count=len(fact_file.visual_headings),
                has_forms=fact_file.form_elements.has_forms,
                latency_ms=latency_ms,
            )

            return fact_file, metrics

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            logger.error(
                "fact_extraction_failed",
                session_id=session_id,
                sequence_number=sequence_number,
                error=str(e),
                latency_ms=latency_ms,
                exc_info=True,
            )

            raise


# Global instance
_fact_extractor: FactExtractor | None = None


def get_fact_extractor() -> FactExtractor:
    """Get or create global fact extractor instance.

    Returns:
        FactExtractor: Configured fact extractor
    """
    global _fact_extractor

    if _fact_extractor is None:
        _fact_extractor = FactExtractor()

    return _fact_extractor


def reset_fact_extractor() -> None:
    """Reset global fact extractor (useful for testing)."""
    global _fact_extractor
    _fact_extractor = None
