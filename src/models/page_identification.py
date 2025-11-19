"""PageIdentification data model for page matching and deduplication.

AI-generated metadata containing page-level characteristics extracted from
screenshot analysis for identifying and matching duplicate pages.
"""

from pydantic import BaseModel, ConfigDict, Field


class PageIdentification(BaseModel):
    """Page-level identification characteristics for similarity-based matching.

    Generated from screenshot analysis to identify and characterize webpages.
    Used for matching duplicate pages captured at different form-filling stages.
    """

    url: str | None = Field(
        default=None,
        description="Page URL if available"
    )
    page_headings: list[str] = Field(
        default_factory=list,
        description="Main page-level headings or titles visible at the top (not form section headings)",
    )
    form_headings: list[str] = Field(
        default_factory=list,
        description="Form section headings and subsection titles",
    )
    visual_sections: list[str] = Field(
        default_factory=list,
        description="Visual layout sections (header, left_navigation_panel, main_content_form, right_sidebar, footer, etc.)",
    )
    navigation_buttons: list[str] = Field(
        default_factory=list,
        description="Navigation button labels (Previous, Next, Save, Submit, etc.)",
    )
    progress_indicator: str | None = Field(
        default=None,
        description="Progress indicator if visible (e.g., '15%', 'Step 2 of 5')",
    )
    page_number: str | None = Field(
        default=None,
        description="Page number if visible (e.g., '3/20', 'Page 3 of 20')",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://immi.homeaffairs.gov.au/citizenship/descent/page-3",
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
