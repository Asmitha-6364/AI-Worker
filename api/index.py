"""
Vercel Serverless Entrypoint for AcmeOps ERP.
"""

import sys
from pathlib import Path

# Ensure root project directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from acme_ops.app import app

# Expose app for Vercel ASGI runtime
__all__ = ["app"]
