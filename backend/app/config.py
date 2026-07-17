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
    adr_output_dir: str = "../adrs"

    @property
    def adr_dir(self) -> Path:
        p = Path(self.adr_output_dir)
        if not p.is_absolute():
            p = (BACKEND_DIR / p).resolve()
        return p

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
