"""Paths relative to the checkout, independent of the current working directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
MODELS_DIR = RUNTIME_DIR / "models"
ARTIFACTS_DIR = RUNTIME_DIR / "artifacts"
