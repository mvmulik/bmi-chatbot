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
    log_level: str = "INFO"

    # LLM (chat) provider
    openai_api_type: str = "azure"
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_api_version: str = "2024-08-01-preview"
    openai_deployment_name: str = ""
    openai_model: str = "gpt-4o-mini"

    # Embedding provider (falls back to LLM settings when unset)
    openai_embedding_api_key: str = ""
    openai_embedding_api_base: str = ""
    openai_embedding_api_version: str = ""
    openai_embedding_deployment_name: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    chroma_persist_directory: str = str(ROOT_DIR / "data" / "chroma")
    chroma_collection_name: str = "bmi_documents"

    rag_top_k: int = 5
    rag_max_context_chars: int = 12000
    rag_temperature: float = 0.1
    rag_max_output_tokens: int = 800
    embedding_provider: str = ""
    embedding_batch_size: int = 64

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def chroma_path(self) -> Path:
        path = Path(self.chroma_persist_directory)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def chat_model(self) -> str:
        if self.openai_api_type.lower() == "azure":
            return self.openai_deployment_name or self.openai_model
        return self.openai_model or self.openai_deployment_name

    @property
    def embedding_model(self) -> str:
        if self.openai_api_type.lower() == "azure":
            return self.openai_embedding_deployment_name or self.openai_embedding_model
        return self.openai_embedding_model or self.openai_embedding_deployment_name

    @property
    def embedding_api_key(self) -> str:
        return self.openai_embedding_api_key or self.openai_api_key

    @property
    def embedding_api_base(self) -> str:
        return self.openai_embedding_api_base or self.openai_api_base

    @property
    def embedding_api_version(self) -> str:
        return self.openai_embedding_api_version or self.openai_api_version


settings = Settings()
