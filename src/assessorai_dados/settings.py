from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/assessorai_dados"
    github_data_repository: str = "assessorAI/assessorai-dados"
    github_data_release: str = "latest"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    public_rate_limit_per_minute: int = 60
    api_key_rate_limit_per_minute: int = 600
    public_api_key_hashes: str = ""
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,testserver"
    mcp_allowed_origins: str = "http://localhost:*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def api_key_hash_set(self) -> set[str]:
        return {value.strip().lower() for value in self.public_api_key_hashes.split(",") if value}

    @staticmethod
    def _csv_values(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def allowed_mcp_hosts(self) -> list[str]:
        return self._csv_values(self.mcp_allowed_hosts)

    @property
    def allowed_mcp_origins(self) -> list[str]:
        return self._csv_values(self.mcp_allowed_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
