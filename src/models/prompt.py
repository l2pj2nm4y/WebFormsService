"""PromptFile data model for form automation.

AI-generated JSON schema containing comprehensive form field definitions with
bracketed notation format for form filling automation.
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


class PromptFile(BaseModel):
    """Form field definitions with bracketed notation for automation.

    Generated from screenshot analysis to describe all editable fields, their types,
    validation rules, and metadata. Uses bracketed notation format:
    [Required/Optional: type - description, constraints]
    """

    schema_version: str = Field(
        default="1.0", description="Schema version for compatibility"
    )
    fields: dict[str, Any] = Field(
        ...,
        description="Field definitions with bracketed notation and nested structures",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Form-level metadata and configuration"
    )

    @field_validator("fields")
    @classmethod
    def validate_fields_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate fields dictionary is not empty."""
        if not v:
            raise ValueError("fields dictionary cannot be empty")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema_version": "1.0",
                "fields": {
                    "applicantName": {
                        "firstName": "[Required: string - Given name as shown on birth certificate]",
                        "middleName": "[Optional: string - Middle name or initial]",
                        "lastName": "[Required: string - Family name as shown on birth certificate]",
                    },
                    "dateOfBirth": "[Required: date - Date of birth in MM/DD/YYYY format]",
                    "email": "[Required: email - Email address for correspondence]",
                    "phoneNumber": "[Required: phone - Contact phone number with area code]",
                    "citizenship": "[Required: string - One of: US Citizen|Permanent Resident|Other]",
                    "documents": {
                        "_arrayDescription": "Upload supporting documents",
                        "_minItems": 1,
                        "_maxItems": 5,
                        "items": "[Required: file - Upload document, Allowed: PDF, DOC, DOCX]",
                    },
                },
                "metadata": {
                    "formTitle": "Application for Naturalization - N-400",
                    "pageNumber": "1 of 20",
                    "websiteId": "uscis.gov",
                },
            }
        }
    )

    def get_required_fields(self) -> list[str]:
        """Extract list of required field paths.

        Returns:
            list[str]: Dot-notation paths to required fields
        """
        required = []

        def extract_required(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    if isinstance(value, str) and value.startswith("[Required:"):
                        required.append(current_path)
                    elif isinstance(value, dict):
                        extract_required(value, current_path)

        extract_required(self.fields)
        return required

    def get_field_type(self, field_path: str) -> str | None:
        """Get field type from bracketed notation.

        Args:
            field_path: Dot-notation path to field

        Returns:
            str | None: Field type if found, None otherwise
        """
        parts = field_path.split(".")
        current = self.fields

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        # Extract type from bracketed notation
        if isinstance(current, str) and "[" in current:
            # Format: [Required/Optional: type - description]
            bracket_content = current.split("[")[1].split("]")[0]
            type_part = bracket_content.split(":")[1].split("-")[0].strip()
            return type_part

        return None
