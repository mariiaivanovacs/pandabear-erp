"""Central settings. Everything env-driven, nothing hardcoded into the graph."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # storage
    data_dir: Path = PROJECT_ROOT / "data"
    metadata_db: Path = PROJECT_ROOT / "data" / "pandabear.db"
    vault_path: Path = PROJECT_ROOT / "data" / "vault.enc"
    vault_key_path: Path = PROJECT_ROOT / "data" / "vault.key"
    chroma_dir: Path = PROJECT_ROOT / "data" / "memory"
    tools_dir: Path = PROJECT_ROOT / "tools"

    # local model (Ollama, OpenAI-compatible endpoint)
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    local_model: str = "qwen3:8b"

    # cloud model (funded by the $200 credit; used for baseline, tool generation,
    # and as automatic fallback when the local model fails the quality bar)
    openai_api_key: str = ""
    cloud_model: str = "gpt-4.1"
    cloud_model_small: str = "gpt-4o-mini"

    # routing behavior: "local" | "cloud" | "auto"
    # auto = try local first, fall back to cloud on malformed/failed tool calls
    model_mode: str = "auto"

    # external systems (values themselves live in the vault, not here —
    # these are only bootstrap paths/refs)
    firebase_service_account_path: str = ""   # used once to seed the vault
    firebase_project_id: str = ""
    telegram_bot_token: str = ""              # used once to seed the vault

    # execution limits (mirrors description.md tool spec)
    tool_timeout_seconds: int = 30
    max_agent_turns: int = 4                  # evaluator.py-style hard bound

    # GitHub push -> AGENTS.md pipeline. repo_path is the local clone the
    # webhook diffs against (git fetch + git diff run here — no GitHub API
    # token needed, works for private repos too). github_webhook_secret lives
    # in the vault like every other credential; not read from here.
    repo_path: Path = PROJECT_ROOT
    agents_md_path: Path = PROJECT_ROOT / "AGENTS.md"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
