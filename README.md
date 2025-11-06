# WebForms File Processor

AI-powered browser extension file processing system with fact extraction for form automation.

## Features

- **AI-First Processing**: Vision-capable AI models (Claude 3.5 Haiku via OpenRouter) analyze screenshots
- **Fact Extraction**: Automatically identifies visual headings, layout patterns, form elements, and content keywords
- **Distributed Processing**: Redis-based FIFO queue and distributed locking for concurrent backends
- **Flexible Storage**: Supports local file system and S3-compatible storage
- **Type-Safe**: Complete Pydantic models with validation throughout
- **Observable**: Structured JSON logging with trace IDs and comprehensive metrics
- **Test-Driven**: Contract tests, unit tests, and integration tests following TDD

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for local Redis)
- OpenRouter API key

### Installation

```bash
# Install dependencies
poetry install

# Configure environment
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

# Start Redis
docker-compose up -d

# Run tests
pytest tests/ -v
```

### Usage

**Process a specific session:**

```bash
python -m src.main process 550e8400-e29b-41d4-a716-446655440000
```

**Run as continuous worker:**

```bash
python -m src.main worker
```

**Add session to queue:**

```bash
python -m src.main enqueue 550e8400-e29b-41d4-a716-446655440000
```

## Implementation Status

**✅ Phase 1: Setup (6 tasks)** - Complete
**✅ Phase 2: Foundational Infrastructure (16 tasks)** - Complete
**✅ Phase 3: User Story 1 MVP (13 tasks)** - Complete

**Total: 35/35 tasks implemented** 🎉

For detailed specifications, see [specs/001-browser-file-processor/](specs/001-browser-file-processor/)
