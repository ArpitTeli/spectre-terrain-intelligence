"""SPECTRE Training Pipeline.

Generates synthetic training data for the tactical AI model.
All models accessed via OpenRouter for unified billing.
"""

from .config import validate_config, TEACHER_MODEL, JUDGE_A_MODEL, JUDGE_B_MODEL
from .db import init_db, get_db, get_stats
from .sampler import generate_scenario, generate_batch
from .teacher import generate_teacher_output
from .geo_filter import validate_example
from .judge import judge_example
from .resolver import resolve_verdict
from .export import export_training_set

__all__ = [
    "validate_config",
    "init_db",
    "get_db",
    "get_stats",
    "generate_scenario",
    "generate_batch",
    "generate_teacher_output",
    "validate_example",
    "judge_example",
    "resolve_verdict",
    "export_training_set",
]
