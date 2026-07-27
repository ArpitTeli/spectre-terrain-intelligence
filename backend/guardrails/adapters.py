"""Policy adapters — turn a kernel :class:`Report` into a context-specific action.

The kernel decides *what is wrong* (deterministically, identically on both
sides). The adapters decide *what to do about it*, and only that differs between
the two deployments:

  * **offline** (synthetic data generation): an ERROR means the example is
    unfit for training — reject it (regenerate rather than hand-patch, so we
    never inject human tactical judgement into the model's own signal). A WARN
    means "spatially/doctrinally plausible but worth a second look" — flag it
    for the dual-judge / human-review stage rather than dropping it.

  * **online** (deployed edge Tasking Layer): an unsafe order must never reach
    the Arma bridge. A geometry/doctrine ERROR blocks the order and falls the
    unit back to a safe default (hold / last acknowledged order), surfacing the
    reason to the operator. A WARN is advisory — the order proceeds but the
    operator is told. Schema ERRORs at the edge (e.g. a coordinate out of the
    map) also block, since a malformed command is not executable.

Both adapters read the *same* Report, so the mapping is the only thing that
varies — the judgement of right vs. wrong is shared.
"""

from dataclasses import dataclass, field
from typing import List

from .kernel import Report, Finding, ERROR, GEOMETRY, DOCTRINE, SCHEMA


# --------------------------------------------------------------------------- #
# Offline (dataset generation)
# --------------------------------------------------------------------------- #
@dataclass
class OfflineDecision:
    status: str                 # "accept" | "flag" | "reject"
    reason: str
    report: Report
    errors: List[Finding] = field(default_factory=list)
    warnings: List[Finding] = field(default_factory=list)

    @property
    def accepted(self):
        return self.status == "accept"

    def to_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "policy_version": self.report.policy_version,
            "errors": [f.to_dict() for f in self.errors],
            "warnings": [f.to_dict() for f in self.warnings],
        }


def offline_decision(report: Report) -> OfflineDecision:
    """Map a Report to a data-generation verdict.

    ERROR (any category) -> reject.  WARN only -> flag.  clean -> accept.
    """
    errors, warnings = report.errors, report.warnings
    if errors:
        status, reason = "reject", (
            f"{len(errors)} guardrail error(s): "
            + "; ".join(sorted({f.code for f in errors}))
        )
    elif warnings:
        status, reason = "flag", (
            f"{len(warnings)} warning(s) for review: "
            + "; ".join(sorted({f.code for f in warnings}))
        )
    else:
        status, reason = "accept", "clean"
    return OfflineDecision(status, reason, report, errors, warnings)


# --------------------------------------------------------------------------- #
# Online (edge command issuance)
# --------------------------------------------------------------------------- #
# At the edge, an unsafe order is worse than no order. These categories block:
# a doctrine mismatch or geometric violation is tactically unsafe, and a schema
# error means the command can't be executed as written.
_BLOCKING_CATEGORIES = frozenset({GEOMETRY, DOCTRINE, SCHEMA})


@dataclass
class OnlineDecision:
    action: str                 # "allow" | "block"
    fallback: str               # suggested safe fallback when blocked
    reason: str
    report: Report
    blocking: List[Finding] = field(default_factory=list)
    advisories: List[Finding] = field(default_factory=list)

    @property
    def allowed(self):
        return self.action == "allow"

    def to_dict(self):
        return {
            "action": self.action,
            "fallback": self.fallback,
            "reason": self.reason,
            "policy_version": self.report.policy_version,
            "blocking": [f.to_dict() for f in self.blocking],
            "advisories": [f.to_dict() for f in self.advisories],
        }


def online_decision(report: Report, fallback: str = "HOLD") -> OnlineDecision:
    """Map a Report to an edge action.

    Any ERROR in a blocking category (geometry/doctrine/schema) blocks the order
    and recommends a fail-safe fallback. Everything else is advisory: the order
    is allowed but its warnings are surfaced to the operator.

    `fallback` is the safe action to take when blocked (default HOLD; a caller
    with a last-acknowledged order may pass e.g. "RESUME_LAST").
    """
    blocking = [
        f for f in report.errors if f.category in _BLOCKING_CATEGORIES
    ]
    advisories = [f for f in report.findings if f not in blocking]

    if blocking:
        reason = (
            f"{len(blocking)} blocking violation(s): "
            + "; ".join(sorted({f.code for f in blocking}))
        )
        return OnlineDecision("block", fallback, reason, report, blocking, advisories)

    reason = "clean" if not advisories else (
        f"allowed with {len(advisories)} advisory(ies): "
        + "; ".join(sorted({f.code for f in advisories}))
    )
    return OnlineDecision("allow", fallback, reason, report, [], advisories)
