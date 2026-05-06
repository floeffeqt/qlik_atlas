from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    env: str
    frontend_dist: Path
    dev_cors_origins: list[str]
    connect_src: str
    fetch_trigger_token: str | None


def load_settings() -> Settings:
    env = os.getenv("APP_ENV", "dev").lower()
    base = Path(__file__).resolve().parents[1]
    frontend_dist = Path(os.getenv("FRONTEND_DIST", str(base / "frontend" / "dist")))
    dev_cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    connect_src = os.getenv("PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
    fetch_trigger_token = os.getenv("FETCH_TRIGGER_TOKEN", "").strip() or None
    return Settings(
        env=env,
        frontend_dist=frontend_dist,
        dev_cors_origins=dev_cors_origins,
        connect_src=connect_src,
        fetch_trigger_token=fetch_trigger_token,
    )


settings = load_settings()


def is_prod() -> bool:
    return settings.env == "prod"
