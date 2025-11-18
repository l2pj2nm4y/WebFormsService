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
from src.services.ai.prompt_generator import (
    PromptGenerator,
    get_prompt_generator,
    reset_prompt_generator,
)
from src.services.ai.schema_generator import (
    SchemaGenerator,
    get_schema_generator,
    reset_schema_generator,
)

__all__ = [
    "FactExtractor",
    "get_fact_extractor",
    "reset_fact_extractor",
    "PromptGenerator",
    "get_prompt_generator",
    "reset_prompt_generator",
    "SchemaGenerator",
    "get_schema_generator",
    "reset_schema_generator",
]
