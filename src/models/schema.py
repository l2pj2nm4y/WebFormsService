"""
Form schema models for representing web form structure and fields.

These models capture the complete structure of a web form including:
- Field types and constraints
- Section organization
- Table/array configurations
- Validation rules
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisibilityRule(BaseModel):
    """Single rule that controls field or section visibility."""

    field: str = Field(..., description="Name of the field this condition depends on")
    operator: str = Field(
        ...,
        description="Comparison operator (equals, notEquals, contains, greaterThan, lessThan, etc.)",
    )
    value: Any = Field(..., description="Value to compare against")


class FormFieldConstraint(BaseModel):
    """Validation constraint for a form field."""

    type: str = Field(
        ...,
        description="Constraint type (maxLength, minLength, pattern, enum, min, max, etc.)",
    )
    value: Any = Field(..., description="Constraint value")
    message: str | None = Field(
        default=None, description="Error message for constraint violation"
    )


class ArrayConfig(BaseModel):
    """Configuration for array/multi-value fields."""

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
    """Configuration for a single column in a table input."""

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
    """Validation rules for table rows."""

    unique_fields: list[str] = Field(
        default_factory=list, description="Fields that must be unique across rows"
    )
    required_fields: list[str] = Field(
        default_factory=list, description="Fields required in each row"
    )


class TableConfig(BaseModel):
    """Configuration for table/grid input fields."""

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
    """Complete specification for a single form field."""

    name: str = Field(..., description="Field identifier/name")
    type: str = Field(
        ...,
        description="Field data type (string, number, boolean, date, datetime, time, email, phone, url, file, currency, percentage, array, object)",
    )
    required: bool = Field(default=False, description="Whether field is required")
    description: str = Field(
        ..., description="What information the user needs to provide"
    )
    label: str | None = Field(default=None, description="Display label for the field")
    placeholder: str | None = Field(
        default=None, description="Placeholder text shown in the field"
    )
    default_value: Any | None = Field(
        default=None, description="Default value for the field"
    )
    constraints: list[FormFieldConstraint] = Field(
        default_factory=list, description="Validation constraints"
    )
    options: list[str] | None = Field(
        default=None, description="Available options for dropdown/radio fields"
    )
    sensitive: bool = Field(
        default=False,
        description="Whether field contains sensitive data (SSN, password, etc.)",
    )
    input_format: str | None = Field(
        default=None, description="Input format (e.g., 'table' for grid inputs)"
    )
    table_config: TableConfig | None = Field(
        default=None, description="Configuration for table/grid inputs"
    )
    array_config: ArrayConfig | None = Field(
        default=None, description="Configuration for array/multi-value fields"
    )
    visibility_rules: list[VisibilityRule] = Field(
        default_factory=list,
        description="Rules that control when this field is visible/enabled (all rules must be satisfied)",
    )


class FormSection(BaseModel):
    """Section of a form containing related fields."""

    name: str = Field(..., description="Section identifier/name")
    description: str = Field(
        ..., description="Purpose of this information group and how it will be used"
    )
    required: bool = Field(
        default=False, description="Whether all fields in section are required"
    )
    fields: list[FormField] = Field(
        default_factory=list, description="Fields contained in this section"
    )
    subsections: list[FormSection] = Field(
        default_factory=list, description="Nested subsections"
    )
    visibility_rules: list[VisibilityRule] = Field(
        default_factory=list,
        description="Rules that control when this section is visible/enabled (all rules must be satisfied)",
    )


class FormSchema(BaseModel):
    """Complete schema representation of a web form."""

    page_identifier: str = Field(
        ..., description="Unique identifier for the form page"
    )
    form_name: str = Field(..., description="Name of the form")
    description: str = Field(
        ..., description="Description of the form and its purpose"
    )
    sections: list[FormSection] = Field(
        ..., description="Form sections containing fields"
    )
