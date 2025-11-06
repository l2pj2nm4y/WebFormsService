"""FactFile data model for page identification.

AI-generated JSON containing page identification characteristics extracted from
screenshot analysis.
"""

from pydantic import BaseModel, ConfigDict, Field


class FormElements(BaseModel):
    """Form element detection results from screenshot analysis."""

    has_forms: bool = Field(..., description="Whether page contains forms")
    visible_fields: list[str] = Field(
        default_factory=list, description="List of visible form field types detected"
    )
    buttons: list[str] = Field(
        default_factory=list, description="List of button labels detected"
    )


class FactFile(BaseModel):
    """Page identification characteristics for AI similarity-based matching.

    Generated from screenshot analysis to identify and characterize webpages.
    Used for matching duplicate pages captured at different form-filling stages.
    """

    visual_headings: list[str] = Field(
        ...,
        description="Main headings/titles visible on page (up to 5)",
        max_length=5,
    )
    visual_sections: list[str] = Field(
        ...,
        description="Visual layout sections (header, content, sidebar, footer, etc.)",
    )
    form_elements: FormElements = Field(
        ..., description="Form element detection results"
    )
    layout_pattern: str = Field(
        ...,
        description="Overall layout pattern description",
        min_length=1,
        max_length=500,
    )
    content_keywords: list[str] = Field(
        ...,
        description="3-5 key descriptive terms about page content/purpose",
        min_length=3,
        max_length=5,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "visual_headings": [
                    "Application for Naturalization",
                    "Form N-400",
                    "Part 1: Your Name",
                ],
                "visual_sections": [
                    "header with logo and form number",
                    "main content area with form fields",
                    "footer with page number",
                ],
                "form_elements": {
                    "has_forms": True,
                    "visible_fields": ["text", "text", "text", "date"],
                    "buttons": ["Continue", "Save for Later"],
                },
                "layout_pattern": "Single column form with header, sequential fields, and action buttons at bottom",
                "content_keywords": [
                    "citizenship",
                    "naturalization",
                    "personal information",
                    "government form",
                ],
            }
        }
    )
