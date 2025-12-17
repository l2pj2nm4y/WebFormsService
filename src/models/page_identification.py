"""PageIdentification data model for page matching and deduplication.

AI-generated metadata containing page-level characteristics extracted from
screenshot analysis for identifying and matching duplicate pages.

All properties use TimestampedValue wrappers for temporal tracking,
enabling merge decisions based on recency and property-level updates.
"""

from pydantic import BaseModel, ConfigDict, Field

from src.models.timestamped import TimestampedValue


class PageIdentification(BaseModel):
    """Page-level identification characteristics for similarity-based matching.

    Generated from screenshot analysis to identify and characterize webpages.
    Used for matching duplicate pages captured at different form-filling stages.

    All scalar properties use TimestampedValue wrappers for property-level
    temporal tracking. List properties contain TimestampedValue items,
    enabling timestamp-based merging where only newer values overwrite.
    """

    url: TimestampedValue[str] | None = Field(
        default=None,
        description="Page URL if available, with timestamp"
    )
    page_headings: list[TimestampedValue[str]] = Field(
        default_factory=list,
        description="Main page-level headings or titles visible at the top (not form section headings), each with timestamp",
    )
    form_headings: list[TimestampedValue[str]] = Field(
        default_factory=list,
        description="Form section headings and subsection titles, each with timestamp",
    )
    visual_sections: list[TimestampedValue[str]] = Field(
        default_factory=list,
        description="Visual layout sections (header, left_navigation_panel, main_content_form, right_sidebar, footer, etc.), each with timestamp",
    )
    navigation_buttons: list[TimestampedValue[str]] = Field(
        default_factory=list,
        description="Navigation button labels (Previous, Next, Save, Submit, etc.), each with timestamp",
    )
    progress_indicator: TimestampedValue[str] | None = Field(
        default=None,
        description="Progress indicator if visible (e.g., '15%', 'Step 2 of 5'), with timestamp",
    )
    page_number: TimestampedValue[str] | None = Field(
        default=None,
        description="Page number if visible (e.g., '3/20', 'Page 3 of 20'), with timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": {
                    "timestamp": "2025-11-17T22:09:03.542Z",
                    "value": "https://immi.homeaffairs.gov.au/citizenship/descent/page-3",
                },
                "page_headings": [
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Online Lodgement"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Australian citizenship by descent"},
                ],
                "form_headings": [
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Applicant"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Applicant details"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Passport details"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Place of birth"},
                ],
                "visual_sections": [
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "header"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "left_navigation_panel"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "main_content_form"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "right_sidebar_related_links"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "footer_navigation"},
                ],
                "navigation_buttons": [
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Previous"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Save"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Print"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Go to my account"},
                    {"timestamp": "2025-11-17T22:09:03.542Z", "value": "Next"},
                ],
                "progress_indicator": {
                    "timestamp": "2025-11-17T22:09:03.542Z",
                    "value": "15%",
                },
                "page_number": {
                    "timestamp": "2025-11-17T22:09:03.542Z",
                    "value": "3/20",
                },
            }
        }
    )
