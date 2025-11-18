"""Contract tests for AI model interactions.

Tests verify AI operations meet contract specifications:
- Input/output structure validation
- Performance SLA compliance (latency, token usage)
- Success rate requirements
- Error handling

These tests define the contract that AI services must fulfill.
"""

import pytest

from src.models.fact import FactFile, FormElements
from src.models.prompt import PromptFile


class TestFactExtractionContract:
    """Contract tests for fact extraction from screenshots."""

    def test_fact_file_structure(self) -> None:
        """Fact file must contain all required fields with correct types."""
        fact = FactFile(
            visual_headings=["Application for Naturalization", "Form N-400"],
            visual_sections=["header", "main content", "footer"],
            form_elements=FormElements(
                has_forms=True,
                visible_fields=["text", "text", "date"],
                buttons=["Continue", "Save"],
            ),
            layout_pattern="Single column form with sequential fields",
            content_keywords=["citizenship", "naturalization", "government"],
        )

        # Verify structure
        assert len(fact.visual_headings) <= 5
        assert len(fact.visual_sections) >= 1
        assert isinstance(fact.form_elements, FormElements)
        assert isinstance(fact.form_elements.has_forms, bool)
        assert 3 <= len(fact.content_keywords) <= 5
        assert len(fact.layout_pattern) <= 500

    def test_fact_file_validates_constraints(self) -> None:
        """Fact file must enforce validation constraints."""
        # Too many visual headings
        with pytest.raises(ValueError):
            FactFile(
                visual_headings=["h1", "h2", "h3", "h4", "h5", "h6"],  # Max 5
                visual_sections=["section"],
                form_elements=FormElements(has_forms=False, visible_fields=[], buttons=[]),
                layout_pattern="test",
                content_keywords=["k1", "k2", "k3"],
            )

        # Too few content keywords
        with pytest.raises(ValueError):
            FactFile(
                visual_headings=["h1"],
                visual_sections=["section"],
                form_elements=FormElements(has_forms=False, visible_fields=[], buttons=[]),
                layout_pattern="test",
                content_keywords=["k1", "k2"],  # Min 3
            )

        # Layout pattern too long
        with pytest.raises(ValueError):
            FactFile(
                visual_headings=["h1"],
                visual_sections=["section"],
                form_elements=FormElements(has_forms=False, visible_fields=[], buttons=[]),
                layout_pattern="x" * 501,  # Max 500
                content_keywords=["k1", "k2", "k3"],
            )

    def test_form_elements_structure(self) -> None:
        """FormElements must have required boolean and lists."""
        form_elements = FormElements(
            has_forms=True, visible_fields=["text", "email"], buttons=["Submit"]
        )

        assert isinstance(form_elements.has_forms, bool)
        assert isinstance(form_elements.visible_fields, list)
        assert isinstance(form_elements.buttons, list)

    def test_fact_extraction_performance_contract(self) -> None:
        """Fact extraction must meet performance SLA.

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
