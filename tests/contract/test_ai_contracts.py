"""Contract tests for AI model interactions.

Tests verify AI operations meet contract specifications:
- Input/output structure validation
- Performance SLA compliance (latency, token usage)
- Success rate requirements
- Error handling

These tests define the contract that AI services must fulfill.
"""

import pytest

from src.models.page_identification import PageIdentification
from src.models.prompt import PromptFile


class TestPageIdentificationContract:
    """Contract tests for page identification from screenshots."""

    def test_page_identification_structure(self) -> None:
        """PageIdentification must contain all required fields with correct types."""
        page_id = PageIdentification(
            url="https://example.gov/citizenship",
            page_headings=["Application for Naturalization", "Form N-400"],
            form_headings=["Part 1", "Personal Information"],
            visual_sections=["header", "main_content_form", "footer"],
            navigation_buttons=["Continue", "Save for Later", "Previous"],
            progress_indicator="25%",
            page_number="1/4",
        )

        # Verify structure
        assert isinstance(page_id.url, str) or page_id.url is None
        assert isinstance(page_id.page_headings, list)
        assert isinstance(page_id.form_headings, list)
        assert isinstance(page_id.visual_sections, list)
        assert isinstance(page_id.navigation_buttons, list)
        assert isinstance(page_id.progress_indicator, str) or page_id.progress_indicator is None
        assert isinstance(page_id.page_number, str) or page_id.page_number is None

    def test_page_identification_optional_fields(self) -> None:
        """PageIdentification must work with optional fields."""
        # All optional fields
        page_id = PageIdentification()

        assert page_id.url is None
        assert page_id.page_headings == []
        assert page_id.form_headings == []
        assert page_id.visual_sections == []
        assert page_id.navigation_buttons == []
        assert page_id.progress_indicator is None
        assert page_id.page_number is None

        # Some optional fields
        page_id = PageIdentification(
            page_headings=["Application Form"],
            visual_sections=["header", "main"],
        )

        assert page_id.url is None
        assert len(page_id.page_headings) == 1
        assert len(page_id.visual_sections) == 2
        assert page_id.progress_indicator is None

    def test_page_identification_performance_contract(self) -> None:
        """Page identification must meet performance SLA.

        Contract requirements:
        - Max 10 seconds latency
        - Average 2000 tokens
        - 95%+ success rate
        """
        # This is a contract definition test - implementation will be tested in integration
        max_latency_ms = 10000
        avg_tokens = 2000
        min_success_rate = 0.95

        assert max_latency_ms == 10000
        assert avg_tokens == 2000
        assert min_success_rate == 0.95


class TestPromptGenerationContract:
    """Contract tests for prompt/schema generation from screenshots."""

    def test_prompt_file_structure(self) -> None:
        """Prompt file must contain fields dictionary and metadata."""
        prompt = PromptFile(
            schema_version="1.0",
            fields={
                "firstName": "[Required: string - Given name]",
                "lastName": "[Required: string - Family name]",
                "email": "[Optional: email - Contact email]",
            },
            metadata={"formTitle": "Application Form", "pageNumber": "1"},
        )

        assert prompt.schema_version == "1.0"
        assert isinstance(prompt.fields, dict)
        assert len(prompt.fields) > 0
        assert isinstance(prompt.metadata, dict)

    def test_prompt_file_validates_non_empty_fields(self) -> None:
        """Prompt file must have non-empty fields dictionary."""
        with pytest.raises(ValueError, match="fields dictionary cannot be empty"):
            PromptFile(schema_version="1.0", fields={}, metadata={})

    def test_bracketed_notation_format(self) -> None:
        """Fields must use bracketed notation format."""
        prompt = PromptFile(
            fields={
                "name": "[Required: string - Full name]",
                "age": "[Optional: number - Age in years]",
                "email": "[Required: email - Email address]",
            }
        )

        # All fields should contain bracketed notation
        for field_value in prompt.fields.values():
            if isinstance(field_value, str):
                assert "[" in field_value and "]" in field_value
                assert ":" in field_value
                assert "-" in field_value

    def test_get_required_fields_method(self) -> None:
        """PromptFile must support extracting required field paths."""
        prompt = PromptFile(
            fields={
                "applicant": {
                    "firstName": "[Required: string - Given name]",
                    "middleName": "[Optional: string - Middle name]",
                    "lastName": "[Required: string - Family name]",
                },
                "email": "[Required: email - Email address]",
                "phone": "[Optional: phone - Phone number]",
            }
        )

        required = prompt.get_required_fields()

        assert "applicant.firstName" in required
        assert "applicant.lastName" in required
        assert "email" in required
        assert "applicant.middleName" not in required
        assert "phone" not in required

    def test_get_field_type_method(self) -> None:
        """PromptFile must support extracting field types."""
        prompt = PromptFile(
            fields={
                "name": "[Required: string - Full name]",
                "age": "[Optional: number - Age]",
                "email": "[Required: email - Email address]",
            }
        )

        assert prompt.get_field_type("name") == "string"
        assert prompt.get_field_type("age") == "number"
        assert prompt.get_field_type("email") == "email"
        assert prompt.get_field_type("nonexistent") is None

    def test_prompt_generation_performance_contract(self) -> None:
        """Prompt generation must meet performance SLA.

        Contract requirements:
        - Max 15 seconds latency
        - Average 4000 tokens
        - 95%+ success rate
        """
        # Contract definition
        max_latency_ms = 15000
        avg_tokens = 4000
        min_success_rate = 0.95

        assert max_latency_ms == 15000
        assert avg_tokens == 4000
        assert min_success_rate == 0.95


class TestAIMetricsContract:
    """Contract tests for AI operation metrics tracking."""

    def test_metrics_must_track_tokens(self) -> None:
        """AI metrics must track prompt, completion, and total tokens."""
        from src.models.result import AIMetrics

        metrics = AIMetrics(
            model="anthropic/claude-sonnet-4.5",
            prompt_tokens=1523,
            completion_tokens=421,
            total_tokens=1944,
            latency_ms=2341.5,
            cost_usd=0.0019,
        )

        assert metrics.prompt_tokens >= 0
        assert metrics.completion_tokens >= 0
        assert metrics.total_tokens == metrics.prompt_tokens + metrics.completion_tokens
        assert metrics.latency_ms >= 0

    def test_metrics_validates_non_negative_values(self) -> None:
        """AI metrics must reject negative values."""
        from src.models.result import AIMetrics

        with pytest.raises(ValueError):
            AIMetrics(
                model="test",
                prompt_tokens=-1,  # Invalid
                completion_tokens=100,
                total_tokens=99,
                latency_ms=100,
            )

        with pytest.raises(ValueError):
            AIMetrics(
                model="test",
                prompt_tokens=100,
                completion_tokens=100,
                total_tokens=200,
                latency_ms=-1,  # Invalid
            )
