"""Per-user configuration for the packaged installation."""

import json
import os
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("LOCAL_PROJECT_MCP_HOME")
    if override:
        return Path(override)
    return Path(os.environ["LOCALAPPDATA"]) / "LocalProjectMcp"


def load_config() -> dict:
    path = data_dir() / "config.json"
    if not path.is_file():
        raise RuntimeError("Local Project MCP is not configured. Run 'local-project-mcp setup' first.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(config: dict) -> None:
    path = data_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_root() -> Path:
    root = Path(load_config()["project_root"])
    if not root.is_dir():
        raise RuntimeError(f"Selected project folder is unavailable: {root}")
    return root


def resolve(path: str) -> Path:
    candidate = Path(path)
    return (candidate if candidate.is_absolute() else project_root() / candidate).resolve()
