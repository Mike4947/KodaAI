from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_client_id: str = ""
    github_client_secret: str = ""
    fernet_key: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_num_ctx: int = 32768

    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    data_dir: str = "data"
    repos_dir: str = ""
    max_agent_turns: int = 30
    max_file_read_lines: int = 300
    max_file_size_bytes: int = 512_000

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import os
        import tempfile

        if not self.repos_dir:
            self.repos_dir = os.path.join(tempfile.gettempdir(), "kodaai", "repos")


settings = Settings()
