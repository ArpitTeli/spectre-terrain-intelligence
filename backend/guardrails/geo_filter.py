"""Drop-in replacement for the pipeline's Stage-4 geometric filter, backed by
the Guardrail Kernel.

The original ``backend/pipeline/geo_filter.py`` was v1: it string-matched a few
avoidance phrases against ``order.target`` and knew nothing about engage_zones,
target_contact, doctrine suitability, or engagement reachability. This module
keeps the *exact same public surface* the pipeline calls —

    validate_example(example, raw_grid=None) -> {"passed", "flags", "flag_count"}
    run_geo_filter(batch_size=None)          -> (passed, failed)

— so ``run.py`` and ``db.py`` need no changes, but every spatial/doctrine
judgement now comes from :func:`guardrails.kernel.evaluate` via the offline
adapter. That is the whole point: the pipeline that filters training data and
the edge that filters live commands run the identical kernel.

Installation in the pipeline repo: copy the ``guardrails/`` package into
``backend/`` (or add it to PYTHONPATH) and replace the body of
``backend/pipeline/geo_filter.py`` with::

    from guardrails.geo_filter import validate_example, run_geo_filter

`raw_grid` (the cover-vs-vegetation check) is accepted for signature
compatibility. Cover validation is intentionally out of the kernel — it depends
on the map cost grid, which the edge doesn't carry — so it is not reintroduced
here; the kernel's contribution is the map-independent coherence layer.
"""

from .kernel import evaluate_example
from .adapters import offline_decision


def validate_example(example, raw_grid=None):
    """Kernel-backed replacement for the pipeline's validate_example.

    Returns the same dict shape the old filter returned:
        {"passed": bool, "flags": [ ... ], "flag_count": int}

    `passed` is True only when the offline adapter accepts (no ERROR findings).
    Both ERROR and WARN findings are surfaced in `flags` (each tagged with its
    severity) so the DB's geo_filter_result keeps the full picture for review.
    """
    report = evaluate_example(example)
    decision = offline_decision(report)

    flags = []
    for f in report.findings:
        flags.append({
            "type": f.code,
            "severity": f.severity,
            "category": f.category,
            "unit_id": f.unit_id,
            "issue": f.message,
            **f.data,
        })

    return {
        "passed": report.ok,                 # WARN-only still passes geo; judges see it
        "status": decision.status,           # accept | flag | reject
        "flags": flags,
        "flag_count": len(flags),
        "policy_version": report.policy_version,
    }


def run_geo_filter(batch_size=None):
    """Kernel-backed replacement for the pipeline's run_geo_filter.

    Same DB contract as the original: pulls ``teacher_done`` rows, writes the
    result + status via ``update_geo_filter``, returns ``(passed, failed)``.
    """
    from pipeline.db import get_db, get_examples_by_status, update_geo_filter

    conn = get_db()
    pending = get_examples_by_status(conn, "teacher_done")
    if batch_size:
        pending = pending[:batch_size]

    passed = failed = 0
    for example in pending:
        result = validate_example(example)
        if result["passed"]:
            update_geo_filter(conn, example["id"], None, "passed")
            passed += 1
        else:
            update_geo_filter(conn, example["id"], result, "failed")
            failed += 1

    conn.close()
    return passed, failed
