from app.config import DEFAULT_OPENAI_MODEL, load_settings

ENV_NAMES = ["MAX_TASKS", "MAX_CONCURRENCY", "TASK_TIMEOUT_S", "MAX_TOTAL_TOKENS", "DATABASE_PATH",
             "OPENAI_API_KEY", "OPENAI_MODEL", "DEMO_DELAY_S", "CORS_ORIGINS"]


def test_defaults_match_the_spec(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()

    assert (settings.max_tasks, settings.max_concurrency) == (8, 3)
    assert (settings.task_timeout_s, settings.max_total_tokens) == (60, 60000)
    assert settings.database_path == "switchboard.db"
    assert settings.openai_api_key == "" and settings.openai_model == DEFAULT_OPENAI_MODEL
    assert settings.demo_delay_s == 0.8
    assert settings.cors_origins == ("http://localhost:3000",)


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENCY", "5")
    monkeypatch.setenv("OPENAI_MODEL", "other-model")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    settings = load_settings()

    assert settings.max_concurrency == 5
    assert settings.openai_model == "other-model"
    assert settings.cors_origins == ("http://a.test", "http://b.test")
