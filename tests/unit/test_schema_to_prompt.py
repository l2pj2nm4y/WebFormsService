"""Unit tests for FormSchema to PromptFile transformation.

Tests the transformation logic that converts AI-generated FormSchema into
PromptFile format for data extraction.
"""

import pytest

from src.models.page_identification import PageIdentification
from src.models.prompt import FormInfo, PromptFile, PromptSection
from src.models.schema import (
    FormField,
    FormFieldConstraint,
    FormSchema,
    FormSection,
    VisibilityRule,
)
from src.services.transformers.schema_to_prompt import (
    _field_to_bracket_notation,
    _process_section,
    formschema_to_promptfile,
)


class TestFieldToBracketNotation:
    """Tests for _field_to_bracket_notation function."""

    def test_required_field_basic(self) -> None:
        """Test conversion of basic required field."""
        field = FormField(
            name="firstName",
            type="string",
            description="Given name",
            required=True,
            constraints=[],
        )

        result = _field_to_bracket_notation(field)

        assert result == "[Required: string - Given name]"

    def test_optional_field_basic(self) -> None:
        """Test conversion of basic optional field."""
        field = FormField(
            name="middleName",
            type="string",
            description="Middle name",
            required=False,
            constraints=[],
        )

        result = _field_to_bracket_notation(field)

        assert result == "[Optional: string - Middle name]"

    def test_field_with_min_length_constraint(self) -> None:
        """Test field with minLength constraint."""
        field = FormField(
            name="password",
            type="string",
            description="Password",
            required=True,
            constraints=[
                FormFieldConstraint(type="minLength", value="8", message="Min 8 characters")
            ],
        )

        result = _field_to_bracket_notation(field)

        assert result == "[Required: string - Password, min 8 chars]"

    def test_field_with_max_length_constraint(self) -> None:
        """Test field with maxLength constraint."""
        field = FormField(
            name="zipCode",
            type="string",
            description="ZIP code",
            required=True,
            constraints=[
                FormFieldConstraint(type="maxLength", value="10", message="Max 10 characters")
            ],
        )

        result = _field_to_bracket_notation(field)

        assert result == "[Required: string - ZIP code, max 10 chars]"

    def test_field_with_enum_constraint(self) -> None:
        """Test field with enum constraint."""
        field = FormField(
            name="status",
            type="string",
            description="Marital status",
            required=True,
            constraints=[
                FormFieldConstraint(
                    type="enum",
                    value=["Single", "Married", "Divorced", "Widowed"],
                    message="Select status",
                )
            ],
        )

        result = _field_to_bracket_notation(field)

        assert result == "[Required: string - Marital status, One of: Single|Married|Divorced|Widowed]"

    def test_field_with_pattern_constraint(self) -> None:
        """Test field with pattern constraint."""
        field = FormField(
            name="email",
            type="email",
            description="Email address",
            required=True,
            constraints=[
                FormFieldConstraint(
                    type="pattern",
                    value=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                    message="Valid email",
                )
            ],
        )

        result = _field_to_bracket_notation(field)

        assert "pattern:" in result
        assert "Email address" in result

    def test_field_with_multiple_constraints(self) -> None:
        """Test field with multiple constraints."""
        field = FormField(
            name="age",
            type="number",
            description="Age in years",
            required=True,
            constraints=[
                FormFieldConstraint(type="min", value=18, message="Must be 18+"),
                FormFieldConstraint(type="max", value=120, message="Max 120"),
            ],
        )

        result = _field_to_bracket_notation(field)

        assert "min: 18" in result
        assert "max: 120" in result
        assert "Age in years" in result


class TestProcessSection:
    """Tests for _process_section function."""

    def test_simple_section(self) -> None:
        """Test conversion of simple section with fields."""
        section = FormSection(
            name="PersonalInfo",
            description="Personal information",
            fields=[
                FormField(
                    name="firstName",
                    type="string",
                    description="Given name",
                    required=True,
                    constraints=[],
                ),
                FormField(
                    name="lastName",
                    type="string",
                    description="Family name",
                    required=True,
                    constraints=[],
                ),
            ],
            subsections=[],
        )

        result = _process_section(section)

        assert isinstance(result, PromptSection)
        assert result.name == "PersonalInfo"
        assert result.description == "Personal information"
        assert result.path == "PersonalInfo"
        assert "firstName" in result.fields
        assert "lastName" in result.fields
        assert result.fields["firstName"] == "[Required: string - Given name]"

    def test_nested_sections(self) -> None:
        """Test conversion of section with subsections."""
        section = FormSection(
            name="Applicant",
            description="Applicant information",
            fields=[
                FormField(
                    name="applicantId",
                    type="string",
                    description="ID number",
                    required=True,
                    constraints=[],
                )
            ],
            subsections=[
                FormSection(
                    name="Contact",
                    description="Contact details",
                    fields=[
                        FormField(
                            name="email",
                            type="email",
                            description="Email address",
                            required=True,
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
        )

        result = _process_section(section)

        assert result.name == "Applicant"
        assert len(result.subsections) == 1
        assert result.subsections[0].name == "Contact"
        assert result.subsections[0].path == "Applicant.Contact"
        assert "email" in result.subsections[0].fields

    def test_section_with_visibility_rule(self) -> None:
        """Test section with visibility rule."""
        section = FormSection(
            name="SpouseInfo",
            description="Spouse information",
            fields=[
                FormField(
                    name="spouseName",
                    type="string",
                    description="Spouse name",
                    required=True,
                    constraints=[],
                )
            ],
            subsections=[],
            visibility_rules=[
                VisibilityRule(
                    operator="equals",
                    field="marital_status",
                    value="married",
                )
            ],
        )

        result = _process_section(section)

        assert result.visible_when == 'marital_status == "married"'


class TestFormSchemaToPromptFile:
    """Tests for formschema_to_promptfile function."""

    def test_basic_transformation(self) -> None:
        """Test basic FormSchema to PromptFile transformation."""
        schema = FormSchema(
            page_identifier="page-1",
            form_name="Application Form",
            description="Test application",
            sections=[
                FormSection(
                    name="PersonalInfo",
                    description="Personal information",
                    fields=[
                        FormField(
                            name="firstName",
                            type="string",
                            description="Given name",
                            required=True,
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
            page_identification=PageIdentification(
                url="https://example.com/form",
                page_headings=["Application"],
                form_headings=["Personal Info"],
            ),
        )

        result = formschema_to_promptfile(schema)

        assert isinstance(result, PromptFile)
        assert result.schema_version == "1.0"
        assert isinstance(result.form_info, FormInfo)
        assert result.form_info.form_name == "Application Form"
        assert result.form_info.url == "https://example.com/form"
        assert len(result.sections) == 1
        assert result.sections[0].name == "PersonalInfo"

    def test_complex_transformation_with_nesting(self) -> None:
        """Test complex FormSchema with nested sections."""
        schema = FormSchema(
            page_identifier="page-1",
            form_name="Citizenship Application",
            description="Application for citizenship",
            sections=[
                FormSection(
                    name="Applicant",
                    description="Applicant information",
                    fields=[
                        FormField(
                            name="applicantId",
                            type="string",
                            description="ID",
                            required=True,
                            constraints=[],
                        )
                    ],
                    subsections=[
                        FormSection(
                            name="PersonalInfo",
                            description="Personal details",
                            fields=[
                                FormField(
                                    name="firstName",
                                    type="string",
                                    description="Given name",
                                    required=True,
                                    constraints=[],
                                ),
                                FormField(
                                    name="lastName",
                                    type="string",
                                    description="Family name",
                                    required=True,
                                    constraints=[],
                                ),
                            ],
                            subsections=[],
                        )
                    ],
                )
            ],
            page_identification=PageIdentification(),
        )

        result = formschema_to_promptfile(schema)

        assert len(result.sections) == 1
        assert len(result.sections[0].subsections) == 1
        assert result.sections[0].subsections[0].name == "PersonalInfo"
        assert result.sections[0].subsections[0].path == "Applicant.PersonalInfo"

    def test_transformation_preserves_all_context(self) -> None:
        """Test that transformation preserves all context from PageIdentification."""
        schema = FormSchema(
            page_identifier="page-3",
            form_name="Form N-400",
            description="Naturalization application",
            sections=[
                FormSection(
                    name="Test",
                    description="Test section",
                    fields=[
                        FormField(
                            name="test",
                            type="string",
                            description="Test field",
                            required=True,
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
            page_identification=PageIdentification(
                url="https://uscis.gov/n-400",
                page_headings=["Application for Naturalization"],
                form_headings=["Part 3", "Personal Information"],
                visual_sections=["header", "main_content", "footer"],
                navigation_buttons=["Previous", "Next", "Save"],
                progress_indicator="15%",
                page_number="3/20",
            ),
        )

        result = formschema_to_promptfile(schema)

        assert result.form_info.url == "https://uscis.gov/n-400"
        assert result.form_info.page_headings == ["Application for Naturalization"]
        assert result.form_info.form_headings == ["Part 3", "Personal Information"]
        assert result.form_info.visual_sections == ["header", "main_content", "footer"]
        assert result.form_info.navigation_buttons == ["Previous", "Next", "Save"]
        assert result.form_info.progress_indicator == "15%"
        assert result.form_info.page_number == "3/20"

    def test_helper_methods_work_after_transformation(self) -> None:
        """Test that PromptFile helper methods work correctly after transformation."""
        schema = FormSchema(
            page_identifier="page-1",
            form_name="Test Form",
            description="Test",
            sections=[
                FormSection(
                    name="Section1",
                    description="Section 1",
                    fields=[
                        FormField(
                            name="field1",
                            type="string",
                            description="Field 1",
                            required=True,
                            constraints=[],
                        ),
                        FormField(
                            name="field2",
                            type="number",
                            description="Field 2",
                            required=False,
                            constraints=[],
                        ),
                    ],
                    subsections=[],
                )
            ],
            page_identification=PageIdentification(),
        )

        result = formschema_to_promptfile(schema)

        # Test get_required_fields
        required = result.get_required_fields()
        assert "Section1.field1" in required
        assert "Section1.field2" not in required

        # Test get_field_type
        assert result.get_field_type("Section1.field1") == "string"
        assert result.get_field_type("Section1.field2") == "number"

        # Test get_all_sections
        all_sections = result.get_all_sections()
        assert len(all_sections) == 1
        assert all_sections[0].name == "Section1"

        # Test get_section_by_path
        section = result.get_section_by_path("Section1")
        assert section is not None
        assert section.name == "Section1"
