"""SPECTRE Guardrails — one deterministic kernel, two deployment adapters.

    from guardrails import evaluate, evaluate_example
    from guardrails import offline_decision, online_decision

The kernel (:mod:`guardrails.kernel`) is pure and shared. The adapters
(:mod:`guardrails.adapters`) turn a Report into the action each context needs:
reject/flag for offline data generation, block/allow for edge command issuance.
See ``README.md`` for the architecture and the train/serve parity guarantee.
"""

from .policy import POLICY_VERSION
from .kernel import (
    Finding, Report, evaluate, evaluate_example, normalize_example,
    ERROR, WARN, SCHEMA, DOCTRINE, GEOMETRY, REASONING,
)
from .adapters import offline_decision, online_decision, OfflineDecision, OnlineDecision

__all__ = [
    "POLICY_VERSION",
    "Finding", "Report", "evaluate", "evaluate_example", "normalize_example",
    "ERROR", "WARN", "SCHEMA", "DOCTRINE", "GEOMETRY", "REASONING",
    "offline_decision", "online_decision", "OfflineDecision", "OnlineDecision",
]
