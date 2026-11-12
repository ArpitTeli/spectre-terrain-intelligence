"""SPECTRE Training Pipeline Configuration.

API keys are loaded from environment variables or a .env file.
All models accessed via OpenRouter for unified billing.
"""

import os
from pathlib import Path

# Try to load from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # backend/.env (written by the desktop app) and the repo-root .env
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

# API Keys (from environment variables)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Model selection
TEACHER_MODEL = os.getenv("TEACHER_MODEL", "anthropic/claude-3.5-sonnet")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-2.5-pro")

# Pipeline settings
TARGET_EXAMPLES = int(os.getenv("TARGET_EXAMPLES", "1000"))
DB_PATH = Path(__file__).parent / "spectre_training.db"
MAP_NAME = os.getenv("MAP_NAME", "stratis")

# Generation settings
MAX_RETRIES = 3
BATCH_SIZE = 10  # examples per API batch call

# Paths
SCRIPTS_DIR = Path(__file__).parent.parent
MAPS_DIR = SCRIPTS_DIR.parent / "public" / "maps"

# Unit types available in the system
UNIT_TYPES = [
    "mbt", "ifv", "apc", "mrap", "light", "truck",
    "spg", "spaa", "eng",
    "infantry", "helicopter", "boat"
]

# OpenRouter API settings
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Policy: no Chinese-origin models anywhere in the SPECTRE defense stack, including
# teacher models whose output trains the deployed model (provenance / procurement risk).
BLOCKED_MODEL_MARKERS = (
    "moonshot", "kimi", "deepseek", "qwen", "alibaba", "z-ai", "zhipu", "glm",
    "minimax", "baidu", "ernie", "tencent", "hunyuan", "bytedance", "doubao",
    "01-ai", "yi-", "stepfun", "baichuan",
)


def _check_model_provenance(name, value):
    low = (value or "").lower()
    for marker in BLOCKED_MODEL_MARKERS:
        if marker in low:
            raise ValueError(
                f"{name}={value!r} looks like a Chinese-origin model ('{marker}'). "
                "SPECTRE policy excludes these from the defense stack. Pick another model."
            )


# Validate API keys
def validate_config():
    """Check that required API keys are set and the models are allowed."""
    _check_model_provenance("TEACHER_MODEL", os.getenv("TEACHER_MODEL", TEACHER_MODEL))
    _check_model_provenance("JUDGE_MODEL", os.getenv("JUDGE_MODEL", JUDGE_MODEL))
    if not os.getenv("GEMINI_API_KEY", GEMINI_API_KEY):
        raise ValueError(
            "GEMINI_API_KEY not set (used by the judge).\n"
            "Get a key at https://aistudio.google.com/apikey"
        )
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY not set.\n"
            "Get an API key at https://openrouter.ai/keys\n"
            "Then set: export OPENROUTER_API_KEY='sk-or-...'"
        )
    return True
