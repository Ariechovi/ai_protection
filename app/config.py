from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ai_protection"
    app_env: str = "dev"

    database_url: str = ""
    redis_url: str = "redis://127.0.0.1:16379/0"

    model_name: str = "deepseek-chat"
    model_base_url: str | None = "https://api.deepseek.com"
    model_api_key: str = ""

    embedding_model: str = "qwen3.7-text-embedding"
    embedding_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    vector_dim: int = 1024

    target_api_key: str = ""
    max_test_cases: int = 6
    target_timeout_seconds: float = 20.0
    judge_timeout_seconds: float = 60.0
    memory_timeout_seconds: float = 15.0
    agent_runtime_mode: Literal["llm", "deterministic"] = "llm"
    agent_max_steps: int = 6
    agent_planner_timeout_seconds: float = 20.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

