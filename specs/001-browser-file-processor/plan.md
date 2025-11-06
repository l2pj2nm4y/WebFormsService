# Implementation Plan: Browser Extension File Processing System

**Branch**: `001-browser-file-processor` | **Date**: 2025-01-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-browser-file-processor/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

AI-powered file processing service that analyzes browser extension session captures (screenshots, HTML, metadata) to generate fact files for page identification and prompt files for form automation. The system uses Redis for distributed coordination, supports concurrent backend processing, and merges page-level prompts across task-based sessions into website-specific master folders. Built with Python, Pydantic AI, and OpenRouter for flexible AI provider integration.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Pydantic AI (latest), FastAPI, OpenRouter SDK, Redis client, Boto3 (S3), Pillow (image processing)
**Storage**: Cloud storage (S3 or compatible) for session/master folders, Redis for queue/locks
**Testing**: pytest (unit/integration), pytest-asyncio, redis-py mock for testing
**Target Platform**: Linux server (containerized service)
**Project Type**: single (long-running backend service)
**Performance Goals**:
- 10 seconds per fact file generation (including AI latency)
- 15 seconds per prompt file generation
- 5 sessions (50 triplets) processed in 10 minutes
- Concurrent processing by multiple backend instances

**Constraints**:
- AI token budget: avg 2000 tokens/fact, 4000 tokens/prompt
- File size limits: 10MB screenshots, 1MB HTML
- Redis lock TTL configurable for processing duration
- Zero code changes between local (Docker Redis) and production (managed Redis)

**Scale/Scope**:
- 10-50 file triplets per session
- Multiple concurrent backend processes
- FIFO session processing queue
- One master folder per website

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ I. AI-First Processing (NON-NEGOTIABLE)
- **Compliance**: FULL - All meaningful processing uses AI (fact extraction via vision models, prompt generation via structured AI, similarity scoring, embeddings for matching)
- **Evidence**: FR-004, FR-005, FR-006, FR-027, FR-029 - AI operations are core to every processing stage

### ✅ II. Test-First Development (NON-NEGOTIABLE)
- **Compliance**: FULL - TDD enforced with minimum 80% unit, 70% integration coverage
- **Evidence**: Constitution mandates, spec includes comprehensive acceptance scenarios for all user stories
- **Approach**: Contract tests for AI models, integration tests with Redis mock, unit tests for pipeline stages

### ✅ III. Documentation is Code (NON-NEGOTIABLE)
- **Compliance**: FULL - Comprehensive documentation required per constitution
- **Evidence**: Spec includes detailed requirements, edge cases, entities; plan includes quickstart.md, data-model.md, contracts/
- **Approach**: Docstrings for all public APIs, ADRs for technical decisions, AI prompt documentation with intent

### ✅ IV. No Backward Compatibility or Fallbacks
- **Compliance**: FULL - Greenfield service, explicitly no fallback code or legacy support
- **Evidence**: User requirement "At this stage I don't want fallback code or backward compatible code"
- **Approach**: Build for current requirements only, version 1.0.0 establishes initial contract

### ✅ V. File Processing Pipeline Architecture
- **Compliance**: FULL - Multi-stage pipeline: Ingest → Analyze (AI) → Transform → Merge → Output
- **Evidence**: FR-014 (sequence order), FR-027-034 (merge pipeline stages)
- **Approach**: Session triplet processing → within-session merge → master merge → combined output

### ✅ VI. Observability and Debugging
- **Compliance**: FULL - Structured logging mandatory for all AI and file operations
- **Evidence**: FR-016 (log AI operations), FR-017 (track statistics), FR-018 (error context)
- **Approach**: JSON structured logging, trace IDs, AI call metrics (prompt, model, latency, tokens, cost)

### ✅ VII. Secure File Handling
- **Compliance**: FULL - Security first-class concern at every stage
- **Evidence**: FR-019 (path validation), FR-020 (size limits), FR-021 (type validation)
- **Approach**: Path sanitization, file size enforcement, type verification before processing

**GATE RESULT**: ✅ **PASS** - All seven constitution principles satisfied with full compliance

## Project Structure

### Documentation (this feature)

```text
specs/001-browser-file-processor/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── ai-models.md     # AI model contracts (fact extraction, prompt generation)
│   ├── storage.md       # Storage interface contracts (S3, local file system)
│   ├── redis.md         # Redis contracts (queue operations, locking)
│   └── pipeline.md      # Internal pipeline stage contracts
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── models/
│   ├── session.py           # Session, FileTriplet entities
│   ├── fact.py              # FactFile structure and validation
│   ├── prompt.py            # PromptFile structure and validation
│   ├── master.py            # MasterFolder, EmbeddingsIndex entities
│   └── result.py            # ProcessingResult entity
├── services/
│   ├── ai/
│   │   ├── fact_extractor.py      # AI fact extraction from screenshots
│   │   ├── prompt_generator.py    # AI prompt/schema generation
│   │   ├── similarity_scorer.py   # AI similarity scoring for page matching
│   │   └── embeddings.py          # AI embeddings generation and search
│   ├── storage/
│   │   ├── session_storage.py     # Session folder read operations
│   │   ├── master_storage.py      # Master folder write operations
│   │   └── cloud_adapter.py       # S3/cloud storage abstraction
│   ├── coordination/
│   │   ├── session_queue.py       # Redis session queue management (FIFO)
│   │   └── master_lock.py         # Redis distributed locking
│   ├── pipeline/
│   │   ├── triplet_processor.py   # Process individual file triplets
│   │   ├── session_merger.py      # Merge prompts within session
│   │   ├── master_merger.py       # Merge session to master
│   │   └── combiner.py            # Generate combined prompt per website
│   └── orchestrator.py            # Main service orchestration
├── lib/
│   ├── logging.py          # Structured logging setup
│   ├── validation.py       # File path/type/size validation
│   └── config.py           # Configuration management
└── main.py                 # Service entry point (FastAPI if API needed)

tests/
├── contract/
│   ├── test_ai_contracts.py      # AI model input/output contracts
│   ├── test_storage_contracts.py # Storage interface contracts
│   └── test_redis_contracts.py   # Redis operation contracts
├── integration/
│   ├── test_pipeline_integration.py   # End-to-end pipeline tests
│   ├── test_redis_integration.py      # Redis queue/lock integration
│   └── test_ai_integration.py         # AI service integration (with mocks)
└── unit/
    ├── test_fact_extractor.py
    ├── test_prompt_generator.py
    ├── test_session_queue.py
    ├── test_master_lock.py
    ├── test_triplet_processor.py
    └── test_validation.py
```

**Structure Decision**: Single project structure selected because this is a standalone backend service with no frontend or mobile components. The service operates as a long-running processor with clear separation between AI services, storage abstraction, coordination (Redis), and pipeline stages. This structure supports independent testing of each component while maintaining clear boundaries between concerns.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

**No violations identified** - All constitution principles are fully satisfied. The multi-stage pipeline architecture (Principle V) naturally accommodates the required processing flow: triplet ingestion → AI fact extraction → AI prompt generation → within-session merge → master merge → combined output generation. Redis coordination adds operational complexity but is necessary for concurrent backend processing (FR-022 through FR-026) and explicitly justified by production scaling requirements.
