"""
Application configuration — loaded from environment variables via Pydantic Settings.
Copy .env.example to .env and populate before running.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # ── App ───────────────────────────────
    ENV: str = "development"
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # ── Database ──────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://sq3d:sq3d@localhost:5432/sq3d"

    # ── Redis ─────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── AWS S3 ────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""  # e.g. http://localhost:9000 for MinIO
    S3_BUCKET: str = "sq3d-assets-dev"
    CLOUDFRONT_DOMAIN: str = ""
    CLOUDFRONT_KEY_PAIR_ID: str = ""
    CLOUDFRONT_PRIVATE_KEY_PATH: str = ""

    # ── Auth ──────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── OAuth2 (Google) ───────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/auth/google/callback"

    # ── OAuth2 (Microsoft) ────────────────
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_REDIRECT_URI: str = "http://localhost:5173/auth/microsoft/callback"

    # ── Celery ────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Elasticsearch ─────────────────────
    ELASTICSEARCH_URL: str = "http://localhost:9200"

    # ── Presigned URL ─────────────────────
    PRESIGN_URL_EXPIRY_SECONDS: int = 21600  # 6 hours
    DOWNLOAD_URL_EXPIRY_SECONDS: int = 3600  # 1 hour
    TILE_URL_EXPIRY_SECONDS: int = 3600


settings = Settings()
