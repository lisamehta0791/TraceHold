"""TraceHold backend. Loads settings from the repository's .env file (if any)
before anything reads the environment. Values already set in the environment win."""
import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_load_env_file(ENV_FILE)
