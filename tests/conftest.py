"""Pytest configuration and shared fixtures.

Provides common test fixtures for configuration, mocking, and test data.
"""

import os
from pathlib import Path
from typing import Any, Generator

# Set environment variables BEFORE any src imports
os.environ["AI_PROVIDER"] = "openrouter"
os.environ["AI_FACT_MODEL"] = "anthropic/claude-3.5-haiku"
os.environ["AI_PROMPT_MODEL"] = "anthropic/claude-3.5-haiku"
os.environ["OPENROUTER_API_KEY"] = "test_api_key"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["STORAGE_TYPE"] = "local"
os.environ["LOCAL_STORAGE_ROOT"] = "./test_storage"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["LOG_FORMAT"] = "json"

import pytest
from fakeredis import FakeAsyncRedis

from src.lib.config import reset_config
from src.lib.logging import reset_trace_id
from src.services.coordination.redis_connection import reset_redis_client
from src.services.storage import reset_storage


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, None, None]:
    """Reset global state before each test."""
    reset_config()
    reset_storage()
    reset_redis_client()
    reset_trace_id()
    yield
    reset_config()
    reset_storage()
    reset_redis_client()
    reset_trace_id()


@pytest.fixture
def test_storage_dir(tmp_path: Path) -> Path:
    """Provide temporary storage directory for tests.

    Args:
        tmp_path: Pytest's temporary path fixture

    Returns:
        Path: Path to test storage directory
    """
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "sessions").mkdir(exist_ok=True)
    (storage_dir / "masters").mkdir(exist_ok=True)

    # Update environment for this test
    os.environ["LOCAL_STORAGE_ROOT"] = str(storage_dir)

    return storage_dir


@pytest.fixture
async def fake_redis() -> FakeAsyncRedis:
    """Provide fake Redis client for testing.

    Returns:
        FakeAsyncRedis: Fake Redis client
    """
    return FakeAsyncRedis()


@pytest.fixture
def sample_screenshot_bytes() -> bytes:
    """Provide sample screenshot data for testing.

    Returns:
        bytes: Sample PNG image bytes
    """
    # Minimal valid PNG (1x1 transparent pixel)
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000000744524e5300fffffffffffffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "ffffffffffffffff0040e6d8660000000a49444154789c6200010000050001"
        "0d0a2db40000000049454e44ae426082"
    )


@pytest.fixture
def sample_html_content() -> str:
    """Provide sample HTML content for testing.

    Returns:
        str: Sample HTML document
    """
    return """<!DOCTYPE html>
<html>
<head><title>Application Form</title></head>
<body>
    <h1>Application for Naturalization</h1>
    <form>
        <label>First Name: <input type="text" name="firstName" required></label>
        <label>Last Name: <input type="text" name="lastName" required></label>
        <label>Date of Birth: <input type="date" name="dob" required></label>
        <button type="submit">Continue</button>
    </form>
</body>
</html>
"""


@pytest.fixture
def sample_metadata() -> dict[str, Any]:
    """Provide sample metadata for testing.

    Returns:
        dict: Sample metadata
    """
    return {
        "url": "https://uscis.gov/n-400/page-1",
        "timestamp": "2025-01-06T12:00:00Z",
        "viewport": {"width": 1920, "height": 1080},
        "browser": "Chrome",
    }
