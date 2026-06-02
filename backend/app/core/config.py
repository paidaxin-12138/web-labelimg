from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Web LabelImg 2.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/labelimg.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me-in-production-use-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./data/storage"
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "labelimg"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False

    LOCK_TTL_SECONDS: int = 120
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost"

    THUMBNAIL_MAX_SIZE: int = 512


@lru_cache
def get_settings() -> Settings:
    return Settings()
