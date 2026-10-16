"""Packaged browser assets and writable runtime locations."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "web" / "templates"
STATIC_DIR = PACKAGE_DIR / "web" / "static"
# Checkouts retain their runtime directory; installed wheels use a writable user cache.
_default_runtime = (PROJECT_ROOT / "runtime" if (PROJECT_ROOT / "pyproject.toml").is_file()
                    else Path.home() / ".yolo-studio" / "runtime")
RUNTIME_DIR = Path(os.environ.get("YOLO_STUDIO_RUNTIME_DIR", _default_runtime)).expanduser().resolve()
MODELS_DIR = RUNTIME_DIR / "models"
ARTIFACTS_DIR = RUNTIME_DIR / "artifacts"
