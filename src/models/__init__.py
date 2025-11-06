"""Data models for the WebForms service.

This package contains Pydantic models for:
- Session and FileTriplet (session.py)
- FactFile (fact.py)
- PromptFile (prompt.py)
- MasterFolder and EmbeddingsIndex (master.py)
- ProcessingResult and SessionProcessingResult (result.py)
"""

from src.models.fact import FactFile, FormElements
from src.models.master import EmbeddingsIndex, MasterFolder, PageEmbedding
from src.models.prompt import FieldMetadata, PromptFile
from src.models.result import AIMetrics, ProcessingResult, SessionProcessingResult
from src.models.session import FileTriplet, Session

__all__ = [
    # Session models
    "Session",
    "FileTriplet",
    # Fact models
    "FactFile",
    "FormElements",
    # Prompt models
    "PromptFile",
    "FieldMetadata",
    # Master models
    "MasterFolder",
    "EmbeddingsIndex",
    "PageEmbedding",
    # Result models
    "ProcessingResult",
    "SessionProcessingResult",
    "AIMetrics",
]
