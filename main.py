"""
Main FastAPI entrypoint for AcmeOps ERP.
Exposes the `app` instance for Vercel, Uvicorn, and ASGI servers.
"""

from acme_ops.app import app

__all__ = ["app"]
