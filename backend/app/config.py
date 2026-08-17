from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(
            str(ROOT_DIR / ".env"),
            str(BACKEND_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "bmi-chatbot"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    openai_api_type: str = "azure"
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_api_version: str = "2024-08-01-preview"
    openai_deployment_name: str = ""
    openai_embedding_deployment_name: str = ""
    openai_model: str = ""
    openai_embedding_model: str = ""

    chroma_persist_directory: str = "./data/chroma"
    chroma_collection_name: str = "bmi_documents"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
