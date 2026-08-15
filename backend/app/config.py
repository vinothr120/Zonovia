from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_SECRET_KEY = "dev-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Zonovia API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://zonovia:zonovia@localhost:5432/zonovia"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    cors_origins: list[str] = ["http://localhost:5173"]

    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15

    # IP-scoped, Redis-backed — independent of the per-account lockout above. See
    # core/rate_limit.py for why both exist.
    login_rate_limit_per_ip: int = 20
    login_rate_limit_window_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> "Settings":
        """The dev-only JWT secret committed in .env.example is public knowledge — shipping
        it to production silently defeats the protection it's meant to provide. Fail fast at
        startup rather than let a misconfigured deploy run 'securely'."""
        if self.is_production and self.jwt_secret_key == _INSECURE_JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY is still the insecure default — set a real secret before deploying to production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
