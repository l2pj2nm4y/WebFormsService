# AI Model Contracts

**Feature**: Browser Extension File Processing System
**Date**: 2025-01-06
**Purpose**: Define input/output contracts for all AI operations

## Overview

All AI operations use Pydantic AI for structured outputs with type safety. This document specifies:
- Input prompt formats
- Expected output schemas
- Error handling requirements
- Performance SLAs
- Token budget constraints

## 1. Fact Extraction Contract

**Operation**: Extract page identification characteristics from screenshot

**Input**:
```python
class FactExtractionInput(BaseModel):
    """Input for fact extraction from screenshot"""
    screenshot_base64: str = Field(..., description="Base64-encoded screenshot image")
    screenshot_format: str = Field(..., description="Image format: 'png' or 'jpeg'")
    page_url: str = Field(..., description="Page URL from metadata")
    html_snippet: str | None = Field(None, description="Optional HTML snippet for context (first 5000 chars)")
```

**Prompt Template**:
```python
FACT_EXTRACTION_SYSTEM_PROMPT = """You are an expert at analyzing webpage screenshots to extract identification facts for page matching.

Your task is to analyze the provided screenshot and extract structured information that uniquely identifies this page.
Focus on visual elements that are stable across form-filling sessions (headings, layout, structure) rather than dynamic content (user input, timestamps).

Return your analysis as structured JSON matching the FactFile schema."""

def create_fact_extraction_prompt(input: FactExtractionInput) -> str:
    return f"""Analyze this webpage screenshot and URL to extract identification facts for page matching.

URL: {input.page_url}

Extract the following information as JSON:

1. **visual_headings**: Array of main headings/titles visible on the page (up to 5 most prominent)
   - Focus on stable headings, not user-entered text
   - Include navigation labels if prominent

2. **visual_sections**: Array describing the visual layout sections
   - Common values: "header", "main_content", "sidebar", "footer", "navigation"
   - Describe the visual structure you see

3. **form_elements**: Object with:
   - has_forms: boolean (true if any forms are visible)
   - visible_fields: array of field types you can identify (e.g., "email", "password", "text", "dropdown", "checkbox", "radio", "file_upload")
   - buttons: array of button labels/text visible (e.g., "Submit", "Cancel", "Next")

4. **layout_pattern**: String describing overall layout
   - Examples: "single_column", "two_column", "centered_form", "dashboard", "grid_layout", "wizard_steps"

5. **content_keywords**: Array of 3-5 key descriptive terms about the page content/purpose
   - Focus on the page's function, not specific user data
   - Examples: ["application", "personal_info", "payment"], ["login", "authentication"], ["dashboard", "overview", "statistics"]

Return valid JSON matching the FactFile schema. Be concise but accurate."""
```

**Output Schema**: [`FactFile`](../data-model.md#3-factfile) (from data-model.md)

**Performance SLA**:
- Max latency: 10 seconds (95th percentile)
- Token budget: Average 2000 tokens (input + output)
- Success rate: 95%+ for well-formed screenshots

**Error Handling**:
- Malformed JSON response: Retry once, then fail with error context
- API timeout: Retry with exponential backoff (3 attempts max)
- Rate limit: Wait and retry based on Retry-After header
- Invalid schema: Log AI response, return validation errors

**Test Contract**:
```python
async def test_fact_extraction_contract():
    """Contract test: Fact extraction returns valid FactFile"""
    # Given: A sample screenshot and metadata
    input_data = FactExtractionInput(
        screenshot_base64=load_test_image("sample_form.png"),
        screenshot_format="png",
        page_url="https://example.gov/form"
    )

    # When: Fact extraction is performed
    result = await ai_service.extract_facts(input_data)

    # Then: Result matches FactFile schema
    assert isinstance(result, FactFile)
    assert len(result.visual_headings) <= 5
    assert 3 <= len(result.content_keywords) <= 5
    assert result.form_elements.has_forms in [True, False]
    assert result.ai_model.startswith("anthropic/") or result.ai_model.startswith("openai/")
```

## 2. Prompt Generation Contract

**Operation**: Generate structured form field definitions from screenshot

**Input**:
```python
class PromptGenerationInput(BaseModel):
    """Input for prompt/schema generation from screenshot"""
    screenshot_base64: str = Field(..., description="Base64-encoded screenshot image")
    screenshot_format: str = Field(..., description="Image format: 'png' or 'jpeg'")
    html_snippet: str | None = Field(None, description="Optional HTML for field names/structure")
    fact_file: FactFile | None = Field(None, description="Optional fact file for context")
```

**Prompt Template** (from user-provided reference):
```python
PROMPT_GENERATION_SYSTEM_PROMPT = """<role>
You are an expert at analysing screenshots and constructing JSON schemas for form automation.
</role>

<field_notation_guide>
Fields in the schema contain bracketed instructions [...] that describe what values to extract and how to format them.
Each bracketed instruction follows a structured pattern: [Requirement: DataType - Description, Constraints, NullHandling]

Examples:
- [Required: string - Full legal name]
- [Optional: string - Middle name, null if none]
- [Required: string - One of: active|inactive|pending]
- [Required: number - Age in years, Between 0 and 150]
- [Required: date - Date of birth, Format: YYYY-MM-DD]
- [Required: file - Upload document, Allowed: PDF, DOC, DOCX]
- [Required: email - Email address, Valid email format]
- [Optional: phone - Phone number, Format: +1-XXX-XXX-XXXX, null if none]
</field_notation_guide>

<task>
Analyze the provided form screenshot and generate a complete JSON schema that describes ALL visible editable fields.

Key requirements:
1. Include ONLY editable fields (text inputs, dropdowns, checkboxes, radio buttons, file uploads)
2. EXCLUDE non-editable elements (buttons, links, static labels, disabled fields, navigation)
3. Mark fields as Required or Optional based on visual indicators (asterisks, "required" labels)
4. For dropdowns/radio buttons, list options as "One of: option1|option2|option3"
5. Include validation constraints visible on the form (character limits, format patterns, value ranges)
6. Organize related fields into nested objects (e.g., address, contact_info)
7. Use arrays for repeating elements (e.g., list of dependents, multiple addresses)
8. Add metadata annotations (_description, _required, _sensitive, _arrayDescription, _minItems, _maxItems)

Return valid JSON matching the PromptFile schema.
</task>"""

def create_prompt_generation_prompt(input: PromptGenerationInput) -> str:
    context = f"HTML snippet (first 5000 chars):\n{input.html_snippet}\n\n" if input.html_snippet else ""
    return f"""Analyze this form screenshot and generate a comprehensive JSON schema for form automation.

{context}Generate a complete schema covering ALL visible editable fields using the bracketed notation format described in the system prompt.

Focus on:
- All input fields (text, email, phone, number, date, etc.)
- All selection fields (dropdowns, radio buttons, checkboxes)
- All file upload fields
- Required vs Optional designation
- Validation constraints
- Field grouping and nesting
- Array structures for repeating elements

Return valid JSON matching the PromptFile schema."""
```

**Output Schema**: [`PromptFile`](../data-model.md#4-promptfile) (from data-model.md)

**Performance SLA**:
- Max latency: 15 seconds (95th percentile)
- Token budget: Average 4000 tokens (input + output)
- Success rate: 90%+ for forms with clear field definitions

**Error Handling**:
- Malformed JSON response: Retry once with clarifying prompt
- Missing required fields: Log warning, return partial schema
- API timeout: Retry with exponential backoff (3 attempts max)
- Invalid schema: Log AI response, return validation errors

**Test Contract**:
```python
async def test_prompt_generation_contract():
    """Contract test: Prompt generation returns valid PromptFile"""
    # Given: A sample screenshot of a form
    input_data = PromptGenerationInput(
        screenshot_base64=load_test_image("sample_form.png"),
        screenshot_format="png"
    )

    # When: Prompt generation is performed
    result = await ai_service.generate_prompt(input_data)

    # Then: Result matches PromptFile schema
    assert isinstance(result, PromptFile)
    assert len(result.fields) > 0
    for field_name, field_def in result.fields.items():
        assert field_def.requirement in ["Required", "Optional"]
        assert field_def.field_type in ["string", "email", "phone", "date", "datetime", "number", "boolean", "array", "file", "object"]
        assert field_def.description
```

## 3. Similarity Scoring Contract

**Operation**: Score similarity between two fact files for page matching

**Input**:
```python
class SimilarityScoringInput(BaseModel):
    """Input for AI-based similarity scoring"""
    fact_file_1: FactFile = Field(..., description="First fact file")
    fact_file_2: FactFile = Field(..., description="Second fact file")
```

**Prompt Template**:
```python
SIMILARITY_SCORING_SYSTEM_PROMPT = """You are an expert at comparing webpage identification facts to determine if two page captures represent the same page at different stages of form filling.

Your task is to analyze two FactFile objects and return a similarity score (0.0 to 1.0) indicating how likely they represent the same page.

Consider:
- Visual headings similarity (high weight)
- Layout pattern match (high weight)
- Form elements similarity (medium weight)
- Visual sections similarity (medium weight)
- Content keywords overlap (medium weight)

Return a structured response with score and reasoning."""

def create_similarity_prompt(input: SimilarityScoringInput) -> str:
    return f"""Compare these two webpage fact files and determine if they represent the same page.

Fact File 1:
{json.dumps(input.fact_file_1.model_dump(), indent=2)}

Fact File 2:
{json.dumps(input.fact_file_2.model_dump(), indent=2)}

Analyze the similarity and return JSON with:
{{
  "similarity_score": <float between 0.0 and 1.0>,
  "is_same_page": <boolean, true if score >= 0.85>,
  "reasoning": <string explaining the similarity assessment>,
  "matching_features": [<list of features that match>],
  "differing_features": [<list of features that differ>]
}}

A score of 0.85 or higher indicates the same page captured at different stages."""
```

**Output Schema**:
```python
class SimilarityResult(BaseModel):
    """AI similarity scoring result"""
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score (0-1)")
    is_same_page: bool = Field(..., description="True if score >= threshold (0.85)")
    reasoning: str = Field(..., description="Explanation of similarity assessment")
    matching_features: List[str] = Field(default_factory=list, description="Features that match")
    differing_features: List[str] = Field(default_factory=list, description="Features that differ")
```

**Performance SLA**:
- Max latency: 5 seconds (95th percentile)
- Token budget: Average 1500 tokens
- Success rate: 95%+

**Error Handling**:
- Invalid score range: Clamp to 0.0-1.0
- Missing fields: Return score 0.0 with error explanation
- API timeout: Retry once, then return similarity 0.0 (conservative)

**Test Contract**:
```python
async def test_similarity_scoring_contract():
    """Contract test: Similarity scoring returns valid result"""
    # Given: Two similar fact files
    fact1 = FactFile(
        visual_headings=["Application Form", "Personal Information"],
        layout_pattern="single_column_form",
        # ... other fields
    )
    fact2 = FactFile(
        visual_headings=["Application Form", "Personal Information"],
        layout_pattern="single_column_form",
        # ... other fields with slight differences
    )

    input_data = SimilarityScoringInput(fact_file_1=fact1, fact_file_2=fact2)

    # When: Similarity scoring is performed
    result = await ai_service.score_similarity(input_data)

    # Then: Result is valid
    assert isinstance(result, SimilarityResult)
    assert 0.0 <= result.similarity_score <= 1.0
    assert isinstance(result.is_same_page, bool)
    assert result.reasoning
```

## 4. Embeddings Generation Contract

**Operation**: Generate vector embeddings from fact file for similarity search

**Input**:
```python
class EmbeddingsInput(BaseModel):
    """Input for embeddings generation"""
    fact_file: FactFile = Field(..., description="Fact file to embed")
    text_representation: str = Field(..., description="Text representation of fact file")
```

**Preprocessing**:
```python
def fact_file_to_text(fact: FactFile) -> str:
    """Convert fact file to text representation for embedding"""
    parts = [
        "Headings: " + ", ".join(fact.visual_headings),
        "Layout: " + fact.layout_pattern,
        "Sections: " + ", ".join(fact.visual_sections),
        "Keywords: " + ", ".join(fact.content_keywords),
        "Has forms: " + str(fact.form_elements.has_forms),
        "Fields: " + ", ".join(fact.form_elements.visible_fields)
    ]
    return " | ".join(parts)
```

**Output Schema**:
```python
class EmbeddingsResult(BaseModel):
    """Embeddings generation result"""
    embedding_vector: List[float] = Field(..., description="Vector representation")
    embedding_model: str = Field(..., description="Model used")
    embedding_dimension: int = Field(..., description="Vector dimension")
```

**Performance SLA**:
- Max latency: 3 seconds (95th percentile)
- Token budget: Average 500 tokens
- Success rate: 99%+

**Model Configuration**:
```python
# Recommended embedding models via OpenRouter
EMBEDDING_MODELS = {
    "small": "openai/text-embedding-3-small",     # 1536 dims, fast, cost-effective
    "large": "openai/text-embedding-3-large",     # 3072 dims, higher quality
    "default": "openai/text-embedding-3-small"
}
```

**Test Contract**:
```python
async def test_embeddings_generation_contract():
    """Contract test: Embeddings generation returns valid vector"""
    # Given: A fact file
    fact = FactFile(
        visual_headings=["Application Form"],
        layout_pattern="single_column",
        # ... other required fields
    )
    text = fact_file_to_text(fact)
    input_data = EmbeddingsInput(fact_file=fact, text_representation=text)

    # When: Embeddings are generated
    result = await ai_service.generate_embeddings(input_data)

    # Then: Result is valid vector
    assert isinstance(result, EmbeddingsResult)
    assert len(result.embedding_vector) in [384, 768, 1536, 3072]  # Common dimensions
    assert all(isinstance(v, float) for v in result.embedding_vector)
```

## Error Handling Strategy

**All AI Operations Must**:
1. Validate input schemas before API calls
2. Implement exponential backoff retry logic (max 3 attempts)
3. Log all AI operations (prompt, model, latency, tokens, cost)
4. Return structured errors with context
5. Track success rates and latency metrics
6. Respect token budgets (fail fast if exceeded)

**Error Response Schema**:
```python
class AIOperationError(BaseModel):
    """Standard error response for AI operations"""
    operation: str = Field(..., description="Operation that failed")
    error_type: str = Field(..., description="Error category: timeout|rate_limit|validation|api_error")
    error_message: str = Field(..., description="Human-readable error message")
    retry_attempted: bool = Field(..., description="Whether retry was attempted")
    context: Dict[str, Any] = Field(..., description="Additional context for debugging")
```

## Configuration

**AI Provider Configuration**:
```python
class AIConfig(BaseModel):
    """Configuration for AI services"""
    provider: str = Field(default="openrouter", description="AI provider: openrouter|openai|anthropic")
    fact_model: str = Field(default="anthropic/claude-3.5-haiku", description="Model for fact extraction")
    prompt_model: str = Field(default="anthropic/claude-3.5-haiku", description="Model for prompt generation")
    similarity_model: str = Field(default="anthropic/claude-3.5-haiku", description="Model for similarity scoring")
    embeddings_model: str = Field(default="openai/text-embedding-3-small", description="Model for embeddings")

    # Performance settings
    max_retries: int = Field(default=3, description="Max retry attempts")
    timeout_seconds: int = Field(default=30, description="API timeout")

    # Budget controls
    max_tokens_per_fact: int = Field(default=2500, description="Token budget for fact extraction")
    max_tokens_per_prompt: int = Field(default=5000, description="Token budget for prompt generation")
```

## Monitoring and Metrics

**Required Metrics** (per Constitution Principle VI):
```python
class AIMetrics(BaseModel):
    """Metrics tracked for AI operations"""
    operation: str
    model: str
    latency_ms: int
    tokens_input: int
    tokens_output: int
    tokens_total: int
    cost_usd: float
    success: bool
    timestamp: datetime
```

**Metrics Collection**:
- Track per-operation latency (P50, P95, P99)
- Track token usage and costs
- Track success/failure rates
- Track retry counts
- Export to structured logs for aggregation

## Next Steps

1. Implement AI service layer using these contracts
2. Write contract tests for each operation
3. Configure OpenRouter with initial models
4. Implement retry logic and error handling
5. Set up metrics collection and logging
