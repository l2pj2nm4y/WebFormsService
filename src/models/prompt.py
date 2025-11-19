"""PromptFile data model for form automation.

AI-generated JSON schema containing comprehensive form field definitions with
bracketed notation format and hierarchical section structure for form filling automation.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FieldMetadata(BaseModel):
    """Metadata annotations for form fields."""

    description: str | None = Field(
        default=None, alias="_description", description="Human-readable field description"
    )
    required: bool = Field(
        default=False, alias="_required", description="Whether field is required"
    )
    sensitive: bool = Field(
        default=False, alias="_sensitive", description="Whether field contains sensitive data"
    )
    array_description: str | None = Field(
        default=None,
        alias="_arrayDescription",
        description="Description for array fields",
    )
    min_items: int | None = Field(
        default=None, alias="_minItems", description="Minimum items for arrays"
    )
    max_items: int | None = Field(
        default=None, alias="_maxItems", description="Maximum items for arrays"
    )
    constraints: str | None = Field(
        default=None, description="Additional validation constraints"
    )

    model_config = ConfigDict(populate_by_name=True)


class FormInfo(BaseModel):
    """Form-level context information for AI extraction."""

    form_name: str = Field(..., description="Name of the form")
    description: str = Field(..., description="Form description")
    page_identifier: str = Field(..., description="Unique page identifier")
    url: str | None = Field(default=None, description="Page URL")
    page_headings: list[str] = Field(
        default_factory=list, description="Main page headings"
    )
    form_headings: list[str] = Field(
        default_factory=list, description="Form section headings"
    )
    visual_sections: list[str] = Field(
        default_factory=list, description="Visual layout sections"
    )
    navigation_buttons: list[str] = Field(
        default_factory=list, description="Navigation buttons present"
    )
    progress_indicator: str | None = Field(
        default=None, description="Progress indicator (e.g., '3/20', '15%')"
    )
    page_number: str | None = Field(
        default=None, description="Page number indicator"
    )


class PromptSection(BaseModel):
    """Hierarchical section with fields in prompt format.

    Represents a section of the form with context, fields, and optional subsections.
    Supports repeating sections (arrays) and conditional visibility.
    """

    name: str = Field(..., description="Section name")
    description: str = Field(..., description="Section description for context")
    path: str = Field(..., description="Dot-notation path (e.g., 'Applicant.PersonalInfo')")

    fields: dict[str, str] = Field(
        default_factory=dict,
        description="Fields in bracketed notation format: field_name -> '[Required: type - description]'",
    )

    subsections: list["PromptSection"] = Field(
        default_factory=list, description="Nested subsections"
    )

    # Conditional visibility
    visible_when: str | None = Field(
        default=None,
        description="Condition for visibility (e.g., 'marital_status == \"married\"')",
    )


class PromptFile(BaseModel):
    """Enhanced form field definitions for AI-powered data extraction.

    Generated from FormSchema to provide comprehensive context for AI data extraction.
    Uses hierarchical section structure with bracketed notation for fields:
    [Required/Optional: type - description, constraints]

    This format provides:
    - Section hierarchy mirroring visual form structure
    - Section descriptions for field disambiguation
    - Conditional visibility rules
    - Array/table metadata for repeating data
    - Page context for better field identification
    """

    schema_version: str = Field(
        default="1.0", description="Schema version for compatibility"
    )

    form_info: FormInfo = Field(..., description="Form-level context and metadata")

    sections: list[PromptSection] = Field(
        ..., description="Hierarchical sections with fields in bracketed notation"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata and configuration"
    )

    @field_validator("sections")
    @classmethod
    def validate_sections_not_empty(cls, v: list[PromptSection]) -> list[PromptSection]:
        """Validate sections list is not empty."""
        if not v:
            raise ValueError("sections list cannot be empty")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema_version": "1.0",
                "form_info": {
                    "form_name": "Application for Naturalization - N-400",
                    "description": "U.S. Citizenship Application",
                    "page_identifier": "page-3-applicant-details",
                    "url": "https://uscis.gov/n-400",
                    "page_headings": ["Application for Naturalization", "Form N-400"],
                    "form_headings": ["Part 3", "Applicant Information"],
                    "page_number": "3/20",
                    "progress_indicator": "15%",
                },
                "sections": [
                    {
                        "name": "Applicant",
                        "description": "Information about the primary applicant",
                        "path": "Applicant",
                        "fields": {
                            "firstName": "[Required: string - Given name as shown on birth certificate]",
                            "middleName": "[Optional: string - Middle name or initial]",
                            "lastName": "[Required: string - Family name as shown on birth certificate]",
                            "dateOfBirth": "[Required: date - Date of birth in MM/DD/YYYY format]",
                        },
                        "subsections": [
                            {
                                "name": "Contact",
                                "description": "Contact information",
                                "path": "Applicant.Contact",
                                "fields": {
                                    "email": "[Required: email - Email address for correspondence]",
                                    "phoneNumber": "[Required: phone - Contact phone number with area code]",
                                },
                            }
                        ],
                    },
                    {
                        "name": "Employment History",
                        "description": "Record of employment in the last 5 years",
                        "path": "EmploymentHistory",
                        "is_array": True,
                        "is_table": True,
                        "min_items": 1,
                        "column_order": ["employer", "position", "startDate", "endDate"],
                        "fields": {
                            "employer": "[Required: string - Company or organization name]",
                            "position": "[Required: string - Job title or position]",
                            "startDate": "[Required: date - Employment start date]",
                            "endDate": "[Optional: date - Employment end date, leave blank if current]",
                        },
                    },
                ],
                "metadata": {
                    "generatedFrom": "schema",
                    "transformationDate": "2025-01-19T00:00:00Z",
                },
            }
        }
    )

    def get_required_fields(self) -> list[str]:
        """Extract list of required field paths from all sections.

        Returns:
            list[str]: Dot-notation paths to required fields
        """
        required = []

        def extract_from_section(section: PromptSection) -> None:
            # Check fields in this section
            for field_name, field_spec in section.fields.items():
                if isinstance(field_spec, str) and field_spec.startswith("[Required:"):
                    field_path = f"{section.path}.{field_name}"
                    required.append(field_path)

            # Recursively check subsections
            for subsection in section.subsections:
                extract_from_section(subsection)

        # Process all top-level sections
        for section in self.sections:
            extract_from_section(section)

        return required

    def get_field_type(self, field_path: str) -> str | None:
        """Get field type from bracketed notation by path.

        Args:
            field_path: Dot-notation path to field (e.g., 'Applicant.Contact.email')

        Returns:
            str | None: Field type if found, None otherwise
        """

        def find_field_in_section(section: PromptSection, remaining_path: list[str]) -> str | None:
            if not remaining_path:
                return None

            # If path matches this section and we have one element left, look in fields
            if len(remaining_path) == 1 and remaining_path[0] in section.fields:
                field_spec = section.fields[remaining_path[0]]
                if isinstance(field_spec, str) and "[" in field_spec:
                    # Format: [Required/Optional: type - description]
                    bracket_content = field_spec.split("[")[1].split("]")[0]
                    type_part = bracket_content.split(":")[1].split("-")[0].strip()
                    return type_part
                return None

            # Check subsections
            for subsection in section.subsections:
                # Check if subsection name matches next path element
                if remaining_path and subsection.name == remaining_path[0]:
                    result = find_field_in_section(subsection, remaining_path[1:])
                    if result:
                        return result

            return None

        # Split path and search sections
        parts = field_path.split(".")
        for section in self.sections:
            if section.name == parts[0]:
                result = find_field_in_section(section, parts[1:])
                if result:
                    return result

        return None

    def get_all_sections(self, include_subsections: bool = True) -> list[PromptSection]:
        """Get all sections, optionally including nested subsections.

        Args:
            include_subsections: Whether to include nested subsections

        Returns:
            list[PromptSection]: List of all sections
        """
        sections = []

        def collect_sections(section: PromptSection) -> None:
            sections.append(section)
            if include_subsections:
                for subsection in section.subsections:
                    collect_sections(subsection)

        for section in self.sections:
            collect_sections(section)

        return sections

    def get_section_by_path(self, path: str) -> PromptSection | None:
        """Get section by its path.

        Args:
            path: Dot-notation path (e.g., 'Applicant.Contact')

        Returns:
            PromptSection | None: Section if found, None otherwise
        """
        parts = path.split(".")

        def find_section(section: PromptSection, remaining_path: list[str]) -> PromptSection | None:
            if not remaining_path:
                return section

            if section.name == remaining_path[0]:
                if len(remaining_path) == 1:
                    return section
                # Search subsections
                for subsection in section.subsections:
                    result = find_section(subsection, remaining_path[1:])
                    if result:
                        return result

            return None

        for section in self.sections:
            result = find_section(section, parts)
            if result:
                return result

        return None
