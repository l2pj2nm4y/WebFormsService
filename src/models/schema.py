"""
Form schema models for representing web form structure and fields.

These models capture the complete structure of a web form including:
- Field types and constraints
- Section organization
- Table/array configurations
- Validation rules
- Page identification metadata

All scalar properties use TimestampedValue wrappers for temporal tracking,
enabling merge decisions based on recency and property-level expiration.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.models.page_identification import PageIdentification
from src.models.timestamped import LEGACY_TIMESTAMP, TimestampedValue


class VisibilityRule(BaseModel):
    """Single rule that controls field or section visibility.

    Includes timestamp for temporal tracking during merges.
    """

    timestamp: str = Field(
        default=LEGACY_TIMESTAMP,
        description="ISO 8601 timestamp when this rule was observed",
    )
    field: str = Field(..., description="Name of the field this condition depends on")
    operator: str = Field(
        ...,
        description="Comparison operator (equals, notEquals, contains, greaterThan, lessThan, etc.)",
    )
    value: Any = Field(..., description="Value to compare against")


class FormFieldConstraint(BaseModel):
    """Validation constraint for a form field.

    Includes timestamp for temporal tracking during merges.
    """

    timestamp: str = Field(
        default=LEGACY_TIMESTAMP,
        description="ISO 8601 timestamp when this constraint was observed",
    )
    type: str = Field(
        ...,
        description="Constraint type (maxLength, minLength, pattern, enum, min, max, etc.)",
    )
    value: Any = Field(..., description="Constraint value")
    message: str | None = Field(
        default=None, description="Error message for constraint violation"
    )


class ArrayConfig(BaseModel):
    """Configuration for array/multi-value fields.

    Includes timestamp for temporal tracking during merges.
    """

    timestamp: str = Field(
        default=LEGACY_TIMESTAMP,
        description="ISO 8601 timestamp when this config was observed",
    )
    item_type: str = Field(
        ..., description="Type of each array element (string, object, etc.)"
    )
    min_items: int | None = Field(
        default=None, description="Minimum number of items required"
    )
    max_items: int | None = Field(
        default=None, description="Maximum number of items allowed"
    )
    allow_empty: bool = Field(
        default=True, description="Whether empty array is valid"
    )
    unique_field: str | None = Field(
        default=None, description="Field name for uniqueness check in object items"
    )
    item_schema: dict[str, Any] | None = Field(
        default=None,
        description="Schema for object items when item_type is 'object'",
    )


class TableColumnConfig(BaseModel):
    """Configuration for a single column in a table input.

    Includes timestamp for temporal tracking during merges.
    """

    timestamp: str = Field(
        default=LEGACY_TIMESTAMP,
        description="ISO 8601 timestamp when this column config was observed",
    )
    name: str = Field(..., description="Column field name")
    label: str = Field(..., description="Column header text")
    type: str = Field(..., description="Column data type")
    required: bool = Field(default=False, description="Whether column is required")
    width: str | None = Field(
        default=None, description="Column width (percentage or pixels)"
    )
    editable: bool = Field(default=True, description="Whether column is editable")
    description: str = Field(
        ..., description="What the user needs to enter in this column"
    )
    constraints: list[FormFieldConstraint] = Field(
        default_factory=list, description="Validation constraints for this column"
    )


class TableRowValidation(BaseModel):
    """Validation rules for table rows.

    Includes timestamp for temporal tracking during merges.
    """

    timestamp: str = Field(
        default=LEGACY_TIMESTAMP,
        description="ISO 8601 timestamp when this validation was observed",
    )
    unique_fields: list[str] = Field(
        default_factory=list, description="Fields that must be unique across rows"
    )
    required_fields: list[str] = Field(
        default_factory=list, description="Fields required in each row"
    )


class TableConfig(BaseModel):
    """Configuration for table/grid input fields.

    Includes timestamp for temporal tracking during merges.
    """

    timestamp: str = Field(
        default=LEGACY_TIMESTAMP,
        description="ISO 8601 timestamp when this config was observed",
    )
    add_button_text: str = Field(
        default="Add row", description="Text for add row button"
    )
    can_delete_rows: bool = Field(
        default=True, description="Whether rows can be deleted"
    )
    can_reorder_rows: bool = Field(
        default=False, description="Whether rows can be reordered"
    )
    columns: list[TableColumnConfig] = Field(
        ..., description="Column definitions for the table"
    )
    row_validation: TableRowValidation | None = Field(
        default=None, description="Row-level validation rules"
    )


class FormField(BaseModel):
    """Complete specification for a single form field.

    All scalar properties use TimestampedValue wrappers for property-level
    temporal tracking. Object types (table_config, array_config) have
    timestamps embedded directly in their structure.
    """

    # Required fields - wrapped scalars
    name: TimestampedValue[str] = Field(
        ..., description="Field identifier/name with timestamp"
    )
    type: TimestampedValue[str] = Field(
        ...,
        description="Field data type (string, number, boolean, date, datetime, time, email, phone, url, file, currency, percentage, array, object) with timestamp",
    )
    description: TimestampedValue[str] = Field(
        ..., description="What information the user needs to provide, with timestamp"
    )

    # Optional scalars - wrapper is optional
    required: TimestampedValue[bool] | None = Field(
        default=None, description="Whether field is required, with timestamp"
    )
    label: TimestampedValue[str] | None = Field(
        default=None, description="Display label for the field, with timestamp"
    )
    placeholder: TimestampedValue[str] | None = Field(
        default=None, description="Placeholder text shown in the field, with timestamp"
    )
    default_value: TimestampedValue[Any] | None = Field(
        default=None, description="Default value for the field, with timestamp"
    )
    sensitive: TimestampedValue[bool] | None = Field(
        default=None,
        description="Whether field contains sensitive data (SSN, password, etc.), with timestamp",
    )
    input_format: TimestampedValue[str] | None = Field(
        default=None,
        description="Input format (e.g., 'table' for grid inputs), with timestamp",
    )

    # Lists - each item has timestamp embedded in object
    constraints: list[FormFieldConstraint] = Field(
        default_factory=list, description="Validation constraints, each with timestamp"
    )
    options: list[TimestampedValue[str]] | None = Field(
        default=None,
        description="Available options for dropdown/radio fields, each with timestamp",
    )
    visibility_rules: list[VisibilityRule] = Field(
        default_factory=list,
        description="Rules that control when this field is visible/enabled, each with timestamp",
    )

    # Object types - timestamp embedded in object
    table_config: TableConfig | None = Field(
        default=None, description="Configuration for table/grid inputs, with timestamp"
    )
    array_config: ArrayConfig | None = Field(
        default=None,
        description="Configuration for array/multi-value fields, with timestamp",
    )


class FormSection(BaseModel):
    """Section of a form containing related fields.

    Scalar properties use TimestampedValue wrappers for property-level
    temporal tracking.
    """

    # Required fields - wrapped scalars
    name: TimestampedValue[str] = Field(
        ..., description="Section identifier/name with timestamp"
    )
    description: TimestampedValue[str] = Field(
        ...,
        description="Purpose of this information group and how it will be used, with timestamp",
    )

    # Optional scalars - wrapper is optional
    required: TimestampedValue[bool] | None = Field(
        default=None,
        description="Whether all fields in section are required, with timestamp",
    )

    # Lists and nested structures
    fields: list[FormField] = Field(
        default_factory=list, description="Fields contained in this section"
    )
    subsections: list[FormSection] = Field(
        default_factory=list, description="Nested subsections"
    )
    visibility_rules: list[VisibilityRule] = Field(
        default_factory=list,
        description="Rules that control when this section is visible/enabled, each with timestamp",
    )


class FormSchema(BaseModel):
    """Complete schema representation of a web form.

    Top-level scalar properties use TimestampedValue wrappers for
    property-level temporal tracking.
    """

    # Required fields - wrapped scalars
    page_identifier: TimestampedValue[str] = Field(
        ..., description="Unique identifier for the form page, with timestamp"
    )
    form_name: TimestampedValue[str] = Field(
        ..., description="Name of the form, with timestamp"
    )
    description: TimestampedValue[str] = Field(
        ..., description="Description of the form and its purpose, with timestamp"
    )

    # Nested structures
    sections: list[FormSection] = Field(
        ..., description="Form sections containing fields"
    )
    page_identification: PageIdentification = Field(
        default_factory=PageIdentification,
        description="Page-level metadata for identification and matching",
    )
