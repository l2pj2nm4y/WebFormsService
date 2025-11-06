# Storage Contracts

**Feature**: Browser Extension File Processing System
**Date**: 2025-01-06
**Purpose**: Define interface contracts for storage operations (S3, local file system)

## Overview

Storage layer provides abstraction over S3-compatible cloud storage and local file system.
Key requirements:
- Support S3 and local file system with same interface
- Zero code changes between local (development) and production (cloud)
- Security: Path validation, size limits, type verification (FR-019, FR-020, FR-021)
- Observability: Log all file operations with duration and size

## Storage Interface Contract

### Base Interface

```python
from abc import ABC, abstractmethod
from typing import BinaryIO, List
from pathlib import Path

class StorageInterface(ABC):
    """
    Abstract storage interface for session and master folder operations.

    Implementations: S3Storage, LocalStorage
    """

    @abstractmethod
    async def read_file(self, path: str) -> bytes:
        """
        Read file contents.

        Args:
            path: File path relative to storage root

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: File does not exist
            PermissionError: Access denied
            StorageSizeError: File exceeds size limit
        """
        pass

    @abstractmethod
    async def write_file(self, path: str, content: bytes) -> None:
        """
        Write file contents.

        Args:
            path: File path relative to storage root
            content: File contents as bytes

        Raises:
            PermissionError: Access denied
            StorageSizeError: Content exceeds size limit
            PathTraversalError: Invalid path detected
        """
        pass

    @abstractmethod
    async def list_files(self, prefix: str, pattern: str | None = None) -> List[str]:
        """
        List files matching prefix and optional glob pattern.

        Args:
            prefix: Directory prefix to search
            pattern: Optional glob pattern (e.g., "*.png", "001-*")

        Returns:
            List of file paths relative to storage root

        Raises:
            PermissionError: Access denied
        """
        pass

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        pass

    @abstractmethod
    async def file_size(self, path: str) -> int:
        """Get file size in bytes"""
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """Delete file"""
        pass
```

## Session Storage Contract

**Purpose**: Read session folder files (screenshots, HTML, metadata)

### Operations

#### 1. List Session Files

```python
async def list_session_files(session_id: UUID) -> List[str]:
    """
    List all files in a session folder.

    Args:
        session_id: Session GUID

    Returns:
        List of file paths within session folder

    Example:
        ['001-screenshot.png', '001-page.html', '001-metadata.json',
         '002-screenshot.png', '002-page.html', '002-metadata.json']
    """
    prefix = f"sessions/{session_id}/"
    return await storage.list_files(prefix)
```

#### 2. Read Screenshot

```python
async def read_screenshot(session_id: UUID, sequence: int) -> bytes:
    """
    Read screenshot file.

    Args:
        session_id: Session GUID
        sequence: Triplet sequence number (1-999)

    Returns:
        Screenshot bytes

    Raises:
        FileNotFoundError: Screenshot not found
        StorageSizeError: Screenshot exceeds 10MB limit (FR-020)
        InvalidFileTypeError: Not a valid image format (FR-021)

    Size Limit: 10MB (configurable)
    """
    path = f"sessions/{session_id}/{sequence:03d}-screenshot.png"  # Try PNG first
    if not await storage.file_exists(path):
        path = f"sessions/{session_id}/{sequence:03d}-screenshot.jpg"  # Fallback to JPG

    # Enforce size limit before reading
    size = await storage.file_size(path)
    if size > 10 * 1024 * 1024:  # 10MB
        raise StorageSizeError(f"Screenshot exceeds 10MB limit: {size} bytes")

    content = await storage.read_file(path)

    # Validate image format
    if not is_valid_image(content):
        raise InvalidFileTypeError(f"Not a valid image: {path}")

    return content
```

#### 3. Read HTML

```python
async def read_html(session_id: UUID, sequence: int) -> str:
    """
    Read HTML file.

    Args:
        session_id: Session GUID
        sequence: Triplet sequence number (1-999)

    Returns:
        HTML content as string

    Raises:
        FileNotFoundError: HTML not found
        StorageSizeError: HTML exceeds 1MB limit (FR-020)

    Size Limit: 1MB (configurable)
    """
    path = f"sessions/{session_id}/{sequence:03d}-page.html"

    # Enforce size limit
    size = await storage.file_size(path)
    if size > 1 * 1024 * 1024:  # 1MB
        raise StorageSizeError(f"HTML exceeds 1MB limit: {size} bytes")

    content = await storage.read_file(path)
    return content.decode('utf-8', errors='ignore')
```

#### 4. Read Metadata

```python
async def read_metadata(session_id: UUID, sequence: int) -> Dict[str, Any]:
    """
    Read and parse metadata JSON file.

    Args:
        session_id: Session GUID
        sequence: Triplet sequence number (1-999)

    Returns:
        Metadata dictionary

    Raises:
        FileNotFoundError: Metadata not found
        StorageSizeError: Metadata exceeds 100KB limit (FR-020)
        InvalidFileTypeError: Not valid JSON (FR-021)

    Size Limit: 100KB (configurable)
    """
    path = f"sessions/{session_id}/{sequence:03d}-metadata.json"

    # Enforce size limit
    size = await storage.file_size(path)
    if size > 100 * 1024:  # 100KB
        raise StorageSizeError(f"Metadata exceeds 100KB limit: {size} bytes")

    content = await storage.read_file(path)

    try:
        return json.loads(content.decode('utf-8'))
    except json.JSONDecodeError as e:
        raise InvalidFileTypeError(f"Invalid JSON in metadata: {e}")
```

#### 5. Write Fact File

```python
async def write_fact_file(session_id: UUID, sequence: int, fact: FactFile) -> str:
    """
    Write fact file to session folder.

    Args:
        session_id: Session GUID
        sequence: Triplet sequence number
        fact: FactFile to write

    Returns:
        Path to written file

    Raises:
        PermissionError: Write access denied
        PathTraversalError: Invalid path (FR-019)
    """
    path = f"sessions/{session_id}/{sequence:03d}-page.facts.json"

    # Validate path (no traversal)
    validate_path(path)

    # Serialize and write
    content = fact.model_dump_json(indent=2).encode('utf-8')
    await storage.write_file(path, content)

    return path
```

#### 6. Write Prompt File

```python
async def write_prompt_file(session_id: UUID, sequence: int, prompt: PromptFile) -> str:
    """
    Write prompt file to session folder.

    Args:
        session_id: Session GUID
        sequence: Triplet sequence number
        prompt: PromptFile to write

    Returns:
        Path to written file

    Raises:
        PermissionError: Write access denied
        PathTraversalError: Invalid path (FR-019)
    """
    path = f"sessions/{session_id}/{sequence:03d}-page.schema.json"

    # Validate path
    validate_path(path)

    # Serialize and write
    content = prompt.model_dump_json(indent=2).encode('utf-8')
    await storage.write_file(path, content)

    return path
```

## Master Storage Contract

**Purpose**: Write to master folder with lock protection

### Operations

#### 1. Read Embeddings Index

```python
async def read_embeddings_index(website_id: str) -> EmbeddingsIndex:
    """
    Read embeddings index from master folder.

    Args:
        website_id: Website identifier

    Returns:
        EmbeddingsIndex object

    Raises:
        FileNotFoundError: Index doesn't exist yet (return empty index)
    """
    path = f"masters/{website_id}/embeddings.index"

    if not await storage.file_exists(path):
        # Return empty index for new master folders
        return EmbeddingsIndex(
            website_id=website_id,
            embeddings=[],
            embedding_model=config.embeddings_model,
            embedding_dimension=1536  # Default for text-embedding-3-small
        )

    content = await storage.read_file(path)
    return EmbeddingsIndex.model_validate_json(content.decode('utf-8'))
```

#### 2. Write Embeddings Index

```python
async def write_embeddings_index(website_id: str, index: EmbeddingsIndex) -> str:
    """
    Write embeddings index to master folder.

    IMPORTANT: Must hold master lock before calling (FR-024, FR-025)

    Args:
        website_id: Website identifier
        index: EmbeddingsIndex to write

    Returns:
        Path to written file

    Raises:
        PermissionError: Write access denied
        LockNotHeldError: Master lock not held by this worker
    """
    # Verify lock is held (check via Redis)
    if not await master_lock.is_held_by_us(website_id):
        raise LockNotHeldError(f"Master lock not held for {website_id}")

    path = f"masters/{website_id}/embeddings.index"
    validate_path(path)

    content = index.model_dump_json(indent=2).encode('utf-8')
    await storage.write_file(path, content)

    return path
```

#### 3. Write Merged Prompt

```python
async def write_merged_prompt(website_id: str, page_hash: str, prompt: PromptFile) -> str:
    """
    Write merged prompt file for a specific page.

    IMPORTANT: Must hold master lock before calling

    Args:
        website_id: Website identifier
        page_hash: Unique page identifier
        prompt: Merged PromptFile

    Returns:
        Path to written file
    """
    if not await master_lock.is_held_by_us(website_id):
        raise LockNotHeldError(f"Master lock not held for {website_id}")

    path = f"masters/{website_id}/{page_hash}.prompt.json"
    validate_path(path)

    content = prompt.model_dump_json(indent=2).encode('utf-8')
    await storage.write_file(path, content)

    return path
```

#### 4. Write Combined Prompt

```python
async def write_combined_prompt(website_id: str, combined: Dict[str, Any]) -> str:
    """
    Write final combined prompt for entire website.

    IMPORTANT: Must hold master lock before calling

    Args:
        website_id: Website identifier
        combined: Combined prompt dictionary

    Returns:
        Path to written file

    Example combined structure:
        {
            "website_id": "uscis.gov",
            "generated_at": "2025-01-06T15:00:00Z",
            "page_count": 15,
            "pages": {
                "page_hash_1": { ... prompt data ... },
                "page_hash_2": { ... prompt data ... }
            }
        }
    """
    if not await master_lock.is_held_by_us(website_id):
        raise LockNotHeldError(f"Master lock not held for {website_id}")

    path = f"masters/{website_id}/combined.prompt.json"
    validate_path(path)

    content = json.dumps(combined, indent=2).encode('utf-8')
    await storage.write_file(path, content)

    return path
```

## Security Validation

### Path Validation (FR-019)

```python
def validate_path(path: str) -> None:
    """
    Validate storage path to prevent path traversal attacks.

    Raises:
        PathTraversalError: If path contains suspicious patterns

    Checks:
        - No '..' components
        - No absolute paths
        - No null bytes
        - Matches expected patterns (sessions/* or masters/*)
    """
    # No path traversal
    if '..' in path:
        raise PathTraversalError(f"Path traversal detected: {path}")

    # No absolute paths
    if path.startswith('/'):
        raise PathTraversalError(f"Absolute path not allowed: {path}")

    # No null bytes
    if '\x00' in path:
        raise PathTraversalError(f"Null byte detected: {path}")

    # Must match expected patterns
    if not (path.startswith('sessions/') or path.startswith('masters/')):
        raise PathTraversalError(f"Invalid path prefix: {path}")

    # Additional checks can be added (e.g., max length, allowed characters)
```

### File Type Validation (FR-021)

```python
def is_valid_image(content: bytes) -> bool:
    """
    Validate image file format.

    Args:
        content: Image bytes

    Returns:
        True if valid PNG or JPEG

    Uses: Pillow to verify format
    """
    try:
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(content))
        return image.format in ['PNG', 'JPEG']
    except Exception:
        return False


def is_valid_json(content: bytes) -> bool:
    """
    Validate JSON file format.

    Args:
        content: JSON bytes

    Returns:
        True if valid JSON
    """
    try:
        json.loads(content.decode('utf-8'))
        return True
    except Exception:
        return False
```

## Error Types

```python
class StorageError(Exception):
    """Base storage error"""
    pass

class PathTraversalError(StorageError):
    """Path traversal attack detected"""
    pass

class StorageSizeError(StorageError):
    """File exceeds size limit"""
    pass

class InvalidFileTypeError(StorageError):
    """File type validation failed"""
    pass

class LockNotHeldError(StorageError):
    """Operation requires master lock"""
    pass
```

## Implementation: S3 Storage

```python
import boto3
from botocore.exceptions import ClientError

class S3Storage(StorageInterface):
    """
    S3-compatible storage implementation.

    Configuration:
        S3_BUCKET: Bucket name
        S3_ENDPOINT: Optional endpoint URL (for MinIO, LocalStack)
        S3_REGION: AWS region
        AWS_ACCESS_KEY_ID: Credentials (from environment)
        AWS_SECRET_ACCESS_KEY: Credentials (from environment)
    """

    def __init__(self, bucket: str, endpoint: str | None = None):
        self.bucket = bucket
        self.s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            region_name=os.getenv('S3_REGION', 'us-east-1')
        )

    async def read_file(self, path: str) -> bytes:
        validate_path(path)
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=path)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"File not found: {path}")
            raise

    async def write_file(self, path: str, content: bytes) -> None:
        validate_path(path)
        self.s3.put_object(Bucket=self.bucket, Key=path, Body=content)

    async def list_files(self, prefix: str, pattern: str | None = None) -> List[str]:
        validate_path(prefix)
        response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        files = [obj['Key'] for obj in response.get('Contents', [])]

        if pattern:
            import fnmatch
            files = [f for f in files if fnmatch.fnmatch(Path(f).name, pattern)]

        return files

    async def file_exists(self, path: str) -> bool:
        validate_path(path)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=path)
            return True
        except ClientError:
            return False

    async def file_size(self, path: str) -> int:
        validate_path(path)
        response = self.s3.head_object(Bucket=self.bucket, Key=path)
        return response['ContentLength']

    async def delete_file(self, path: str) -> None:
        validate_path(path)
        self.s3.delete_object(Bucket=self.bucket, Key=path)
```

## Implementation: Local File System

```python
import aiofiles
from pathlib import Path

class LocalStorage(StorageInterface):
    """
    Local file system storage implementation for development.

    Configuration:
        STORAGE_ROOT: Root directory for all files
    """

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        """Resolve path within storage root"""
        validate_path(path)
        full_path = self.root / path
        # Ensure resolved path is within root (additional security check)
        if not str(full_path.resolve()).startswith(str(self.root.resolve())):
            raise PathTraversalError(f"Path escapes storage root: {path}")
        return full_path

    async def read_file(self, path: str) -> bytes:
        full_path = self._resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async with aiofiles.open(full_path, 'rb') as f:
            return await f.read()

    async def write_file(self, path: str, content: bytes) -> None:
        full_path = self._resolve_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, 'wb') as f:
            await f.write(content)

    async def list_files(self, prefix: str, pattern: str | None = None) -> List[str]:
        prefix_path = self._resolve_path(prefix)
        if not prefix_path.exists():
            return []

        files = []
        for item in prefix_path.rglob(pattern or '*'):
            if item.is_file():
                rel_path = item.relative_to(self.root)
                files.append(str(rel_path))

        return files

    async def file_exists(self, path: str) -> bool:
        return self._resolve_path(path).exists()

    async def file_size(self, path: str) -> int:
        return self._resolve_path(path).stat().st_size

    async def delete_file(self, path: str) -> None:
        self._resolve_path(path).unlink(missing_ok=True)
```

## Configuration

```python
class StorageConfig(BaseModel):
    """Storage configuration"""
    storage_type: str = Field(default="s3", description="Storage type: s3|local")

    # S3 configuration
    s3_bucket: str = Field(default="webforms-service", description="S3 bucket name")
    s3_endpoint: str | None = Field(None, description="S3 endpoint (for MinIO, LocalStack)")
    s3_region: str = Field(default="us-east-1", description="AWS region")

    # Local storage configuration
    local_storage_root: str = Field(default="./storage", description="Local storage root directory")

    # Size limits (FR-020)
    max_screenshot_size_mb: int = Field(default=10, description="Max screenshot size in MB")
    max_html_size_mb: int = Field(default=1, description="Max HTML size in MB")
    max_metadata_size_kb: int = Field(default=100, description="Max metadata size in KB")

def create_storage(config: StorageConfig) -> StorageInterface:
    """Factory function to create storage instance"""
    if config.storage_type == "s3":
        return S3Storage(bucket=config.s3_bucket, endpoint=config.s3_endpoint)
    elif config.storage_type == "local":
        return LocalStorage(root=config.local_storage_root)
    else:
        raise ValueError(f"Unknown storage type: {config.storage_type}")
```

## Observability (FR-016)

```python
async def read_file_with_logging(storage: StorageInterface, path: str) -> bytes:
    """Wrapper that logs file operations"""
    start = datetime.utcnow()
    try:
        content = await storage.read_file(path)
        duration_ms = (datetime.utcnow() - start).total_seconds() * 1000
        logger.info("storage_read", path=path, size_bytes=len(content), duration_ms=duration_ms, success=True)
        return content
    except Exception as e:
        duration_ms = (datetime.utcnow() - start).total_seconds() * 1000
        logger.error("storage_read", path=path, duration_ms=duration_ms, success=False, error=str(e))
        raise
```

## Test Contracts

```python
async def test_storage_read_write():
    """Contract test: Storage read/write operations"""
    storage = create_storage(test_config)

    # Write file
    content = b"test content"
    await storage.write_file("sessions/test/file.txt", content)

    # Read file
    read_content = await storage.read_file("sessions/test/file.txt")
    assert read_content == content

    # Clean up
    await storage.delete_file("sessions/test/file.txt")

async def test_path_traversal_prevention():
    """Contract test: Path traversal attacks are blocked"""
    storage = create_storage(test_config)

    with pytest.raises(PathTraversalError):
        await storage.read_file("../etc/passwd")

    with pytest.raises(PathTraversalError):
        await storage.read_file("sessions/../masters/data")
```

## Next Steps

1. Implement S3Storage and LocalStorage classes
2. Write contract tests for each operation
3. Configure MinIO for local development
4. Set up size limit enforcement
5. Implement logging wrappers for observability
