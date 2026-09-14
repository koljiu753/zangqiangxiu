"""Expose the AI FastAPI application to the Vercel Python runtime."""

from app.main import app

__all__ = ["app"]
