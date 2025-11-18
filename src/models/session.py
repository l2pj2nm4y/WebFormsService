"""Session and FileTriplet data models.

These models represent browser extension recording sessions and their file triplets.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FileTriplet(BaseModel):
    """A set of three related files sharing a sequence number prefix.

    Represents one webpage snapshot during form-filling: screenshot (visual capture),
    HTML (page source), and metadata (browser context).
    """

    sequence_number: int = Field(..., description="Sequence number (1-999)", ge=1, le=999)
    screenshot_path: str = Field(..., description="Path to screenshot file (.png, .jpg)")
    html_path: str = Field(..., description="Path to HTML file (.html)")
    metadata_path: str = Field(..., description="Path to metadata file (.json)")
    fact_file_path: str | None = Field(
        default=None, description="Path to generated fact file (.facts.json)"
    )
    prompt_file_path: str | None = Field(
        default=None, description="Path to generated prompt file (.schema.json)"
    )

    @field_validator("screenshot_path", "html_path", "metadata_path")
    @classmethod
    def validate_paths(cls, v: str) -> str:
        """Validate file paths are non-empty."""
        if not v or not v.strip():
            raise ValueError("File path cannot be empty")
        return v


class FileQuartet(BaseModel):
    """A set of four related files sharing a sequence number prefix.

    Represents one webpage snapshot during form-filling: screenshot (visual capture),
    HTML (page source), metadata (browser context), and scraped facts (extracted data).
    """

    sequence_number: int = Field(..., description="Sequence number (1-999)", ge=1, le=999)
    screenshot_path: str = Field(..., description="Path to screenshot file (.png, .jpg)")
    html_path: str = Field(..., description="Path to HTML file (.html)")
    metadata_path: str = Field(..., description="Path to metadata file (.json)")
    scraped_facts_path: str = Field(
        ..., description="Path to scraped facts file (.facts.json)"
    )
    schema_file_path: str | None = Field(
        default=None, description="Path to generated schema file (.schema.json)"
    )

    @field_validator("screenshot_path", "html_path", "metadata_path", "scraped_facts_path")
    @classmethod
    def validate_paths(cls, v: str) -> str:
        """Validate file paths are non-empty."""
        if not v or not v.strip():
            raise ValueError("File path cannot be empty")
        return v


class Session(BaseModel):
    """Task-specific browser extension recording session.

    Represents a complete form-filling session (e.g., "citizenship form" or "work visa" task)
    containing multiple page captures organized as numbered file triplets.
    """

    session_id: UUID = Field(..., description="Unique session identifier (GUID)")
    task_type: str = Field(
        ...,
        description="Task description (e.g., 'citizenship_form', 'work_visa')",
        min_length=1,
        max_length=100,
    )
    website_id: str = Field(
        ...,
        description="Website identifier for master folder mapping (e.g., 'uscis.gov')",
        min_length=1,
        max_length=100,
    )
    upload_timestamp: datetime = Field(
        ..., description="When session was uploaded (for FIFO queue ordering)"
    )
    storage_path: str = Field(..., description="Storage path to session folder")
    triplets: list[FileTriplet] = Field(
        default_factory=list, description="List of file triplets in this session"
    )
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        default="pending", description="Processing status"
    )

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        """Validate task type is alphanumeric with underscores."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("task_type must be alphanumeric with underscores or hyphens")
        return v.lower()

    @field_validator("website_id")
    @classmethod
    def validate_website_id(cls, v: str) -> str:
        """Validate website ID format (basic domain validation)."""
        # Allow domain names, alphanumeric with dots and hyphens
        if not all(c.isalnum() or c in ".-" for c in v):
            raise ValueError("website_id must be a valid domain-like identifier")
        return v.lower()

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        """Validate storage path starts with sessions/."""
        if not v.startswith("sessions/"):
            raise ValueError("storage_path must start with 'sessions/'")
        return v

    def add_triplet(
        self,
        sequence_number: int,
        screenshot_path: str,
        html_path: str,
        metadata_path: str,
    ) -> FileTriplet:
        """Add a file triplet to the session.

        Args:
            sequence_number: Triplet sequence number
            screenshot_path: Path to screenshot file
            html_path: Path to HTML file
            metadata_path: Path to metadata file

        Returns:
            FileTriplet: The created triplet
        """
        triplet = FileTriplet(
            sequence_number=sequence_number,
            screenshot_path=screenshot_path,
            html_path=html_path,
            metadata_path=metadata_path,
        )
        self.triplets.append(triplet)
        return triplet

    def get_triplet(self, sequence_number: int) -> FileTriplet | None:
        """Get triplet by sequence number.

        Args:
            sequence_number: Sequence number to find

        Returns:
            FileTriplet | None: Triplet if found, None otherwise
        """
        for triplet in self.triplets:
            if triplet.sequence_number == sequence_number:
                return triplet
        return None

    def triplet_count(self) -> int:
        """Get number of triplets in session.

        Returns:
            int: Number of triplets
        """
        return len(self.triplets)
