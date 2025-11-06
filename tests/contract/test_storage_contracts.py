"""Contract tests for storage operations.

Tests verify storage interface implementations meet contract specifications:
- Path validation and security
- File size limit enforcement
- CRUD operation contracts
- Error handling requirements
"""

import pytest

from src.lib.validation import PathTraversalError
from src.services.storage import LocalStorage


class TestStorageSecurityContract:
    """Contract tests for storage security requirements."""

    @pytest.mark.asyncio
    async def test_storage_must_reject_path_traversal(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must reject path traversal attempts."""
        storage = LocalStorage()

        # Path traversal with ..
        with pytest.raises(PathTraversalError):
            await storage.read_file("sessions/../etc/passwd")

        # Path traversal in nested path
        with pytest.raises(PathTraversalError):
            await storage.read_file("sessions/session-id/../../../etc/passwd")

        # Null byte injection
        with pytest.raises(PathTraversalError):
            await storage.read_file("sessions/file\x00.txt")

    @pytest.mark.asyncio
    async def test_storage_must_reject_absolute_paths(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must reject absolute paths."""
        storage = LocalStorage()

        with pytest.raises(PathTraversalError):
            await storage.read_file("/etc/passwd")

        with pytest.raises(PathTraversalError):
            await storage.write_file("/tmp/malicious.txt", b"bad")

    @pytest.mark.asyncio
    async def test_storage_must_require_valid_prefix(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage paths must start with sessions/ or masters/."""
        storage = LocalStorage()

        # Invalid prefix
        with pytest.raises(PathTraversalError):
            await storage.read_file("invalid/path/file.txt")

        # No prefix
        with pytest.raises(PathTraversalError):
            await storage.read_file("file.txt")


class TestStorageCRUDContract:
    """Contract tests for storage CRUD operations."""

    @pytest.mark.asyncio
    async def test_write_and_read_file(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must support write and read operations."""
        storage = LocalStorage()

        content = b"test content"
        path = "sessions/test-session/001-test.txt"

        # Write
        await storage.write_file(path, content)

        # Read
        read_content = await storage.read_file(path)

        assert read_content == content

    @pytest.mark.asyncio
    async def test_file_exists_check(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must support file existence checks."""
        storage = LocalStorage()

        path = "sessions/test-session/002-test.txt"

        # File doesn't exist
        exists = await storage.file_exists(path)
        assert exists is False

        # Write file
        await storage.write_file(path, b"content")

        # File exists
        exists = await storage.file_exists(path)
        assert exists is True

    @pytest.mark.asyncio
    async def test_get_file_size(self, test_storage_dir: pytest.TempPathFactory) -> None:
        """Storage must support getting file size."""
        storage = LocalStorage()

        content = b"x" * 1024  # 1 KB
        path = "sessions/test-session/003-test.txt"

        await storage.write_file(path, content)

        size = await storage.get_file_size(path)
        assert size == 1024

    @pytest.mark.asyncio
    async def test_delete_file(self, test_storage_dir: pytest.TempPathFactory) -> None:
        """Storage must support file deletion."""
        storage = LocalStorage()

        path = "sessions/test-session/004-test.txt"

        # Write and verify exists
        await storage.write_file(path, b"content")
        assert await storage.file_exists(path)

        # Delete
        await storage.delete_file(path)

        # Verify deleted
        assert not await storage.file_exists(path)

    @pytest.mark.asyncio
    async def test_list_files_with_prefix(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must support listing files by prefix."""
        storage = LocalStorage()

        session_id = "test-session-001"
        prefix = f"sessions/{session_id}/"

        # Write multiple files
        await storage.write_file(f"{prefix}001-screenshot.png", b"png")
        await storage.write_file(f"{prefix}001-page.html", b"html")
        await storage.write_file(f"{prefix}002-screenshot.png", b"png")

        # List all files
        files = await storage.list_files(prefix)

        assert len(files) == 3
        assert any("001-screenshot.png" in f for f in files)
        assert any("001-page.html" in f for f in files)
        assert any("002-screenshot.png" in f for f in files)

    @pytest.mark.asyncio
    async def test_list_files_with_pattern(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must support listing files with glob patterns."""
        storage = LocalStorage()

        session_id = "test-session-002"
        prefix = f"sessions/{session_id}/"

        # Write files with different extensions
        await storage.write_file(f"{prefix}001-screenshot.png", b"png")
        await storage.write_file(f"{prefix}001-page.html", b"html")
        await storage.write_file(f"{prefix}001-metadata.json", b"json")

        # List only JSON files
        json_files = await storage.list_files(prefix, "*.json")

        assert len(json_files) == 1
        assert "001-metadata.json" in json_files[0]


class TestStorageErrorContract:
    """Contract tests for storage error handling."""

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_raises_error(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must raise FileNotFoundError for nonexistent files."""
        storage = LocalStorage()

        with pytest.raises(FileNotFoundError):
            await storage.read_file("sessions/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_get_size_nonexistent_file_raises_error(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must raise FileNotFoundError when getting size of nonexistent file."""
        storage = LocalStorage()

        with pytest.raises(FileNotFoundError):
            await storage.get_file_size("sessions/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file_raises_error(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must raise FileNotFoundError when deleting nonexistent file."""
        storage = LocalStorage()

        with pytest.raises(FileNotFoundError):
            await storage.delete_file("sessions/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_list_nonexistent_prefix_returns_empty(
        self, test_storage_dir: pytest.TempPathFactory
    ) -> None:
        """Storage must return empty list for nonexistent prefix."""
        storage = LocalStorage()

        files = await storage.list_files("sessions/nonexistent-session/")

        assert files == []
