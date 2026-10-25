"""
Configuration module for the Autonomous AI Task Worker.
Loads settings from environment variables with sensible defaults.
Supports both local execution and Vercel serverless environments.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Detect serverless environment (Vercel / AWS Lambda)
IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

# Base paths
BASE_DIR = Path(__file__).resolve().parent

if IS_SERVERLESS:
    # On Vercel / Lambda, root filesystem is read-only.
    # Writable files (SQLite database, traces) must reside in /tmp.
    DATA_DIR = Path("/tmp")
    DB_PATH = DATA_DIR / "acme_ops.db"
    DOCUMENTS_DIR = BASE_DIR / "documents"
    TRACES_DIR = DATA_DIR / "traces"
    SCREENSHOTS_DIR = TRACES_DIR / "screenshots"
else:
    DOCUMENTS_DIR = BASE_DIR / "documents"
    TRACES_DIR = BASE_DIR / "traces"
    SCREENSHOTS_DIR = TRACES_DIR / "screenshots"
    DB_PATH = BASE_DIR / "acme_ops.db"

# Ensure runtime directories exist safely without throwing on read-only systems
try:
    if not IS_SERVERLESS:
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

# AcmeOps Mock Application Settings
ACME_HOST = os.getenv("ACME_HOST", "127.0.0.1")
ACME_PORT = int(os.getenv("ACME_PORT", "8000"))
ACME_BASE_URL = os.getenv("ACME_BASE_URL", f"http://{ACME_HOST}:{ACME_PORT}")
ACME_ADMIN_USERNAME = os.getenv("ACME_ADMIN_USERNAME", "admin")
ACME_ADMIN_PASSWORD = os.getenv("ACME_ADMIN_PASSWORD", "acmepass123")
ACME_SECRET_KEY = os.getenv("ACME_SECRET_KEY", "super-secret-acme-ops-token-key-2026")

# Agent Settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")  # 'openai', 'gemini', 'anthropic', 'deterministic'
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# Browser Settings
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() in ("true", "1", "yes")
BROWSER_SLOW_MO = int(os.getenv("BROWSER_SLOW_MO", "200"))  # ms delay for visual demo readability

# Agent Limits
MAX_STEPS = int(os.getenv("MAX_STEPS", "25"))
MAX_RETRIES_PER_FAILURE = int(os.getenv("MAX_RETRIES_PER_FAILURE", "3"))
