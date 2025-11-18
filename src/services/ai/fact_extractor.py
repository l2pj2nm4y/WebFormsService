"""AI-powered fact extraction from screenshots.

Extracts page identification characteristics using vision-capable AI models
for similarity-based page matching.
"""

import base64
import time
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ImageUrl
from pydantic_ai.models.openai import OpenAIChatModel

from src.lib.config import get_config
from src.lib.logging import get_logger, log_ai_operation
from src.models.fact import FactFile

logger = get_logger(__name__)

# System prompt for fact extraction - EXACT format as specified
FACT_EXTRACTION_SYSTEM_PROMPT = """<role>
You are an expert at analysing webpage screenshots to extract page identification facts and constructing JSON.
</role>

<objective>
Analyse the form screenshots provided in the user prompt and generate a comprehensive JSON data structure representing key identification facts that could be used for page matching. You'll be given screenshots and the page URL.
</objective>

<critical_requirements>
    <requirement priority="1">Only include information you can actually observe in the screenshot</requirement>
    <requirement priority="2">Follow the EXACT format specified</requirement>
</critical_requirements>

<analysis_scope>

<scratchpad>
Analyze the screenshot systematically:
- What are the most prominent headings or titles you can see?
- How is the page visually organized (sections/layout)?
- Is there any progress indication or page number?
- Are there any page navigation buttons (next, previous, submit, home, etc)?
</scratchpad>
</analysis_scope>

<example_format>
{
  "url": "abc.com",
  "scratchpad": "Looking at this screenshot, I can observe:\n\nProminent Headings/Titles:\n- \"Online Lodgement\" at the top right\n- \"Australian citizenship by descent\" in the left panel\n- \"Applicant\" section\n- \"Applicant details\"\n- \"Other names, dates of birth or gender\"\n- \"Passport details\"\n- \"National identity card\"\n- \"Other passports and documents for travel\"\n- \"Place of birth\"\n- \"Surrogacy\"\n- \"Adoption\"\n- \"Citizenship details\"\n- \"Chinese commercial code\"\n- \"Australian licences\"\n- \"Related Links\" in the right sidebar\n- \"Help and Support\" in the right sidebar\n\nVisual Organization:\n- Three-column layout with dark blue header, left navigation panel, main content area in the center, and sidebar on the right\n- The main content area contains a long form with multiple sections organized vertically\n- Progress indicator showing \"3/20\" near the top\n- Right sidebar has related links and help resources\n- Footer with navigation buttons and accessibility links\n- Australian Government Department of Home Affairs branding at the top\n\nForms and Interactive Elements:\n- This is a government citizenship application form\n- Text input fields for: Title (dropdown with \"Mr\" selected), Family name (Fleming), Given names (Robert Arthur), Town/City (Sydney), State/Province (New South Wales)\n- Dropdown menus for: Title, Country of birth (AUSTRIA)\n- Radio buttons for: Sex (Female/Male/Other with Male selected), Yes/No questions for passport, identity card, travel documents, Australia entry/departure, surrogacy, adoption, citizenship, Chinese commercial code, driver licence, firearms licence\n- Date picker field showing \"04 Mar 1979\"\n- Data table showing \"Other names\" with columns: Family name, Given names, Sex, Date of birth, Actions\n- Table contains two entries: Fleming/Rob/Male/4 Mar 1979 and Flemington/Roberta/Female/4 Mar 1979\n- \"Add\" button below the table\n- \"Edit\" and \"Delete\" links in the Actions column\n- Navigation buttons at bottom: \"Previous\", \"Save\", \"Print\", \"Go to my account\", \"Next\"\n- Information icons (i) next to various fields providing help\n\nLayout Pattern:\n- Three-column government form layout\n- Long-form questionnaire style\n- Progressive disclosure with sections\n- Transaction reference number displayed: \"EGP8ISOADN\"",
  "page_headings": [
    "Online Lodgement",
    "Australian citizenship by descent"
  ],
  "form_headings": [
    "Applicant",
    "Applicant details",
    "Other names, dates of birth or gender",
    "Passport details",
    "National identity card",
    "Other passports and documents for travel",
    "Place of birth",
    "Surrogacy",
    "Adoption",
    "Citizenship details",
    "Chinese commercial code",
    "Australian licences"
  ],
  "visual_sections": [
    "header",
    "left_navigation_panel",
    "main_content_form",
    "right_sidebar_related_links",
    "right_sidebar_help_support",
    "footer_navigation",
    "footer_links"
  ],
    "navigation_buttons": [
      "Previous",
      "Save",
      "Print",
      "Go to my account",
      "Next"
    ],
  "progress_indicator": "15%",
  "page_number": "3/20"
}
</example_format>

<output_rules>
    <format>Raw JSON structure only</format>
    <validation>Ensure valid JSON syntax that can be parsed</validation>
    <restrictions>
        <no_markdown>Do not include markdown code blocks or ```json``` formatting</no_markdown>
        <no_explanation>Do not include any explanatory text outside the JSON</no_explanation>
        <no_comments>Do not include JSON comments or additional notes</no_comments>
    </restrictions>
</output_rules>"""


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

            # Create vision message with image and URL
            # TODO: Extract actual URL from metadata when available
            page_url = "unknown"
            prompt_text = f"Analyze this webpage screenshot and extract the facts as specified. URL: {page_url}"

            # Log the request being sent (without base64 image data)
            logger.info(
                "ai_request_sending",
                session_id=session_id,
                sequence_number=sequence_number,
                prompt=prompt_text,
                image_type=image_type,
                image_size_bytes=len(screenshot_bytes),
                base64_size=len(screenshot_b64),
                system_prompt=FACT_EXTRACTION_SYSTEM_PROMPT[:200] + "...",
            )

            # Run AI agent with vision - pass text and ImageUrl in user_prompt list
            # This is the correct format for pydantic-ai vision support
            result = await self.agent.run(
                user_prompt=[
                    prompt_text,  # Text prompt first
                    ImageUrl(url=f"data:{image_type};base64,{screenshot_b64}")  # Image as ImageUrl object
                ]
            )

            # Extract the FactFile from the output (pydantic-ai 1.11.1 API)
            fact_file = result.output

            # Log the AI response
            logger.info(
                "ai_response_received",
                session_id=session_id,
                sequence_number=sequence_number,
                url=fact_file.url,
                page_headings=fact_file.page_headings,
                form_headings=fact_file.form_headings,
                visual_sections=fact_file.visual_sections,
                navigation_buttons=fact_file.navigation_buttons,
                progress_indicator=fact_file.progress_indicator,
                page_number=fact_file.page_number,
            )

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
                page_headings_count=len(fact_file.page_headings),
                form_headings_count=len(fact_file.form_headings),
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
