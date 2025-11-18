"""FactFile data model for page identification.

AI-generated JSON containing page identification characteristics extracted from
screenshot analysis.
"""

from pydantic import BaseModel, ConfigDict, Field


class FactFile(BaseModel):
    """Page identification characteristics for AI similarity-based matching.

    Generated from screenshot analysis to identify and characterize webpages.
    Used for matching duplicate pages captured at different form-filling stages.
    """

    url: str = Field(..., description="Page URL")
    scratchpad: str = Field(
        ...,
        description="Systematic analysis of the screenshot covering: prominent headings/titles, visual organization (sections/layout), progress indication or page number, and page navigation buttons",
    )
    page_headings: list[str] = Field(
        ...,
        description="Main page-level headings or titles visible at the top (not form section headings)",
    )
    form_headings: list[str] = Field(
        default_factory=list,
        description="Form section headings and subsection titles",
    )
    visual_sections: list[str] = Field(
        ...,
        description="Visual layout sections (header, left_navigation_panel, main_content_form, right_sidebar, footer, etc.)",
    )
    navigation_buttons: list[str] = Field(
        default_factory=list,
        description="Navigation button labels (Previous, Next, Save, Submit, etc.)",
    )
    progress_indicator: str | None = Field(
        None,
        description="Progress indicator if visible (e.g., '15%', 'Step 2 of 5')",
    )
    page_number: str | None = Field(
        None,
        description="Page number if visible (e.g., '3/20', 'Page 3 of 20')",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "abc.com",
                "scratchpad": "Looking at this screenshot, I can observe:\n\nProminent Headings/Titles:\n- \"Online Lodgement\" at the top right\n- \"Australian citizenship by descent\" in the left panel\n- \"Applicant\" section\n\nVisual Organization:\n- Three-column layout with dark blue header\n- Progress indicator showing \"3/20\" near the top\n- Navigation buttons at bottom: Previous, Save, Print, Next\n\nForms and Interactive Elements:\n- Text input fields for personal details\n- Radio buttons for gender selection\n- Date picker showing \"04 Mar 1979\"",
                "page_headings": [
                    "Online Lodgement",
                    "Australian citizenship by descent",
                ],
                "form_headings": [
                    "Applicant",
                    "Applicant details",
                    "Passport details",
                    "Place of birth",
                ],
                "visual_sections": [
                    "header",
                    "left_navigation_panel",
                    "main_content_form",
                    "right_sidebar_related_links",
                    "footer_navigation",
                ],
                "navigation_buttons": [
                    "Previous",
                    "Save",
                    "Print",
                    "Go to my account",
                    "Next",
                ],
                "progress_indicator": "15%",
                "page_number": "3/20",
            }
        }
    )
