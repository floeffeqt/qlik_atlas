from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os


@dataclass(frozen=True)
class Settings:
    env: str
    data_dir: Path
    usage_dir: Path
    scripts_dir: Path
    data_connections_file: Path
    frontend_dist: Path
    spaces_file: Optional[Path]
    dev_cors_origins: list[str]
    connect_src: str
    fetch_trigger_token: Optional[str]


def load_settings() -> Settings:
    env = os.getenv("APP_ENV", "dev").lower()
    base = Path(__file__).resolve().parents[2]

    default_data_dir = base / "output" / "lineage_success"
    fallback_data_dir = base / "output" / "lineage"
    data_dir_default = default_data_dir if default_data_dir.exists() else fallback_data_dir
    data_dir = Path(os.getenv("LINEAGE_DATA_DIR", str(data_dir_default)))

    usage_dir = Path(os.getenv("APP_USAGE_DIR", str(base / "output" / "appusage")))
    scripts_dir = Path(os.getenv("APP_SCRIPTS_DIR", str(base / "output" / "appscripts")))
    data_connections_file = Path(
        os.getenv(
            "DATA_CONNECTIONS_FILE",
            str(base / "output" / "lineage" / "tenant_data_connections.json"),
        )
    )

    frontend_dist = Path(os.getenv("FRONTEND_DIST", str(base / "frontend" / "dist")))
    spaces_env = os.getenv("SPACES_FILE", "")
    spaces_candidates = [
        Path(spaces_env) if spaces_env else None,
        base / "output" / "spaces.json",
        base / "data" / "spaces.json",
    ]
    spaces_file = next((p for p in spaces_candidates if p and p.exists()), None)
    dev_cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    connect_src = "http://127.0.0.1:8000"
    fetch_trigger_token = os.getenv("FETCH_TRIGGER_TOKEN", "").strip() or None
    return Settings(
        env=env,
        data_dir=data_dir,
        usage_dir=usage_dir,
        scripts_dir=scripts_dir,
        data_connections_file=data_connections_file,
        frontend_dist=frontend_dist,
        spaces_file=spaces_file,
        dev_cors_origins=dev_cors_origins,
        connect_src=connect_src,
        fetch_trigger_token=fetch_trigger_token,
    )


settings = load_settings()


def is_prod() -> bool:
    return settings.env == "prod"
