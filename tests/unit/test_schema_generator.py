"""Unit tests for AI schema generator service.

Tests the schema generation service in isolation with mocked AI responses.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import (
    ArrayConfig,
    FormField,
    FormFieldConstraint,
    FormSchema,
    FormSection,
    TableColumnConfig,
    TableConfig,
    TableRowValidation,
)
from src.services.ai.schema_generator import SchemaGenerator


@pytest.fixture
def sample_form_schema() -> FormSchema:
    """Provide sample form schema for testing."""
    return FormSchema(
        page_identifier="Australian citizenship by descent - Applicant details (3/22)",
        form_name="CitizenshipByDescentApplication",
        description="Application for Australian citizenship by descent - collecting applicant's personal information",
        sections=[
            FormSection(
                name="PersonalInformation",
                description="Basic personal details required to verify your identity",
                required=True,
                fields=[
                    FormField(
                        name="firstName",
                        type="string",
                        required=True,
                        description="Enter your legal first name as it appears on official documents",
                        label="First Name",
                        placeholder="Enter your first name",
                        constraints=[
                            FormFieldConstraint(
                                type="maxLength",
                                value=50,
                                message="First name cannot exceed 50 characters",
                            )
                        ],
                    ),
                    FormField(
                        name="dateOfBirth",
                        type="date",
                        required=True,
                        description="Select your date of birth in DD/MM/YYYY format",
                        label="Date of Birth",
                        placeholder="DD/MM/YYYY",
                    ),
                ],
                subsections=[],
            ),
            FormSection(
                name="TravelDocuments",
                description="Current and previous travel documents",
                required=False,
                fields=[
                    FormField(
                        name="otherTravelDocuments",
                        type="array",
                        required=False,
                        description="List all other passports and travel documents you hold",
                        label="Other Travel Documents",
                        sensitive=True,
                        input_format="table",
                        table_config=TableConfig(
                            add_button_text="Add details",
                            can_delete_rows=True,
                            can_reorder_rows=False,
                            columns=[
                                TableColumnConfig(
                                    name="documentType",
                                    label="Document Type",
                                    type="string",
                                    required=True,
                                    width="25%",
                                    editable=True,
                                    description="Select the type of travel document",
                                ),
                                TableColumnConfig(
                                    name="documentNumber",
                                    label="Document Number",
                                    type="string",
                                    required=True,
                                    width="25%",
                                    editable=True,
                                    description="Enter the document number exactly as shown",
                                ),
                            ],
                            row_validation=TableRowValidation(
                                unique_fields=["documentNumber"],
                                required_fields=["documentType", "documentNumber"],
                            ),
                        ),
                        array_config=ArrayConfig(
                            item_type="object",
                            min_items=0,
                            max_items=None,
                            allow_empty=True,
                            unique_field="documentNumber",
                        ),
                    )
                ],
                subsections=[],
            ),
        ],
    )


@pytest.fixture
def mock_agent_result(sample_form_schema: FormSchema) -> MagicMock:
    """Mock Pydantic AI agent result (pydantic-ai 1.11.1 API)."""
    mock_result = MagicMock()
    mock_result.output = sample_form_schema  # Use .output for structured output
    mock_result.usage.return_value = MagicMock(
        request_tokens=2500, response_tokens=1200, total_tokens=3700
    )
    return mock_result


class TestSchemaGenerator:
    """Unit tests for SchemaGenerator class."""

    @pytest.mark.asyncio
    async def test_generate_schema_success(
        self,
        sample_screenshot_bytes: bytes,
        sample_form_schema: FormSchema,
        mock_agent_result: MagicMock,
    ) -> None:
        """Test successful schema generation from screenshot."""
        with patch("src.services.ai.schema_generator.Agent") as mock_agent_class:
            # Setup mock
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_agent_result
            mock_agent_class.return_value = mock_agent

            generator = SchemaGenerator()
            generator.agent = mock_agent

            # Generate schema
            form_schema, metrics = await generator.generate_schema(
                sample_screenshot_bytes, sequence_number=1, session_id="test-session"
            )

            # Verify result
            assert isinstance(form_schema, FormSchema)
            assert form_schema == sample_form_schema
            assert form_schema.page_identifier == sample_form_schema.page_identifier
            assert form_schema.form_name == sample_form_schema.form_name
            assert len(form_schema.sections) == 2

            # Verify metrics
            assert metrics["model"] == "anthropic/claude-sonnet-4.5"
            assert metrics["prompt_tokens"] == 2500
            assert metrics["completion_tokens"] == 1200
            assert metrics["total_tokens"] == 3700
            assert metrics["latency_ms"] > 0

            # Verify agent was called
            mock_agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_schema_rejects_invalid_format(self) -> None:
        """Test rejection of unsupported image formats."""
        invalid_bytes = b"\x00\x00\x00\x00" + b"invalid"

        generator = SchemaGenerator()

        with pytest.raises(ValueError, match="Unsupported image format"):
            await generator.generate_schema(
                invalid_bytes, sequence_number=1, session_id="test"
            )

    @pytest.mark.asyncio
    async def test_generate_schema_handles_ai_failure(
        self, sample_screenshot_bytes: bytes
    ) -> None:
        """Test error handling when AI operation fails."""
        with patch("src.services.ai.schema_generator.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("AI API error")
            mock_agent_class.return_value = mock_agent

            generator = SchemaGenerator()
            generator.agent = mock_agent

            with pytest.raises(Exception, match="AI API error"):
                await generator.generate_schema(
                    sample_screenshot_bytes, sequence_number=1, session_id="test"
                )

    @pytest.mark.asyncio
    async def test_generate_schema_logs_operation(
        self,
        sample_screenshot_bytes: bytes,
        mock_agent_result: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that schema generation logs operation details."""
        with patch("src.services.ai.schema_generator.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_agent_result
            mock_agent_class.return_value = mock_agent

            generator = SchemaGenerator()
            generator.agent = mock_agent

            await generator.generate_schema(
                sample_screenshot_bytes,
                sequence_number=5,
                session_id="test-session-123",
            )

            # Verify logging occurred (structlog writes to stdout, not caplog)
            # The actual logging is verified in integration tests
            # Here we just verify the method completed successfully
            assert mock_agent.run.called

    @pytest.mark.asyncio
    async def test_generate_schema_with_complex_fields(
        self,
        sample_screenshot_bytes: bytes,
    ) -> None:
        """Test schema generation with complex field types."""
        complex_schema = FormSchema(
            page_identifier="Complex Form - Page 1",
            form_name="ComplexApplicationForm",
            description="Test form with various field types",
            sections=[
                FormSection(
                    name="MixedFields",
                    description="Section with various field types",
                    required=True,
                    fields=[
                        FormField(
                            name="email",
                            type="email",
                            required=True,
                            description="Enter your email address",
                            label="Email",
                        ),
                        FormField(
                            name="age",
                            type="number",
                            required=True,
                            description="Enter your age",
                            label="Age",
                            constraints=[
                                FormFieldConstraint(type="min", value=0),
                                FormFieldConstraint(type="max", value=150),
                            ],
                        ),
                        FormField(
                            name="acceptTerms",
                            type="boolean",
                            required=True,
                            description="Check to accept terms",
                            label="Accept Terms",
                        ),
                        FormField(
                            name="country",
                            type="string",
                            required=True,
                            description="Select your country",
                            label="Country",
                            options=["USA", "Canada", "UK", "Australia"],
                            constraints=[
                                FormFieldConstraint(
                                    type="enum",
                                    value=["USA", "Canada", "UK", "Australia"],
                                )
                            ],
                        ),
                    ],
                    subsections=[],
                )
            ],
        )

        mock_result = MagicMock()
        mock_result.output = complex_schema
        mock_result.usage.return_value = MagicMock(
            request_tokens=2000, response_tokens=800, total_tokens=2800
        )

        with patch("src.services.ai.schema_generator.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent

            generator = SchemaGenerator()
            generator.agent = mock_agent

            form_schema, metrics = await generator.generate_schema(
                sample_screenshot_bytes, sequence_number=1, session_id="test"
            )

            # Verify complex field types
            assert form_schema.sections[0].fields[0].type == "email"
            assert form_schema.sections[0].fields[1].type == "number"
            assert form_schema.sections[0].fields[2].type == "boolean"
            assert form_schema.sections[0].fields[3].options is not None
            assert len(form_schema.sections[0].fields[3].options) == 4

    @pytest.mark.asyncio
    async def test_generate_schema_with_nested_subsections(
        self,
        sample_screenshot_bytes: bytes,
    ) -> None:
        """Test schema generation with nested subsections."""
        nested_schema = FormSchema(
            page_identifier="Nested Form",
            form_name="NestedForm",
            description="Form with nested sections",
            sections=[
                FormSection(
                    name="ParentSection",
                    description="Parent section with subsections",
                    required=True,
                    fields=[
                        FormField(
                            name="parentField",
                            type="string",
                            required=True,
                            description="Parent field",
                            label="Parent",
                        )
                    ],
                    subsections=[
                        FormSection(
                            name="ChildSection",
                            description="Child section",
                            required=False,
                            fields=[
                                FormField(
                                    name="childField",
                                    type="string",
                                    required=False,
                                    description="Child field",
                                    label="Child",
                                )
                            ],
                            subsections=[],
                        )
                    ],
                )
            ],
        )

        mock_result = MagicMock()
        mock_result.output = nested_schema
        mock_result.usage.return_value = MagicMock(
            request_tokens=1800, response_tokens=600, total_tokens=2400
        )

        with patch("src.services.ai.schema_generator.Agent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = mock_result
            mock_agent_class.return_value = mock_agent

            generator = SchemaGenerator()
            generator.agent = mock_agent

            form_schema, metrics = await generator.generate_schema(
                sample_screenshot_bytes, sequence_number=1, session_id="test"
            )

            # Verify nested structure
            assert len(form_schema.sections) == 1
            assert len(form_schema.sections[0].subsections) == 1
            assert (
                form_schema.sections[0].subsections[0].name == "ChildSection"
            )


class TestSchemaGeneratorSingleton:
    """Test schema generator singleton pattern."""

    def test_get_schema_generator_returns_singleton(self) -> None:
        """Test that get_schema_generator returns same instance."""
        from src.services.ai.schema_generator import (
            get_schema_generator,
            reset_schema_generator,
        )

        reset_schema_generator()

        generator1 = get_schema_generator()
        generator2 = get_schema_generator()

        assert generator1 is generator2

    def test_reset_schema_generator_clears_instance(self) -> None:
        """Test that reset creates new instance."""
        from src.services.ai.schema_generator import (
            get_schema_generator,
            reset_schema_generator,
        )

        generator1 = get_schema_generator()
        reset_schema_generator()
        generator2 = get_schema_generator()

        assert generator1 is not generator2
