"""MasterFolder and EmbeddingsIndex data models.

Models for website-specific master repositories that accumulate merged data across
multiple task-based sessions.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PageEmbedding(BaseModel):
    """Vector representation of a page's fact file for similarity search."""

    page_hash: str = Field(
        ..., description="Hash identifier for the page", min_length=1, max_length=64
    )
    embedding: list[float] = Field(
        ..., description="Vector embedding of fact file content"
    )
    fact_file_path: str = Field(..., description="Path to source fact file")
    prompt_file_path: str = Field(..., description="Path to merged prompt file")
    last_updated: datetime = Field(
        ..., description="When this embedding was last updated"
    )

    @field_validator("embedding")
    @classmethod
    def validate_embedding_not_empty(cls, v: list[float]) -> list[float]:
        """Validate embedding vector is not empty."""
        if not v:
            raise ValueError("embedding vector cannot be empty")
        return v


class EmbeddingsIndex(BaseModel):
    """AI-generated vector representations of page fact files for fast similarity search.

    Maintained in master folder for cross-session page matching. Updated incrementally
    as new pages are added or facts change.
    """

    website_id: str = Field(..., description="Website identifier this index belongs to")
    embeddings: list[PageEmbedding] = Field(
        default_factory=list, description="List of page embeddings"
    )
    model: str = Field(..., description="Embeddings model used")
    last_updated: datetime = Field(..., description="When index was last updated")
    version: str = Field(default="1.0", description="Index format version")

    @field_validator("website_id")
    @classmethod
    def validate_website_id(cls, v: str) -> str:
        """Validate website ID format."""
        if not all(c.isalnum() or c in ".-" for c in v):
            raise ValueError("website_id must be a valid domain-like identifier")
        return v.lower()

    def add_embedding(
        self,
        page_hash: str,
        embedding: list[float],
        fact_file_path: str,
        prompt_file_path: str,
    ) -> PageEmbedding:
        """Add or update a page embedding.

        Args:
            page_hash: Page hash identifier
            embedding: Embedding vector
            fact_file_path: Path to fact file
            prompt_file_path: Path to prompt file

        Returns:
            PageEmbedding: The created/updated embedding
        """
        # Remove existing embedding for this page if it exists
        self.embeddings = [e for e in self.embeddings if e.page_hash != page_hash]

        # Add new embedding
        page_embedding = PageEmbedding(
            page_hash=page_hash,
            embedding=embedding,
            fact_file_path=fact_file_path,
            prompt_file_path=prompt_file_path,
            last_updated=datetime.utcnow(),
        )
        self.embeddings.append(page_embedding)
        self.last_updated = datetime.utcnow()

        return page_embedding

    def find_similar(
        self, query_embedding: list[float], threshold: float = 0.8, top_k: int = 5
    ) -> list[tuple[PageEmbedding, float]]:
        """Find similar pages using cosine similarity.

        Args:
            query_embedding: Query embedding vector
            threshold: Minimum similarity threshold (0-1)
            top_k: Maximum number of results

        Returns:
            list[tuple[PageEmbedding, float]]: List of (embedding, similarity_score) tuples
        """
        import math

        results = []

        # Calculate query magnitude
        query_magnitude = math.sqrt(sum(x * x for x in query_embedding))

        for page_embedding in self.embeddings:
            # Calculate cosine similarity
            dot_product = sum(
                q * e for q, e in zip(query_embedding, page_embedding.embedding)
            )
            embedding_magnitude = math.sqrt(
                sum(x * x for x in page_embedding.embedding)
            )

            if query_magnitude == 0 or embedding_magnitude == 0:
                continue

            similarity = dot_product / (query_magnitude * embedding_magnitude)

            if similarity >= threshold:
                results.append((page_embedding, similarity))

        # Sort by similarity descending and take top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def embedding_count(self) -> int:
        """Get number of embeddings in index.

        Returns:
            int: Number of page embeddings
        """
        return len(self.embeddings)


class MasterFolder(BaseModel):
    """Website-specific repository containing merged data across task-based sessions.

    One master folder per website, accumulating deduplicated page data from multiple
    sessions for different tasks (e.g., citizenship form, work visa).
    """

    website_id: str = Field(..., description="Website identifier (e.g., 'uscis.gov')")
    storage_path: str = Field(..., description="Storage path to master folder")
    embeddings_index_path: str = Field(
        ..., description="Path to embeddings index file"
    )
    combined_prompt_path: str | None = Field(
        default=None, description="Path to final combined prompt file"
    )
    page_count: int = Field(default=0, description="Number of unique pages", ge=0)
    last_updated: datetime = Field(..., description="When master was last updated")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Master folder metadata"
    )

    @field_validator("website_id")
    @classmethod
    def validate_website_id(cls, v: str) -> str:
        """Validate website ID format."""
        if not all(c.isalnum() or c in ".-" for c in v):
            raise ValueError("website_id must be a valid domain-like identifier")
        return v.lower()

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        """Validate storage path starts with masters/."""
        if not v.startswith("masters/"):
            raise ValueError("storage_path must start with 'masters/'")
        return v
