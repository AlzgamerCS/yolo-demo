"""Compatibility import for existing ASGI launch commands."""
from .web.app import app, create_app

__all__ = ["app", "create_app"]
