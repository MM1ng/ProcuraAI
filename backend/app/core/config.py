from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SQLITE_URL = f"sqlite:///{(PROJECT_ROOT / 'backend' / 'procurement.db').as_posix()}"

for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"):
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    sqlite_database_url: str = os.getenv("SQLITE_DATABASE_URL", DEFAULT_SQLITE_URL)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "tongyi")
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen-turbo")
    qwen_top_p: float = _float_env("QWEN_TOP_P", 0.8)
    qwen_max_tokens: int = _int_env("QWEN_MAX_TOKENS", 2000)
    qwen_timeout_seconds: int = _int_env("QWEN_TIMEOUT_SECONDS", 12)
    qwen_enable_thinking: bool = _bool_env("QWEN_ENABLE_THINKING", False)
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "tongyi")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
    embedding_dimension: int = _int_env("EMBEDDING_DIMENSION", 1024)
    embedding_timeout_seconds: int = _int_env("EMBEDDING_TIMEOUT_SECONDS", 20)
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_success_url: str = os.getenv("STRIPE_SUCCESS_URL", "")
    stripe_cancel_url: str = os.getenv("STRIPE_CANCEL_URL", "")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
    use_mock_llm: bool = _bool_env("USE_MOCK_LLM", False)
    use_mock_payment: bool = _bool_env("USE_MOCK_PAYMENT", True)
    query_rewrite_enabled: bool = _bool_env("QUERY_REWRITE_ENABLED", True)
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

    @property
    def effective_database_url(self) -> str:
        return self.database_url or self.sqlite_database_url

    @property
    def LLM_PROVIDER(self) -> str:
        return self.llm_provider

    @property
    def USE_MOCK_LLM(self) -> bool:
        return self.use_mock_llm

    @property
    def DASHSCOPE_API_KEY(self) -> str:
        return self.dashscope_api_key

    @property
    def QWEN_MODEL(self) -> str:
        return self.qwen_model

    @property
    def QWEN_TOP_P(self) -> float:
        return self.qwen_top_p

    @property
    def QWEN_MAX_TOKENS(self) -> int:
        return self.qwen_max_tokens

    @property
    def QWEN_TIMEOUT_SECONDS(self) -> int:
        return self.qwen_timeout_seconds

    @property
    def QWEN_ENABLE_THINKING(self) -> bool:
        return self.qwen_enable_thinking

    @property
    def EMBEDDING_PROVIDER(self) -> str:
        return self.embedding_provider

    @property
    def EMBEDDING_MODEL(self) -> str:
        return self.embedding_model

    @property
    def EMBEDDING_DIMENSION(self) -> int:
        return self.embedding_dimension

    @property
    def EMBEDDING_TIMEOUT_SECONDS(self) -> int:
        return self.embedding_timeout_seconds

    @property
    def QUERY_REWRITE_ENABLED(self) -> bool:
        return self.query_rewrite_enabled


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
