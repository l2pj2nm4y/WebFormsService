"""AI services for fact extraction, prompt generation, and page matching.

This package contains AI-powered services using Pydantic AI and OpenRouter:
- Fact extraction from screenshots
- Prompt/schema generation
- Similarity scoring for page matching
- Embeddings generation for similarity search
"""

from src.services.ai.fact_extractor import (
    FactExtractor,
    get_fact_extractor,
    reset_fact_extractor,
)

__all__ = [
    "FactExtractor",
    "get_fact_extractor",
    "reset_fact_extractor",
]
