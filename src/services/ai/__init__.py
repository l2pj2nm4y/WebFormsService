"""AI services for prompt generation and page matching.

This package contains AI-powered services using Pydantic AI and OpenRouter:
- Prompt/schema generation
- Similarity scoring for page matching
- Embeddings generation for similarity search
"""

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
    "PromptGenerator",
    "get_prompt_generator",
    "reset_prompt_generator",
    "SchemaGenerator",
    "get_schema_generator",
    "reset_schema_generator",
]
