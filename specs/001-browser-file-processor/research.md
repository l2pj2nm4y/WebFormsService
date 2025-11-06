# Phase 0: Research & Technology Choices

**Feature**: Browser Extension File Processing System
**Date**: 2025-01-06
**Purpose**: Document technology selection rationale and resolve technical unknowns

## Technology Selection Rationale

### 1. Python 3.11+ (Language)

**Decision**: Use Python 3.11 or later as the implementation language

**Rationale**:
- **Explicit User Requirement**: "I want this to be in python"
- **AI Ecosystem**: Best-in-class support for AI/ML libraries and frameworks
- **Async Support**: Native async/await with asyncio for concurrent AI API calls and I/O operations
- **Type Safety**: Type hints (PEP 484) and runtime validation via Pydantic for data model integrity
- **Mature Ecosystem**: Rich library support for image processing (Pillow), cloud storage (boto3), Redis, HTTP APIs

**Alternatives Considered**: None - explicit user requirement

**Constitution Alignment**:
- ✅ Principle I (AI-First): Excellent AI library ecosystem
- ✅ Principle II (TDD): pytest provides comprehensive testing framework
- ✅ Principle VI (Observability): structlog and native logging support

### 2. Pydantic AI (AI Framework)

**Decision**: Use Pydantic AI (latest version) as the primary AI agent framework

**Rationale**:
- **Explicit User Requirement**: "Use the latest Pydantic AI"
- **Structured Outputs**: Native support for structured AI responses with Pydantic models (critical for fact files and prompt files)
- **Type Safety**: Compile-time and runtime validation of AI outputs against defined schemas
- **Provider Abstraction**: Built-in support for multiple AI providers (OpenAI, Anthropic, etc.) via unified interface
- **Model Flexibility**: Easy switching between models without changing business logic
- **Modern Framework**: Latest AI agent patterns with streaming, retries, and error handling built-in

**Key Features for This Project**:
- Fact extraction returns validated `FactFile` Pydantic model
- Prompt generation returns validated `PromptFile` Pydantic model
- Embeddings generation for similarity matching
- Structured prompts with clear input/output contracts

**Alternatives Considered**:
- LangChain: More complex, heavier abstractions than needed
- Direct API calls: No type safety, manual retry/error handling
- Instructor: Similar capabilities but Pydantic AI is user's explicit choice

**Constitution Alignment**:
- ✅ Principle I (AI-First): Purpose-built for AI agent applications
- ✅ Principle II (TDD): Structured outputs enable contract testing
- ✅ Principle III (Documentation): Clear model definitions serve as documentation
- ✅ Principle VI (Observability): Built-in logging and tracing support

### 3. OpenRouter with Anthropic Claude 3.5 Haiku (AI Provider)

**Decision**: Use OpenRouter as the AI provider gateway, initially configured for anthropic/claude-3.5-haiku

**Rationale**:
- **Explicit User Requirement**: "initially use OpenRouter with anthropic/claude-3.5-haiku"
- **Provider Flexibility**: OpenRouter provides unified API for 100+ AI models from multiple providers
- **Easy Switching**: Change models via configuration without code changes (user requirement: "Allow easy switching of AI Model Providers")
- **Cost Optimization**: Compare costs across providers, switch to cheaper models for specific tasks
- **Redundancy**: Fallback to alternative models if primary provider has issues
- **Vision Support**: Access to vision-capable models (Claude 3.5, GPT-4 Vision, Gemini) for screenshot analysis

**Initial Model Choice (anthropic/claude-3.5-haiku)**:
- Fast inference (critical for 10-15 second SLA per file)
- Vision capabilities for screenshot analysis
- Strong structured output generation
- Cost-effective for high-volume processing
- Proven track record with form understanding

**Configuration Strategy**:
```python
# config.py
AI_PROVIDER = "openrouter"  # Can switch to "openai", "anthropic", "together", etc.
AI_FACT_MODEL = "anthropic/claude-3.5-haiku"
AI_PROMPT_MODEL = "anthropic/claude-3.5-haiku"
AI_EMBEDDINGS_MODEL = "openai/text-embedding-3-small"  # Dedicated embeddings model
```

**Alternatives Considered**:
- Direct Anthropic API: Less flexible, locked to one provider
- OpenAI only: No access to Claude models
- Multiple provider SDKs: More complex, harder to switch

**Constitution Alignment**:
- ✅ Principle I (AI-First): Purpose-built AI provider infrastructure
- ✅ Principle VI (Observability): OpenRouter provides detailed logging and usage metrics

### 4. FastAPI (Web Framework)

**Decision**: Use FastAPI for the API layer (if needed)

**Rationale**:
- **User Requirement**: "If an API is required then use FastAPI"
- **Async Native**: Built on Starlette/ASGI for high-performance async request handling
- **Type Safety**: Automatic validation using Pydantic models (consistent with our data models)
- **Auto-Documentation**: OpenAPI/Swagger docs generated automatically from code
- **Modern Python**: Leverages Python 3.6+ features (type hints, async/await)
- **Performance**: One of the fastest Python frameworks (comparable to Node.js, Go)

**Use Cases in This Project**:
- Health check endpoints for monitoring
- Session submission endpoint (if not using direct file system access)
- Status/metrics API for observability
- Webhook endpoints for notifications

**Note**: Service can run as pure background worker without API if files are uploaded directly to S3. FastAPI provides flexibility for future requirements.

**Alternatives Considered**:
- Flask: Synchronous by default, less modern
- Django: Too heavy for a focused processing service
- No API: Possible, but FastAPI adds minimal overhead and provides operational visibility

**Constitution Alignment**:
- ✅ Principle VI (Observability): Built-in health checks and metrics endpoints
- ✅ Principle III (Documentation): Auto-generated API documentation

### 5. Redis (Coordination Layer)

**Decision**: Use Redis for session queue management and distributed locking

**Rationale**:
- **Explicit User Requirement**: "lets go with redis for both selecting sessions for processing and for locking of the master"
- **Atomic Operations**: FIFO queue operations (LPUSH/RPOP) with atomicity guarantees
- **Distributed Locking**: Native support for distributed locks (Redlock algorithm)
- **High Performance**: Sub-millisecond latency for queue/lock operations
- **Mature Ecosystem**: Battle-tested in production distributed systems
- **Local Development**: Docker image available for local development (user requirement met)
- **Production Ready**: Managed services available (AWS ElastiCache, Redis Cloud) with zero code changes

**Key Operations**:
- Session Queue: Sorted set (ZADD/ZPOPMIN) ordered by upload timestamp for FIFO
- Master Locks: SET with NX and EX flags for distributed locking
- Lock TTL: Configurable timeout to prevent deadlocks from crashed processes

**Alternatives Considered**:
- Database-based locking: Higher latency, more complex
- File-based locking: Doesn't work with distributed file systems (S3)
- Message queues (RabbitMQ, SQS): Overkill for simple FIFO + locking needs

**Constitution Alignment**:
- ✅ Principle VI (Observability): Redis provides monitoring and metrics
- ✅ Principle VII (Security): Supports authentication and TLS for production

### 6. AWS S3 / Cloud Storage (File Storage)

**Decision**: Use S3-compatible cloud storage for session and master folders

**Rationale**:
- **User Context**: "The storage might be cloud base storage like S3"
- **Scalability**: Unlimited storage, no capacity planning needed
- **Durability**: 99.999999999% durability (11 nines)
- **Accessibility**: Multiple backend processes can access same storage
- **Cost-Effective**: Pay only for what you use, no upfront costs
- **Event Notifications**: S3 events can trigger processing (future enhancement)
- **Compatibility**: S3-compatible interface supported by MinIO, Backblaze B2, Wasabi (vendor flexibility)

**Local Development Strategy**:
- Option 1: MinIO (S3-compatible server in Docker)
- Option 2: LocalStack (AWS service emulator)
- Option 3: Local file system with same interface (for simplicity)

**Storage Organization**:
```
sessions/
  <session-guid>/
    001-screenshot.png
    001-page.html
    001-metadata.json
    001-page.facts.json      # Generated
    001-page.schema.json     # Generated

masters/
  <website-id>/
    embeddings.index         # Page embeddings for similarity search
    <page-hash>.prompt.json  # Merged prompt files
    combined.prompt.json     # Final combined output
```

**Alternatives Considered**:
- Local file system only: Doesn't scale to multiple backends
- Database storage: Not optimized for large binary files (images)
- Shared network file system: Complex setup, single point of failure

**Constitution Alignment**:
- ✅ Principle V (Pipeline): Clear input/output boundaries with storage stages
- ✅ Principle VII (Security): S3 supports encryption at rest and in transit

### 7. Pillow (Image Processing)

**Decision**: Use Pillow for image loading, validation, and preprocessing

**Rationale**:
- **Standard Library**: De facto standard for image processing in Python
- **Format Support**: PNG, JPEG, and all common image formats
- **Validation**: Built-in format detection and validation
- **Preprocessing**: Resize/compress images before sending to AI (reduce costs)
- **Metadata Extraction**: Read EXIF data if needed for context

**Use Cases**:
- Load and validate screenshot files
- Verify file formats match expectations (FR-021)
- Resize large images to optimize AI API costs
- Convert to base64 for AI API submission

**Alternatives Considered**:
- OpenCV: Overkill for basic image operations
- imageio: Less mature than Pillow
- Raw file reading: No format validation

**Constitution Alignment**:
- ✅ Principle VII (Security): Format validation prevents malicious files
- ✅ Principle VI (Observability): Can log image dimensions, format, file size

### 8. pytest & pytest-asyncio (Testing Framework)

**Decision**: Use pytest as the primary testing framework with pytest-asyncio for async tests

**Rationale**:
- **Python Standard**: Industry standard testing framework for Python
- **Async Support**: pytest-asyncio enables testing of async code
- **Fixtures**: Powerful fixture system for test setup/teardown
- **Parametrization**: Test same logic with multiple inputs easily
- **Plugin Ecosystem**: pytest-cov for coverage, pytest-mock for mocking, pytest-redis for Redis testing
- **Constitution Requirement**: Supports 80% unit, 70% integration coverage targets

**Testing Strategy**:
- **Unit Tests**: Mock external dependencies (AI API, Redis, S3)
- **Integration Tests**: Real Redis (via docker), mocked AI API (deterministic responses), temporary file system
- **Contract Tests**: Validate AI input prompts and output schemas against specifications
- **Performance Tests**: Measure AI latency, throughput, memory usage

**Key Testing Libraries**:
- pytest-asyncio: Test async functions
- pytest-mock: Mock AI API responses
- fakeredis: In-memory Redis for testing (alternative to docker)
- moto: Mock AWS S3 for testing
- pytest-cov: Code coverage measurement

**Alternatives Considered**:
- unittest: Less feature-rich, more boilerplate
- nose2: Less maintained than pytest

**Constitution Alignment**:
- ✅ Principle II (TDD): pytest enables test-first development
- ✅ Principle II (Coverage): pytest-cov measures 80% unit, 70% integration requirements

### 9. Structured Logging (Python logging + structlog)

**Decision**: Use Python's native logging module with structlog for structured JSON logs

**Rationale**:
- **User Requirement**: "Add logging"
- **Constitution Requirement**: Principle VI mandates structured logging for all operations
- **Observability**: JSON logs easily parsed by log aggregators (CloudWatch, Elasticsearch, Datadog)
- **Context Preservation**: Structured fields enable filtering and correlation
- **Performance**: Low overhead, async-safe

**Log Structure**:
```json
{
  "timestamp": "2025-01-06T12:34:56.789Z",
  "level": "INFO",
  "trace_id": "abc-123",
  "operation": "fact_extraction",
  "file_path": "sessions/guid-123/001-screenshot.png",
  "ai_model": "anthropic/claude-3.5-haiku",
  "ai_latency_ms": 3421,
  "ai_tokens": 2134,
  "ai_cost_usd": 0.0042,
  "success": true
}
```

**Required Log Fields** (per Constitution Principle VI):
- AI operations: prompt (truncated), model, latency, tokens, cost
- File operations: path, size, operation, duration
- Errors: operation, input snapshot, system state, stack trace
- Processing: session_id, triplet_id, stage, success/failure

**Alternatives Considered**:
- Print statements: Not structured, hard to parse
- Native logging only: Lacks structured field support
- Third-party frameworks: structlog is lightweight and flexible

**Constitution Alignment**:
- ✅ Principle VI (Observability): Structured logging is explicitly required
- ✅ Principle III (Documentation): Logs document system behavior

## Resolved Technical Questions

### Q1: How to handle local vs. production Redis?
**Answer**: Single Redis client configuration with environment-based connection string. Docker Redis for local (`redis://localhost:6379`), managed Redis for production (`redis://prod.cache.amazonaws.com:6379`). Zero code changes required (FR-026).

### Q2: How to make AI providers easily switchable?
**Answer**: Pydantic AI provides built-in provider abstraction. Change provider via configuration file:
```python
# Switch from OpenRouter to direct Anthropic
AI_PROVIDER = "anthropic"
AI_MODEL = "claude-3-5-haiku-20241022"
```

### Q3: How to implement FIFO session queue in Redis?
**Answer**: Use Redis Sorted Set (ZADD/ZPOPMIN) with upload timestamp as score:
```python
# Add to queue: ZADD sessions <timestamp> <session_guid>
# Claim next: ZPOPMIN sessions 1
```

### Q4: How to implement distributed locking in Redis?
**Answer**: Use SET with NX (not exists) and EX (expiration) flags:
```python
# Acquire lock: SET lock:master:<website_id> <worker_id> NX EX 300
# Release lock: DEL lock:master:<website_id>
# Lock TTL: 300 seconds (5 minutes) configurable
```

### Q5: How to generate embeddings for similarity search?
**Answer**: Use OpenRouter with embedding-specialized model (e.g., `text-embedding-3-small`):
```python
# Generate embedding from fact file JSON
embedding = await ai_client.embeddings(text=json.dumps(fact_file))
# Store in master folder: embeddings.index (vector database or simple JSON)
```

### Q6: How to structure AI prompts for consistency?
**Answer**: Define prompt templates as Pydantic models with clear structure:
```python
class FactExtractionPrompt(BaseModel):
    system: str  # Role and instructions
    image: str   # Base64 encoded screenshot
    url: str     # Page URL from metadata

# Prompts versioned in code, documented with intent and expected output
```

### Q7: What file size limits to enforce?
**Answer**: Based on spec edge cases and practical limits:
- Screenshots: 10MB max (typical 1-3MB, allows high-res captures)
- HTML: 1MB max (typical 50-200KB, handles large SPAs)
- Metadata: 100KB max (typical 1-5KB JSON)

## Architecture Decision Records (ADRs)

### ADR-001: Use OpenRouter for AI Provider Flexibility

**Context**: Need to support multiple AI providers with easy switching, access to vision-capable models, and cost optimization opportunities.

**Decision**: Use OpenRouter as the AI provider gateway with initial configuration for Anthropic Claude 3.5 Haiku.

**Consequences**:
- ✅ Single API integration point for 100+ models
- ✅ Easy model switching via configuration
- ✅ Cost comparison across providers
- ⚠️ Additional latency from proxy layer (typically <50ms)
- ⚠️ Dependency on OpenRouter service availability (mitigated by direct provider fallback)

**Alternatives**: Direct provider APIs (locked in), LangChain (too heavy), custom abstraction (more work)

### ADR-002: Use Redis Sorted Sets for FIFO Session Queue

**Context**: Need to ensure strict FIFO processing order by upload timestamp while preventing duplicate processing by multiple backends.

**Decision**: Use Redis Sorted Set (ZADD/ZPOPMIN) with upload timestamp as score for atomic FIFO queue operations.

**Consequences**:
- ✅ Atomic FIFO operations (ZPOPMIN is atomic)
- ✅ Timestamp-based ordering (explicit requirement)
- ✅ Prevents duplicate claims (atomic pop)
- ✅ Built-in Redis primitive (no custom logic)

**Alternatives**: List (LPUSH/RPOP - loses timestamp ordering), Custom Lua script (more complex), Database queue (higher latency)

### ADR-003: Simple Overwrite Strategy for MVP Merge

**Context**: Prompt merging is complex (combining fields, resolving conflicts, preserving context). User explicitly requested simple approach for MVP.

**Decision**: Implement simple overwrite strategy for MVP: newer prompt files replace older ones at the master level. Defer advanced merge algorithms to future iterations.

**Consequences**:
- ✅ Fast MVP delivery (FR-032 explicitly allows this)
- ✅ Clear upgrade path (extensible design)
- ⚠️ May lose information if prompts contain complementary data
- ✅ Acceptable per user requirement: "use simple overwrite for MVP"

**Alternatives**: Immediate complex merge (delays MVP), Field-level merge (requires AI to decide conflicts)

### ADR-004: Pydantic Models for All Data Entities

**Context**: Need type safety, validation, and clear contracts between components, especially for AI-generated outputs.

**Decision**: Use Pydantic models for all data entities (Session, FileTriplet, FactFile, PromptFile, ProcessingResult) with strict validation rules.

**Consequences**:
- ✅ Compile-time type checking
- ✅ Runtime validation prevents corrupt data
- ✅ Self-documenting code (models define structure)
- ✅ Easy serialization (JSON, YAML)
- ✅ Constitution Principle III: Models serve as documentation

**Alternatives**: Plain dicts (no validation), dataclasses (less validation), TypedDict (no runtime validation)

## Dependencies Summary

### Core Dependencies
```toml
[tool.poetry.dependencies]
python = "^3.11"
pydantic = "^2.5"
pydantic-ai = "^0.0.8"  # Latest version
fastapi = "^0.109"
uvicorn = "^0.27"       # ASGI server for FastAPI
redis = "^5.0"
boto3 = "^1.34"         # AWS SDK (S3)
pillow = "^10.2"        # Image processing
httpx = "^0.26"         # Async HTTP client for OpenRouter
structlog = "^24.1"     # Structured logging
python-dotenv = "^1.0"  # Environment configuration

[tool.poetry.group.dev.dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.23"
pytest-cov = "^4.1"
pytest-mock = "^3.12"
fakeredis = "^2.21"     # Redis testing
moto = "^5.0"           # S3 mocking
black = "^24.1"         # Code formatting
ruff = "^0.1"           # Linting
mypy = "^1.8"           # Type checking
```

### Local Development Tools
- Docker (Redis container)
- MinIO or LocalStack (S3 emulation) - optional
- Poetry (dependency management)
- VS Code + Python extensions

### Production Requirements
- Python 3.11+ runtime
- Redis server (managed service or self-hosted)
- S3-compatible storage
- Container runtime (Docker/Kubernetes) - optional but recommended

## Next Steps

**Phase 1 Deliverables** (to be created by continuing /speckit.plan):
1. [data-model.md](./data-model.md) - Complete entity definitions with Pydantic models
2. [contracts/ai-models.md](./contracts/ai-models.md) - AI input/output contracts
3. [contracts/storage.md](./contracts/storage.md) - Storage interface contracts
4. [contracts/redis.md](./contracts/redis.md) - Redis operation contracts
5. [contracts/pipeline.md](./contracts/pipeline.md) - Pipeline stage contracts
6. [quickstart.md](./quickstart.md) - Setup and usage guide

**After Planning Complete**: Run `/speckit.tasks` to generate dependency-ordered implementation tasks with TDD workflow.
