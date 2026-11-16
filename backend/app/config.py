"""Settings read from environment variables. Defaults match SPEC.md."""
import os
from dataclasses import dataclass

# Small, cheap model from the OpenAI models page; override with OPENAI_MODEL.
DEFAULT_OPENAI_MODEL = "gpt-6-luna"


@dataclass(frozen=True)
class Settings:
    max_tasks: int = 8
    max_concurrency: int = 3
    task_timeout_s: float = 60
    max_total_tokens: int = 60000
    database_path: str = "switchboard.db"
    openai_api_key: str = ""  # empty means demo mode
    openai_model: str = DEFAULT_OPENAI_MODEL
    demo_delay_s: float = 0.8
    cors_origins: tuple = ("http://localhost:3000",)


def load_settings() -> Settings:
    env = os.environ
    defaults = Settings()
    return Settings(
        max_tasks=int(env.get("MAX_TASKS", defaults.max_tasks)),
        max_concurrency=int(env.get("MAX_CONCURRENCY", defaults.max_concurrency)),
        task_timeout_s=float(env.get("TASK_TIMEOUT_S", defaults.task_timeout_s)),
        max_total_tokens=int(env.get("MAX_TOTAL_TOKENS", defaults.max_total_tokens)),
        database_path=env.get("DATABASE_PATH", defaults.database_path),
        openai_api_key=env.get("OPENAI_API_KEY", ""),
        openai_model=env.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
        demo_delay_s=float(env.get("DEMO_DELAY_S", defaults.demo_delay_s)),
        cors_origins=tuple(
            origin.strip()
            for origin in env.get("CORS_ORIGINS", ",".join(defaults.cors_origins)).split(",")
            if origin.strip()
        ),
    )
