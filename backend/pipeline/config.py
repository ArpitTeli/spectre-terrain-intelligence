"""SPECTRE Training Pipeline Configuration.

API keys are loaded from environment variables or a .env file.
All models accessed via OpenRouter for unified billing.
"""

import os
from pathlib import Path

# Try to load from .env file if python-dotenv is available
# Look for .env in the backend directory, then the app root
try:
    from dotenv import load_dotenv
    backend_dir = Path(__file__).parent
    app_root = backend_dir.parent
    # Try backend/.env first, then app root .env
    for env_path in [backend_dir / ".env", app_root / ".env"]:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    pass

# API Keys (from environment variables)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Model selection (OpenRouter format: provider/model)
TEACHER_MODEL = os.getenv("TEACHER_MODEL", "anthropic/claude-3.5-sonnet")
JUDGE_A_MODEL = os.getenv("JUDGE_A_MODEL", "anthropic/claude-3.5-haiku")
JUDGE_B_MODEL = os.getenv("JUDGE_B_MODEL", "openai/gpt-4o-mini")

# Pipeline settings
TARGET_EXAMPLES = int(os.getenv("TARGET_EXAMPLES", "1000"))
DB_PATH = Path(__file__).parent / "spectre_training.db"
MAP_NAME = os.getenv("MAP_NAME", "stratis")

# Generation settings
MAX_RETRIES = 3
BATCH_SIZE = 10  # examples per API batch call

# Paths
SCRIPTS_DIR = Path(__file__).parent
MAPS_DIR = SCRIPTS_DIR.parent.parent / "public" / "maps"

# Unit types available in the system
UNIT_TYPES = [
    "mbt", "ifv", "apc", "mrap", "light", "truck",
    "spg", "spaa", "eng",
    "infantry", "helicopter", "boat"
]

# OpenRouter API settings
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Validate API keys
def validate_config():
    """Check that required API keys are set."""
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY not set.\n"
            "Get an API key at https://openrouter.ai/keys\n"
            "Then set: export OPENROUTER_API_KEY='sk-or-...'"
        )
    return True
