"""Geometric + doctrinal filter — Guardrail Kernel backed.

Historically this module string-matched a few avoidance phrases against
``order.target`` and knew nothing about the v2 schema (engage_zones,
target_contact, doctrine suitability, weapon reach). It now delegates every
coherence check to the shared Guardrail Kernel in ``backend/guardrails/`` — the
SAME logic the deployed edge runs against live orders — so a training example
this stage rejects is an order the edge would also refuse (train/serve parity).

The public surface is unchanged, so ``run.py`` / ``pipeline_runner.py`` need no
edits:

    validate_example(example, raw_grid=None) -> {"passed","status","flags","flag_count","policy_version"}
    run_geo_filter(batch_size=None)          -> (passed, failed)

Behaviour change worth knowing: the kernel classifies avoidance/route
contradictions as WARN (the example still passes geo and is surfaced to the
judges) rather than the old hard fail. Only physically/doctrinally unexecutable
orders (route enters an avoid_zone, unit can never reach its declared target,
outmatched engager, out-of-bounds coord, unresolved target_contact) are ERRORs
that fail the stage. This is the intended v2 fix for the old filter's
over-rejection.

The one check that stays local is :func:`check_cover_claims`: it needs the map
cost grid (per-cell vegetation/buildings), which is map-specific and not
available at the edge, so it lives here as an offline-only supplement rather
than in the shared kernel. A cover contradiction fails the example, as before.
"""

from guardrails.kernel import evaluate_example, normalize_example
from guardrails.adapters import offline_decision


def check_cover_claims(order, raw_grid):
    """Check if reasoning claims cover but waypoints are exposed.

    Offline-only: depends on the map cost grid. Unchanged from the original
    filter — kept here because the kernel is deliberately map-independent.
    """
    flags = []

    reasoning = order.get("reasoning", {})
    if isinstance(reasoning, dict):
        reasoning_text = " ".join(str(v) for v in reasoning.values()).lower()
    else:
        reasoning_text = str(reasoning).lower()

    cover_phrases = [
        "cover", "concealment", "forest", "trees", "vegetation",
        "building", "urban", "structures"
    ]

    claims_cover = any(phrase in reasoning_text for phrase in cover_phrases)

    if claims_cover and raw_grid is not None:
        waypoints = order.get("anchors", [])
        target = order.get("target")
        if target:
            waypoints = waypoints + [target]

        cell_size = 64  # meters per cell
        grid_dim = raw_grid.shape[0]

        for wp in waypoints:
            gx = int(wp[0] / cell_size) % grid_dim
            gy = int(wp[1] / cell_size) % grid_dim

            # Check vegetation and buildings
            vegetation = raw_grid[gy, gx, 2] if raw_grid.shape[2] > 2 else 0
            buildings = raw_grid[gy, gx, 3] if raw_grid.shape[2] > 3 else 0

            if vegetation < 3 and buildings < 1:
                # No cover but claims cover
                flags.append({
                    "type": "cover_contradiction",
                    "severity": "error",
                    "category": "cover",
                    "unit_id": order.get("unit_id"),
                    "waypoint": wp,
                    "vegetation": float(vegetation),
                    "buildings": float(buildings),
                    "issue": f"Reasoning claims cover at [{wp[0]}, {wp[1]}] but "
                             f"cell has low vegetation ({vegetation}) and no buildings"
                })
                break  # Only flag once per order

    return flags


def validate_example(example, raw_grid=None):
    """Validate a single example's teacher output via the Guardrail Kernel,
    plus the offline-only cover check when a map grid is available.

    Returns the same dict shape the pipeline expects:
        {"passed", "status", "flags", "flag_count", "policy_version"}
    `passed` is True when there are no ERROR findings and no cover contradiction
    (WARN-only still passes; the judges see the warnings).
    """
    report = evaluate_example(example)

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

    # Offline-only cover check (map-grid dependent), per order.
    cover_flags = []
    if raw_grid is not None:
        _, orders = normalize_example(example)
        for order in orders:
            cover_flags.extend(check_cover_claims(order, raw_grid))
    flags.extend(cover_flags)

    passed = report.ok and not cover_flags
    if not report.ok or cover_flags:
        status = "reject"
    elif report.warnings:
        status = "flag"
    else:
        status = "accept"

    return {
        "passed": passed,
        "status": status,
        "flags": flags,
        "flag_count": len(flags),
        "policy_version": report.policy_version,
    }


def run_geo_filter(batch_size=None):
    """Run the geometric filter on all pending examples.

    Same DB contract as before: pulls ``teacher_done`` rows, writes the result
    + status via ``update_geo_filter``, returns ``(passed, failed)``.
    """
    from .db import get_db, get_examples_by_status, update_geo_filter
    from .config import MAPS_DIR, MAP_NAME

    # Load raw grid for the offline-only cover validation.
    raw_grid = None
    grid_path = MAPS_DIR / f"{MAP_NAME}_costgrid.npz"
    if grid_path.exists():
        import numpy as np
        raw_grid = np.load(grid_path)["grid"]

    conn = get_db()
    pending = get_examples_by_status(conn, "teacher_done")

    if batch_size:
        pending = pending[:batch_size]

    passed = 0
    failed = 0

    for example in pending:
        example_id = example["id"]

        result = validate_example(example, raw_grid)

        if result["passed"]:
            update_geo_filter(conn, example_id, None, "passed")
            passed += 1
        else:
            update_geo_filter(conn, example_id, result, "failed")
            failed += 1

    conn.close()
    return passed, failed
