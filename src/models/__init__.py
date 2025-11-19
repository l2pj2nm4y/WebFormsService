"""Data models for the WebForms service.

This package contains Pydantic models for:
- Session and FileTriplet (session.py)
- PageIdentification (page_identification.py)
- PromptFile (prompt.py)
- FormSchema (schema.py)
- MasterFolder and EmbeddingsIndex (master.py)
- ProcessingResult and SessionProcessingResult (result.py)
"""

from src.models.page_identification import PageIdentification
from src.models.master import EmbeddingsIndex, MasterFolder, PageEmbedding
from src.models.prompt import FieldMetadata, PromptFile
from src.models.result import AIMetrics, ProcessingResult, SessionProcessingResult
from src.models.schema import (
    ArrayConfig,
    FormField,
    FormFieldConstraint,
    FormSchema,
    FormSection,
    TableColumnConfig,
    TableConfig,
    TableRowValidation,
)
from src.models.session import FileTriplet, FileQuartet, Session

__all__ = [
    # Session models
    "Session",
    "FileTriplet",
    "FileQuartet",
    # Page identification models
    "PageIdentification",
    # Prompt models
    "PromptFile",
    "FieldMetadata",
    # Schema models
    "FormSchema",
    "FormSection",
    "FormField",
    "FormFieldConstraint",
    "ArrayConfig",
    "TableConfig",
    "TableColumnConfig",
    "TableRowValidation",
    # Master models
    "MasterFolder",
    "EmbeddingsIndex",
    "PageEmbedding",
    # Result models
    "ProcessingResult",
    "SessionProcessingResult",
    "AIMetrics",
]
