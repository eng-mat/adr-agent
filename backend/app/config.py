"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root is two parents up from this file's parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    bedrock_model: str = "anthropic.claude-opus-4-8-v1:0"
    aws_region: str = "us-east-1"
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    @property
    def active_model(self) -> str:
        return {
            "bedrock": self.bedrock_model,
            "gemini": self.gemini_model,
        }.get(self.llm_provider, self.anthropic_model)

    @property
    def llm_ready(self) -> bool:
        """Whether the selected provider has the credentials it needs to run."""
        if self.llm_provider == "gemini":
            return bool(self.google_api_key) and not self.google_api_key.startswith(
                "your-google"
            )
        if self.llm_provider == "bedrock":
            return True  # relies on the standard AWS credential chain
        return bool(self.anthropic_api_key) and not self.anthropic_api_key.startswith(
            "sk-ant-your-key"
        )

    @property
    def llm_key_env(self) -> str:
        return {
            "gemini": "GOOGLE_API_KEY",
            "bedrock": "AWS credentials",
        }.get(self.llm_provider, "ANTHROPIC_API_KEY")

    # --- Publishing ---
    github_token: str = ""
    github_repo: str = ""
    github_branch: str = "main"
    confluence_base_url: str = ""
    confluence_user: str = ""
    confluence_api_token: str = ""
    confluence_space_key: str = ""

    # --- Storage ---
    # All four accept absolute paths so they can point at a mounted volume
    # (e.g. a CMEK GCS bucket on Cloud Run, whose filesystem is otherwise ephemeral).
    adr_output_dir: str = "../adrs"       # env ADR_OUTPUT_DIR
    data_dir: str = ""                    # env DATA_DIR       (admin runtime config)
    knowledge_dir: str = ""               # env KNOWLEDGE_DIR  (uploaded standards)
    skills_dir: str = ""                  # env SKILLS_DIR     (agent skills)

    def _resolve(self, value: str, default: Path) -> Path:
        if not value:
            return default
        p = Path(value)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def adr_dir(self) -> Path:
        return self._resolve(self.adr_output_dir, (BACKEND_DIR / "../adrs").resolve())

    @property
    def data_path(self) -> Path:
        return self._resolve(self.data_dir, BACKEND_DIR / "data")

    @property
    def knowledge_path(self) -> Path:
        return self._resolve(self.knowledge_dir, BACKEND_DIR / "app" / "knowledge")

    @property
    def skills_path(self) -> Path:
        return self._resolve(self.skills_dir, BACKEND_DIR / "app" / "skills")

    @property
    def local_mirror_dir(self) -> Path:
        return (BACKEND_DIR / ".local-mirror").resolve()

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token and self.github_repo)

    @property
    def confluence_configured(self) -> bool:
        return bool(
            self.confluence_base_url
            and self.confluence_user
            and self.confluence_api_token
            and self.confluence_space_key
        )


settings = Settings()
