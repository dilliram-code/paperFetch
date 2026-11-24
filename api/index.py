"""Vercel Serverless Function entry point for FastAPI."""
from backend.app.main import app

# Vercel's Python runtime requires the ASGI application instance as `app`
__all__ = ["app"]
