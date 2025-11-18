"""Configuration management using Pydantic BaseSettings.

This module provides centralized configuration management with environment variable
loading, validation, and type safety. All configuration is loaded from environment
variables or .env files.
"""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIConfig(BaseSettings):
    """AI provider and model configuration."""

    model_config = SettingsConfigDict(env_prefix="AI_", case_sensitive=False)

    provider: Literal["openrouter"] = Field(
        default="openrouter", description="AI provider selection"
    )
    fact_model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        description="Model for fact extraction from screenshots",
    )
    schema_model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        description="Model for form schema generation from screenshots",
    )
    prompt_model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        description="Model for prompt/schema generation",
    )
    similarity_model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        description="Model for similarity scoring",
    )
    embeddings_model: str = Field(
        default="openai/text-embedding-3-small",
        description="Model for embeddings generation",
    )


class OpenRouterConfig(BaseSettings):
    """OpenRouter API configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENROUTER_", case_sensitive=False)

    api_key: str = Field(..., description="OpenRouter API key")


class RedisConfig(BaseSettings):
    """Redis connection and coordination configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    host: str = Field(default="localhost", description="Redis server host")
    port: int = Field(default=6379, description="Redis server port", ge=1, le=65535)
    db: int = Field(default=0, description="Redis database number", ge=0, le=15)
    password: str = Field(default="", description="Redis password (empty for no auth)")
    ssl: bool = Field(default=False, description="Use SSL/TLS for Redis connection")
    default_lock_ttl: int = Field(
        default=300, description="Default lock TTL in seconds", ge=10, le=3600
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Allow empty password for local development."""
        return v


class StorageConfig(BaseSettings):
    """Storage backend configuration."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    storage_type: Literal["local", "s3"] = Field(
        default="local", description="Storage backend type"
    )
    local_storage_root: str = Field(
        default="./storage", description="Local storage root directory"
    )


class S3Config(BaseSettings):
    """S3-compatible storage configuration."""

    model_config = SettingsConfigDict(env_prefix="S3_", case_sensitive=False)

    bucket: str = Field(default="", description="S3 bucket name")
    endpoint: str = Field(default="", description="S3 endpoint (empty for AWS S3)")
    region: str = Field(default="us-east-1", description="S3 region")


class AWSConfig(BaseSettings):
    """AWS credentials configuration."""

    model_config = SettingsConfigDict(env_prefix="AWS_", case_sensitive=False)

    access_key_id: str = Field(default="", description="AWS access key ID")
    secret_access_key: str = Field(default="", description="AWS secret access key")


class FileSizeLimitsConfig(BaseSettings):
    """File size validation limits."""

    model_config = SettingsConfigDict(env_prefix="MAX_", case_sensitive=False)

    screenshot_size_mb: int = Field(
        default=10, description="Max screenshot size in MB", ge=1, le=100
    )
    html_size_mb: int = Field(default=1, description="Max HTML size in MB", ge=1, le=50)
    metadata_size_kb: int = Field(
        default=100, description="Max metadata size in KB", ge=1, le=1000
    )


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_", case_sensitive=False)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    format: Literal["json", "text"] = Field(
        default="json", description="Log output format"
    )


class APIConfig(BaseSettings):
    """FastAPI server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_", case_sensitive=False)

    host: str = Field(default="0.0.0.0", description="API server host")
    port: int = Field(default=8000, description="API server port", ge=1, le=65535)
    workers: int = Field(default=1, description="Number of worker processes", ge=1, le=16)


class Config(BaseSettings):
    """Master configuration combining all subsystems."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Subsystem configurations
    ai: AIConfig = Field(default_factory=AIConfig)
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    s3: S3Config = Field(default_factory=S3Config)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    file_size_limits: FileSizeLimitsConfig = Field(default_factory=FileSizeLimitsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    def validate_storage_config(self) -> None:
        """Validate storage configuration based on storage_type."""
        if self.storage.storage_type == "s3":
            if not self.s3.bucket:
                raise ValueError("S3_BUCKET is required when STORAGE_TYPE=s3")
            if not self.aws.access_key_id or not self.aws.secret_access_key:
                raise ValueError(
                    "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required for S3 storage"
                )


# Global configuration instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create global configuration instance.

    Returns:
        Config: Validated configuration instance

    Raises:
        ValueError: If configuration validation fails
    """
    global _config
    if _config is None:
        _config = Config()
        _config.validate_storage_config()
    return _config


def reset_config() -> None:
    """Reset global configuration (useful for testing)."""
    global _config
    _config = None
