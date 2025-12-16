"""AI-powered prompt generation for form automation.

Generates form field definitions with bracketed notation format for filling instructions.
Uses LiteLLM with OpenRouter and LangFuse for observability.
"""

import base64
import json
import os
import time
from typing import Any

import litellm
from litellm import acompletion

from src.lib.config import get_config
from src.lib.logging import get_logger, log_ai_operation
from src.services.html.form_parser import FormField

logger = get_logger(__name__)

# Initialize LangFuse callbacks for LiteLLM
_langfuse_initialized = False


def _initialize_langfuse() -> None:
    """Initialize LangFuse callbacks for LiteLLM tracing."""
    global _langfuse_initialized
    if _langfuse_initialized:
        return

    config = get_config()
    if config.langfuse.enabled and config.langfuse.public_key:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", config.langfuse.public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", config.langfuse.secret_key)
        os.environ.setdefault("LANGFUSE_HOST", config.langfuse.host)
        logger.info("langfuse_tracing_enabled", host=config.langfuse.host)

    _langfuse_initialized = True


# System prompt for prompt generation - EXACT format as specified
PROMPT_GENERATION_SYSTEM_PROMPT = """<role>
You are an expert at analysing screenshots and constructing JSON.
</role>

<objective>
Analyse the form screenshot provided in the user prompt and generate a comprehensive JSON data structure representing all required input fields.
</objective>

<field_notation_guide>
    <overview>
        Fields in the schema contain bracketed instructions [...] that describe what values to extract and how to format them.
        Each bracketed instruction follows a structured pattern that you must interpret to correctly fill the JSON.
    </overview>

    <bracket_structure>
        <pattern>[Requirement: DataType - Description, Constraints, NullHandling]</pattern>
        <components>
            <requirement>First element indicates if field is mandatory:
                - Required: MUST have a value, cannot be null
                - Optional: MAY be null if not found in source
                - Conditional: Required only if specified conditions are met
                - System: Skip this field - it's auto-generated
                - Calculated: Skip this field - it's computed from other fields
            </requirement>
            <data_type>The type of value expected:
                - string: Text value (use quotes)
                - number: Numeric value (no quotes)
                - boolean: true or false (no quotes, lowercase)
                - date: YYYY-MM-DD format
                - datetime: ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
                - time: HH:MM or HH:MM:SS format
                - array: List of items (use [])
                - array of strings: List of text values
                - array of numbers: List of numeric values
                - array of objects: List of complex items
                - object: Nested structure (use {})
                - email: Valid email format
                - url: Valid URL with protocol
                - phone: Phone with country code
                - file: File upload reference
                - currency: Monetary amount
                - percentage: Percentage value
                - enum: One of specified values
            </data_type>
            <description>Explanation of what the field represents - use this to understand what to extract</description>
            <constraints>Any limitations or specific requirements for the value</constraints>
            <null_handling>Instructions for when data is not found</null_handling>
        </components>
    </bracket_structure>

    <common_patterns>
        <pattern>
            <notation>[Required: string - Full legal name]</notation>
            <meaning>Required text field for name input</meaning>
        </pattern>
        <pattern>
            <notation>[Optional: string - Middle name, null if none]</notation>
            <meaning>Optional text field, use null if not provided</meaning>
        </pattern>
        <pattern>
            <notation>[Required: string - One of: active|inactive|pending]</notation>
            <meaning>Required dropdown/select with specific options</meaning>
        </pattern>
        <pattern>
            <notation>[Required: number - Age in years, Between 0 and 150]</notation>
            <meaning>Required numeric field with range validation</meaning>
        </pattern>
        <pattern>
            <notation>[Required: boolean - Accept terms and conditions]</notation>
            <meaning>Required checkbox field</meaning>
        </pattern>
        <pattern>
            <notation>[Required: datetime - ISO 8601 format YYYY-MM-DDTHH:MM:SSZ]</notation>
            <meaning>Required date-time picker field</meaning>
        </pattern>
        <pattern>
            <notation>[Optional: array of strings - Selected options, empty array if none]</notation>
            <meaning>Multi-select field, use [] if nothing selected</meaning>
        </pattern>
        <pattern>
            <notation>[Required: file - Upload document, PDF or DOC format]</notation>
            <meaning>Required file upload field with format restrictions</meaning>
        </pattern>
    </common_patterns>

    <enumeration_handling>
        <instruction>When you see "One of:" followed by options separated by pipes (|):</instruction>
        <steps>
            <step>This indicates a dropdown/select or radio button group</step>
            <step>List ONLY the provided options</step>
            <step>Match the case exactly as shown</step>
            <step>These are the only valid values for the field</step>
        </steps>
        <example>
            <notation>[Required: string - One of: small|medium|large|x-large]</notation>
            <form_element>Dropdown menu with size options</form_element>
        </example>
    </enumeration_handling>

    <constraint_notation>
        <constraint type="range">
            <notation>Between X and Y</notation>
            <meaning>Numeric input with min/max validation</meaning>
        </constraint>
        <constraint type="length">
            <notation>Maximum N characters</notation>
            <meaning>Text input with character limit</meaning>
        </constraint>
        <constraint type="format">
            <notation>Format: pattern</notation>
            <meaning>Input must match specific pattern (e.g., phone, SSN)</meaning>
        </constraint>
        <constraint type="file_types">
            <notation>Allowed: PDF, JPG, PNG</notation>
            <meaning>File upload with accepted formats</meaning>
        </constraint>
        <constraint type="array_size">
            <notation>Minimum X items, maximum Y items</notation>
            <meaning>Multi-select or repeating fields with count limits</meaning>
        </constraint>
    </constraint_notation>

    <form_element_mapping>
        <mapping>
            <form_element>Text input field</form_element>
            <notation>[Required/Optional: string - description]</notation>
        </mapping>
        <mapping>
            <form_element>Number input field</form_element>
            <notation>[Required/Optional: number - description, constraints]</notation>
        </mapping>
        <mapping>
            <form_element>Email input field</form_element>
            <notation>[Required/Optional: email - description]</notation>
        </mapping>
        <mapping>
            <form_element>Phone input field</form_element>
            <notation>[Required/Optional: phone - description, format]</notation>
        </mapping>
        <mapping>
            <form_element>Date picker</form_element>
            <notation>[Required/Optional: date - YYYY-MM-DD format]</notation>
        </mapping>
        <mapping>
            <form_element>Dropdown/Select menu</form_element>
            <notation>[Required/Optional: string - One of: option1|option2|option3]</notation>
        </mapping>
        <mapping>
            <form_element>Radio button group</form_element>
            <notation>[Required/Optional: string - One of: option1|option2|option3]</notation>
        </mapping>
        <mapping>
            <form_element>Single checkbox</form_element>
            <notation>[Required/Optional: boolean - description]</notation>
        </mapping>
        <mapping>
            <form_element>Multiple checkboxes</form_element>
            <notation>[Required/Optional: array of strings - description]</notation>
        </mapping>
        <mapping>
            <form_element>Textarea</form_element>
            <notation>[Required/Optional: string - description, Maximum X characters]</notation>
        </mapping>
        <mapping>
            <form_element>File upload</form_element>
            <notation>[Required/Optional: file - description, Allowed: formats]</notation>
        </mapping>
        <mapping>
            <form_element>Multi-select list</form_element>
            <notation>[Required/Optional: array of strings - description]</notation>
        </mapping>
    </form_element_mapping>
</field_notation_guide>

<critical_requirements>
    <requirement priority="1">ONLY include fields where users can INPUT or MODIFY data - exclude all navigation controls, buttons, links, and display-only elements</requirement>
    <requirement priority="2">Follow the EXACT format specified with proper metadata annotations using underscores</requirement>
    <requirement priority="3">Use [Required: type - description] and [Optional: type - description] notation for all fields according to the field_notation_guide</requirement>
    <requirement priority="4">Include all _description, _required, _sensitive metadata fields where applicable</requirement>
    <requirement priority="5">Create logical nested structures for related fields and use arrays for repeating elements</requirement>
    <requirement priority="6">For array structures include: _arrayDescription, _minItems, _maxItems, _allowEmpty, _uniqueField where appropriate</requirement>
    <requirement priority="7">Identify all editable form elements and map them to proper data types using the form_element_mapping guide</requirement>
    <requirement priority="8">Add validation rules and constraints visible on the form using the constraint_notation patterns</requirement>
    <requirement priority="9">Exclude form controls such as buttons and links</requirement>
    <requirement priority="10">Exclude any metadata or system data fields that might be visible</requirement>
    <requirement priority="11">Include a top level JSON property for the page_identifier as provided in the user prompt</requirement>
</critical_requirements>

<analysis_scope>
    <identify>
        <editable_only>
            <element>text input fields (text, email, password, etc.)</element>
            <element>dropdown/select menus</element>
            <element>checkboxes (user can toggle)</element>
            <element>radio buttons (user can select)</element>
            <element>text areas</element>
            <element>file upload fields</element>
            <element>date/time pickers</element>
            <element>number/range inputs</element>
            <element>multi-select lists</element>
        </editable_only>

        <explicitly_exclude>
            <element>buttons (submit, cancel, navigation)</element>
            <element>links and anchors</element>
            <element>static labels and headers</element>
            <element>disabled/readonly fields</element>
            <element>display-only elements</element>
            <element>progress bars</element>
            <element>informational text</element>
        </explicitly_exclude>
    </identify>

    <determine>
        <field_types>Map each form element to appropriate type using field_notation_guide</field_types>
        <field_requirements>Identify required vs optional based on visual indicators (*, required labels, validation messages)</field_requirements>
        <field_groupings>Organise related fields into logical sections and objects</field_groupings>
        <array_detection>Identify repeating patterns that suggest array/list structures</array_detection>
        <validation_rules>Extract any visible constraints and express using constraint_notation</validation_rules>
        <field_naming>Use descriptive names matching visual labels on the form</field_naming>
    </determine>
</analysis_scope>

<example_format>
{
    "page_identifier": "[As provided in user prompt]",
    "FormData": {
        "_description": "Main form entity containing all user inputs",
        "_required": true,

        "PersonalInfo": {
            "_description": "User personal information section",
            "_required": true,
            "_sensitive": true,
            "FirstName": "[Required: string - User's legal first name, Maximum 50 characters]",
            "LastName": "[Required: string - User's legal surname, Maximum 50 characters]",
            "Email": "[Required: email - Valid email address for contact]",
            "Phone": "[Optional: phone - Phone number with country code, Format: +X-XXX-XXX-XXXX, null if not provided]",
            "DateOfBirth": "[Required: date - Birth date, YYYY-MM-DD format]",
            "Gender": "[Required: string - One of: male|female|non-binary|prefer-not-to-say]"
        },

        "Address": {
            "_description": "Mailing address information",
            "_required": false,
            "Street": "[Required: string - Street address line 1]",
            "Street2": "[Optional: string - Street address line 2, null if not needed]",
            "City": "[Required: string - City name]",
            "State": "[Required: string - State/Province, One of: CA|NY|TX|FL|...]",
            "PostalCode": "[Required: string - ZIP/Postal code, Format: XXXXX or XXXXX-XXXX]",
            "Country": "[Required: string - Country selection, One of: US|CA|UK|AU|...]"
        },

        "Preferences": [
            {
                "_arrayDescription": "User preference selections",
                "_minItems": 0,
                "_maxItems": 10,
                "_required": false,
                "_allowEmpty": true
            },
            {
                "PreferenceType": "[Required: string - One of: email|sms|push|mail]",
                "Enabled": "[Required: boolean - true if preference is enabled]",
                "Frequency": "[Optional: string - One of: immediate|daily|weekly|monthly, null if not applicable]"
            }
        ],

        "Documents": {
            "_description": "Required document uploads",
            "_required": true,
            "Resume": "[Required: file - Upload resume, Allowed: PDF, DOC, DOCX, Maximum 5MB]",
            "CoverLetter": "[Optional: file - Upload cover letter, Allowed: PDF, DOC, DOCX, Maximum 5MB, null if not provided]",
            "References": "[Optional: array of files - Upload reference letters, Maximum 3 files, Allowed: PDF]"
        },

        "Agreement": {
            "_description": "Terms and conditions acceptance",
            "_required": true,
            "AcceptTerms": "[Required: boolean - Accept terms and conditions]",
            "SubscribeNewsletter": "[Optional: boolean - Subscribe to email newsletter, Default to false if not checked]",
            "DataProcessingConsent": "[Required: boolean - Consent to data processing per privacy policy]"
        }
    }
}
</example_format>

<output_rules>
    <format>Raw JSON structure only</format>
    <validation>Ensure valid JSON syntax that can be parsed</validation>
    <field_notation>All field values must use the bracket notation from field_notation_guide</field_notation>
    <metadata_fields>Include all underscore-prefixed metadata fields for structure description</metadata_fields>
    <restrictions>
        <no_markdown>Do not include markdown code blocks or ```json``` formatting</no_markdown>
        <no_explanation>Do not include any explanatory text outside the JSON</no_explanation>
        <no_comments>Do not include JSON comments or additional notes</no_comments>
    </restrictions>
</output_rules>"""


def _extract_cache_stats(usage: Any) -> tuple[int, int]:
    """Extract cache statistics from LiteLLM usage object.

    Args:
        usage: LiteLLM usage object from response

    Returns:
        tuple[int, int]: (cache_read_tokens, cache_creation_tokens)
    """
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = 0

    # Get cached_tokens from prompt_tokens_details (LiteLLM standard location)
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details:
        if isinstance(prompt_details, dict):
            cache_read = prompt_details.get("cached_tokens", 0) or 0
        else:
            cache_read = getattr(prompt_details, "cached_tokens", 0) or 0

    # Fallback: check for cache_read_input_tokens direct attribute
    if not cache_read:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    return cache_read, cache_creation


class PromptGenerator:
    """AI-powered prompt generation service using LiteLLM."""

    def __init__(self) -> None:
        """Initialize prompt generator with configuration."""
        _initialize_langfuse()

        config = get_config()
        self.model_name = config.ai.prompt_model
        self.temperature = config.ai.temperature
        self.max_tokens = config.ai.max_tokens
        self.timeout = config.ai.timeout
        self.enable_cache = config.ai.enable_cache
        self.api_key = config.openrouter.api_key
        self.site_url = config.openrouter.site_url
        self.app_name = config.openrouter.app_name

        logger.info(
            "prompt_generator_initialized",
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            cache_enabled=self.enable_cache,
        )

    def _build_messages(
        self,
        screenshot_b64: str,
        image_type: str,
        prompt_text: str,
    ) -> list[dict[str, Any]]:
        """Build messages for LiteLLM completion call.

        Args:
            screenshot_b64: Base64-encoded screenshot
            image_type: MIME type of image (image/png or image/jpeg)
            prompt_text: User prompt text

        Returns:
            list[dict]: Messages for LiteLLM
        """
        # Build system message with cache control for Anthropic caching
        if self.enable_cache:
            system_message: dict[str, Any] = {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": PROMPT_GENERATION_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        else:
            system_message = {"role": "system", "content": PROMPT_GENERATION_SYSTEM_PROMPT}

        # Build user message with image
        user_message: dict[str, Any] = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_type};base64,{screenshot_b64}"},
                },
            ],
        }

        return [system_message, user_message]

    async def generate_prompt(
        self,
        screenshot_bytes: bytes,
        form_fields: list[FormField],
        sequence_number: int,
        session_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Generate prompt schema from screenshot and form analysis.

        Args:
            screenshot_bytes: Raw screenshot image bytes
            form_fields: Parsed HTML form fields
            sequence_number: Quartet sequence number
            session_id: Session identifier for logging

        Returns:
            tuple[dict, dict]: Generated prompt schema dictionary and metrics dictionary

        Raises:
            ValueError: If AI response is invalid or image format unsupported
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

            # Simple prompt with screenshot
            prompt_text = "Analyze the screenshot I've provided."

            logger.info(
                "prompt_generation_request",
                session_id=session_id,
                sequence_number=sequence_number,
                field_count=len(form_fields),
                image_type=image_type,
                image_size_bytes=len(screenshot_bytes),
            )

            # Build messages
            messages = self._build_messages(screenshot_b64, image_type, prompt_text)

            # Call LiteLLM with OpenRouter
            response = await acompletion(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=self.api_key,
                timeout=self.timeout,
                # LangFuse metadata for trace grouping
                metadata={
                    "operation": "prompt_generation",
                    "session_id": session_id,
                    "sequence_number": sequence_number,
                },
                # OpenRouter headers
                extra_headers={
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.app_name,
                },
                # OpenRouter requires usage.include=true to return cache statistics
                extra_body={
                    "usage": {"include": True},
                },
            )

            # Extract response text
            response_text = response.choices[0].message.content

            # Strip markdown code fences if present
            cleaned_text = response_text.strip() if response_text else ""
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            # Parse JSON
            prompt_data = json.loads(cleaned_text)

            # Extract metrics from response
            usage = response.usage
            cache_read, cache_creation = _extract_cache_stats(usage)

            latency_ms = (time.time() - start_time) * 1000
            metrics = {
                "model": self.model_name,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.prompt_tokens + usage.completion_tokens,
                "cache_read_tokens": cache_read,
                "cache_creation_tokens": cache_creation,
                "latency_ms": latency_ms,
                "cost_usd": None,
            }

            logger.info(
                "token_usage",
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cache_read=cache_read,
                cache_creation=cache_creation,
            )

            # Log operation
            log_ai_operation(
                logger,
                operation="prompt_generation",
                model=self.model_name,
                prompt_tokens=metrics["prompt_tokens"],
                completion_tokens=metrics["completion_tokens"],
                total_tokens=metrics["total_tokens"],
                latency_ms=latency_ms,
                prompt_preview=f"Generate prompt for {len(form_fields)} fields",
            )

            logger.info(
                "prompt_generation_complete",
                session_id=session_id,
                sequence_number=sequence_number,
                latency_ms=latency_ms,
            )

            return prompt_data, metrics

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            logger.error(
                "prompt_generation_failed",
                session_id=session_id,
                sequence_number=sequence_number,
                error=str(e),
                latency_ms=latency_ms,
                exc_info=True,
            )

            raise


# Global instance
_prompt_generator: PromptGenerator | None = None


def get_prompt_generator() -> PromptGenerator:
    """Get or create global prompt generator instance.

    Returns:
        PromptGenerator: Configured prompt generator
    """
    global _prompt_generator

    if _prompt_generator is None:
        _prompt_generator = PromptGenerator()

    return _prompt_generator


def reset_prompt_generator() -> None:
    """Reset global prompt generator (useful for testing)."""
    global _prompt_generator
    _prompt_generator = None
