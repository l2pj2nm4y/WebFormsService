# Quickstart Guide: Browser Extension File Processing System

**Feature**: Browser Extension File Processing System
**Date**: 2025-01-06
**Purpose**: Setup, configuration, and usage guide for developers

## Prerequisites

### System Requirements
- Python 3.11 or later
- Docker (for local Redis)
- Poetry (for dependency management)
- AWS account (for S3) OR MinIO (for local S3-compatible storage)
- OpenRouter API key

### Skills Required
- Python development experience
- Basic understanding of async/await
- Familiarity with Redis (helpful)
- Cloud storage concepts (S3)

## Quick Setup (5 Minutes)

### 1. Clone and Install Dependencies

```bash
# Clone repository
cd /Users/John.mooney/dev/Corto/WebFormsService

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 2. Start Local Redis

```bash
# Start Redis container
docker run -d --name webforms-redis \
  -p 6379:6379 \
  redis:7-alpine

# Verify Redis is running
docker ps | grep webforms-redis
redis-cli ping  # Should return "PONG"
```

### 3. Configure Environment

Create `.env` file in project root:

```bash
# AI Configuration
AI_PROVIDER=openrouter
AI_FACT_MODEL=anthropic/claude-3.5-haiku
AI_PROMPT_MODEL=anthropic/claude-3.5-haiku
AI_SIMILARITY_MODEL=anthropic/claude-3.5-haiku
AI_EMBEDDINGS_MODEL=openai/text-embedding-3-small
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Redis Configuration (Local Development)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_SSL=false
REDIS_DEFAULT_LOCK_TTL=300

# Storage Configuration (Local Development)
STORAGE_TYPE=local
LOCAL_STORAGE_ROOT=./storage

# File Size Limits
MAX_SCREENSHOT_SIZE_MB=10
MAX_HTML_SIZE_MB=1
MAX_METADATA_SIZE_KB=100

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 4. Initialize Storage

```bash
# Create storage directories
mkdir -p storage/sessions
mkdir -p storage/masters

# Verify structure
tree storage -L 2
```

### 5. Run Tests (Verify Setup)

```bash
# Run all tests
pytest tests/ -v

# Run only contract tests
pytest tests/contract/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Detailed Setup

### Option A: Local File System Storage (Simplest)

Best for: Local development, testing

```bash
# Already configured in Quick Setup above
STORAGE_TYPE=local
LOCAL_STORAGE_ROOT=./storage
```

**Pros**: Simple, fast, no cloud dependencies
**Cons**: Not suitable for multiple backend processes

### Option B: MinIO (S3-Compatible Local)

Best for: Testing S3 integration locally

```bash
# 1. Start MinIO container
docker run -d --name webforms-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"

# 2. Create bucket (via MinIO console at http://localhost:9001)
# Or use AWS CLI:
aws --endpoint-url http://localhost:9000 s3 mb s3://webforms-service

# 3. Update .env
STORAGE_TYPE=s3
S3_BUCKET=webforms-service
S3_ENDPOINT=http://localhost:9000
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
```

### Option C: AWS S3 (Production)

Best for: Production deployment

```bash
# 1. Create S3 bucket (via AWS Console or CLI)
aws s3 mb s3://your-webforms-service

# 2. Configure IAM user with S3 access
# Create IAM user, attach policy for bucket access

# 3. Update .env
STORAGE_TYPE=s3
S3_BUCKET=your-webforms-service
S3_ENDPOINT=  # Leave empty for AWS S3
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

## Usage Examples

### Example 1: Process a Single Session

```python
from uuid import UUID
from src.services.orchestrator import process_session_pipeline

# Process session by ID
session_id = UUID("550e8400-e29b-41d4-a716-446655440000")
result = await process_session_pipeline(session_id)

print(f"Processed {result['triplets_processed']} triplets")
print(f"Identified {result['unique_pages']} unique pages")
print(f"Added {result['pages_added_to_master']} pages to master")
print(f"Combined prompt: {result['combined_prompt_path']}")
```

### Example 2: Upload Session and Add to Queue

```python
from datetime import datetime
from src.services.coordination.session_queue import enqueue_session
from src.models.session import Session

# Create session
session = Session(
    session_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
    task_type="citizenship_form",
    website_id="uscis.gov",
    upload_timestamp=datetime.utcnow(),
    storage_path="sessions/550e8400-e29b-41d4-a716-446655440000"
)

# Add to Redis queue
added = await enqueue_session(
    session.session_id,
    session.upload_timestamp.timestamp()
)

print(f"Session added to queue: {added}")
```

### Example 3: Worker Process (Continuous)

```python
import asyncio
from src.services.coordination.session_queue import claim_next_session
from src.services.orchestrator import process_session_pipeline

async def worker_loop():
    """
    Continuous worker process that claims and processes sessions.
    """
    print("Worker starting...")

    while True:
        # Claim next session from queue
        session_id = await claim_next_session()

        if session_id:
            print(f"Processing session: {session_id}")

            try:
                result = await process_session_pipeline(session_id)
                print(f"Session {session_id} completed successfully")
            except Exception as e:
                print(f"Session {session_id} failed: {e}")
        else:
            # Queue empty, wait before trying again
            await asyncio.sleep(5)

# Run worker
asyncio.run(worker_loop())
```

### Example 4: FastAPI Service

```python
from fastapi import FastAPI
from src.services.orchestrator import process_session_pipeline
from src.services.coordination.session_queue import enqueue_session

app = FastAPI(title="WebForms File Processor")

@app.post("/sessions/{session_id}/enqueue")
async def enqueue_session_endpoint(session_id: UUID, upload_timestamp: float):
    """Add session to processing queue"""
    added = await enqueue_session(session_id, upload_timestamp)
    return {"session_id": str(session_id), "queued": added}

@app.post("/sessions/{session_id}/process")
async def process_session_endpoint(session_id: UUID):
    """Process session immediately (bypass queue)"""
    result = await process_session_pipeline(session_id)
    return result

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from src.services.coordination.redis_connection import redis_health_check

    redis_status = await redis_health_check()

    return {
        "status": "healthy" if redis_status["status"] == "healthy" else "unhealthy",
        "redis": redis_status,
        "timestamp": datetime.utcnow().isoformat()
    }

# Run with: uvicorn src.main:app --reload
```

## Project Structure (Reference)

```
/Users/John.mooney/dev/Corto/WebFormsService/
├── .env                          # Environment configuration
├── pyproject.toml                # Python dependencies (Poetry)
├── storage/                      # Local storage (if using local mode)
│   ├── sessions/
│   │   └── <session-guid>/
│   │       ├── 001-screenshot.png
│   │       ├── 001-page.html
│   │       ├── 001-metadata.json
│   │       ├── 001-page.facts.json       # Generated
│   │       └── 001-page.schema.json      # Generated
│   └── masters/
│       └── <website-id>/
│           ├── embeddings.index
│           ├── <page-hash>.prompt.json
│           └── combined.prompt.json
├── src/
│   ├── models/                   # Pydantic data models
│   ├── services/                 # Core services
│   │   ├── ai/                   # AI operations
│   │   ├── storage/              # Storage abstraction
│   │   ├── coordination/         # Redis queue/locks
│   │   ├── pipeline/             # Pipeline stages
│   │   └── orchestrator.py       # Main orchestration
│   ├── lib/                      # Utilities
│   └── main.py                   # FastAPI entry point
├── tests/
│   ├── contract/                 # Contract tests
│   ├── integration/              # Integration tests
│   └── unit/                     # Unit tests
└── specs/                        # Feature specifications
    └── 001-browser-file-processor/
        ├── spec.md
        ├── plan.md
        ├── research.md
        ├── data-model.md
        ├── quickstart.md          # This file
        └── contracts/
```

## Common Operations

### Check Queue Status

```bash
# Connect to Redis CLI
redis-cli

# Check queue size
ZCARD session_queue

# View next 5 sessions
ZRANGE session_queue 0 4 WITHSCORES

# Clear queue (development only!)
DEL session_queue
```

### Check Master Lock Status

```bash
redis-cli

# Check if website is locked
EXISTS lock:master:uscis.gov

# View lock owner
GET lock:master:uscis.gov

# Force release lock (admin only!)
DEL lock:master:uscis.gov
```

### View Generated Files

```bash
# List session files
ls -lah storage/sessions/<session-guid>/

# View fact file
cat storage/sessions/<session-guid>/001-page.facts.json | jq

# View prompt file
cat storage/sessions/<session-guid>/001-page.schema.json | jq

# View combined prompt
cat storage/masters/<website-id>/combined.prompt.json | jq
```

### Monitor Logs

```bash
# Tail logs (if using file logging)
tail -f logs/webforms.log | jq

# Filter for errors
grep "ERROR" logs/webforms.log | jq

# Filter for specific operation
grep "triplet_processing" logs/webforms.log | jq
```

## Testing Workflow

### Test Data Setup

Create test session folder:

```bash
# Create test session
mkdir -p storage/sessions/test-session-001

# Add sample files (create or copy from real session)
cp path/to/screenshot.png storage/sessions/test-session-001/001-screenshot.png
cp path/to/page.html storage/sessions/test-session-001/001-page.html
echo '{"url": "https://example.com/form"}' > storage/sessions/test-session-001/001-metadata.json
```

### Run Contract Tests

```bash
# Test AI contracts
pytest tests/contract/test_ai_contracts.py -v

# Test storage contracts
pytest tests/contract/test_storage_contracts.py -v

# Test Redis contracts
pytest tests/contract/test_redis_contracts.py -v

# Test pipeline contracts
pytest tests/contract/test_pipeline_contracts.py -v
```

### Run Integration Tests

```bash
# Full pipeline integration test
pytest tests/integration/test_pipeline_integration.py -v

# Redis integration test (requires Docker Redis)
pytest tests/integration/test_redis_integration.py -v

# AI integration test (requires API key)
pytest tests/integration/test_ai_integration.py -v
```

### Test Coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=html --cov-report=term

# View in browser
open htmlcov/index.html

# Check coverage meets requirements (80% unit, 70% integration)
pytest --cov=src --cov-fail-under=80
```

## Troubleshooting

### Issue: Redis connection refused

**Symptoms**: `ConnectionError: Error connecting to Redis`

**Solution**:
```bash
# Check if Redis is running
docker ps | grep webforms-redis

# If not running, start it
docker start webforms-redis

# Or restart from scratch
docker rm webforms-redis
docker run -d --name webforms-redis -p 6379:6379 redis:7-alpine
```

### Issue: OpenRouter API errors

**Symptoms**: `AIOperationError: API key invalid`

**Solution**:
1. Check API key in `.env` file
2. Verify API key at https://openrouter.ai/keys
3. Ensure OPENROUTER_API_KEY environment variable is set
4. Check for sufficient credits in OpenRouter account

### Issue: File size limit exceeded

**Symptoms**: `StorageSizeError: Screenshot exceeds 10MB limit`

**Solution**:
```bash
# Adjust limits in .env
MAX_SCREENSHOT_SIZE_MB=20  # Increase limit
MAX_HTML_SIZE_MB=2

# Or compress images before processing
# (handled by browser extension, not this service)
```

### Issue: Path traversal errors

**Symptoms**: `PathTraversalError: Path traversal detected`

**Solution**:
- Ensure file paths don't contain `..` or start with `/`
- Check session folder structure matches expected pattern
- Verify file naming follows convention: `###-name.extension`

### Issue: Lock acquisition failures

**Symptoms**: `LockAcquisitionError: Could not acquire lock for uscis.gov`

**Solution**:
```bash
# Check if lock exists
redis-cli GET lock:master:uscis.gov

# Wait for lock to expire (default 300s = 5 minutes)
# Or force release (admin only, check for crashed worker first)
redis-cli DEL lock:master:uscis.gov
```

## Production Deployment

### Configuration Checklist

- [ ] Use managed Redis service (AWS ElastiCache, Redis Cloud)
- [ ] Use S3 for storage (not local file system)
- [ ] Set strong Redis password
- [ ] Enable Redis SSL/TLS
- [ ] Use secrets manager for API keys (not .env files)
- [ ] Configure proper IAM roles for S3 access
- [ ] Set up structured logging to CloudWatch/Elasticsearch
- [ ] Configure metrics collection and alerting
- [ ] Set appropriate lock TTL for production workload
- [ ] Enable auto-scaling for worker processes
- [ ] Set up health check endpoints
- [ ] Configure rate limiting for AI API calls

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction

# Copy source code
COPY src/ ./src/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run worker
CMD ["python", "-m", "src.main"]
```

```bash
# Build image
docker build -t webforms-processor .

# Run worker
docker run -d \
  --name webforms-worker \
  --env-file .env.production \
  webforms-processor
```

### Kubernetes Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webforms-processor
spec:
  replicas: 3  # Multiple workers for concurrency
  selector:
    matchLabels:
      app: webforms-processor
  template:
    metadata:
      labels:
        app: webforms-processor
    spec:
      containers:
      - name: processor
        image: webforms-processor:latest
        env:
        - name: REDIS_HOST
          value: "redis.default.svc.cluster.local"
        - name: STORAGE_TYPE
          value: "s3"
        envFrom:
        - secretRef:
            name: webforms-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
```

## Next Steps

1. **Implement Core Services**: Start with data models, then AI services, storage, Redis coordination
2. **Write Tests**: Follow TDD - write tests before implementation
3. **Pipeline Integration**: Implement pipeline stages and orchestration
4. **Logging & Metrics**: Set up comprehensive observability
5. **Documentation**: Add docstrings, ADRs, and API documentation
6. **Performance Testing**: Load testing with realistic session volumes
7. **Production Deployment**: Deploy to staging, then production with monitoring

## Additional Resources

- [Feature Specification](./spec.md)
- [Implementation Plan](./plan.md)
- [Technology Research](./research.md)
- [Data Model](./data-model.md)
- [AI Model Contracts](./contracts/ai-models.md)
- [Storage Contracts](./contracts/storage.md)
- [Redis Contracts](./contracts/redis.md)
- [Pipeline Contracts](./contracts/pipeline.md)

## Support

For issues or questions:
1. Check specification documents in `specs/001-browser-file-processor/`
2. Review contract tests in `tests/contract/`
3. Check logs for error context
4. Consult constitution for design principles

---

**Last Updated**: 2025-01-06
**Feature Version**: 001-browser-file-processor (MVP)
