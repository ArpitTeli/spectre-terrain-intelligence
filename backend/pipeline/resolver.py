"""Resolution logic for judge verdicts.

Aggregates judge verdicts into final status:
- Both judges accept -> accepted
- Both judges reject -> rejected
- Judges disagree -> flagged for human review
- Geo filter failed -> rejected
"""

import json
from typing import Dict, Any


def resolve_verdict(verdict_a, verdict_b, geo_status):
    """Resolve the final status based on all checks.
    
    Args:
        verdict_a: Judge A verdict dict
        verdict_b: Judge B verdict dict
        geo_status: Geometric filter status ("passed" or "failed")
    
    Returns:
        str: Final status ("accepted", "rejected", or "flagged")
    """
    # Geo filter takes priority
    if geo_status == "failed":
        return "rejected"
    
    # Both judges must accept
    a_accept = verdict_a.get("verdict") == "accept"
    b_accept = verdict_b.get("verdict") == "accept"
    
    if a_accept and b_accept:
        return "accepted"
    elif not a_accept and not b_accept:
        return "rejected"
    else:
        # Disagreement - flag for human review
        return "flagged"


def run_resolver(batch_size=None):
    """Resolve all judged examples.
    
    Returns:
        tuple: (accepted, rejected, flagged) counts
    """
    from .db import get_db, get_examples_by_status, update_final_status
    
    conn = get_db()
    judged = get_examples_by_status(conn, "judged")
    
    if batch_size:
        judged = judged[:batch_size]
    
    accepted = 0
    rejected = 0
    flagged = 0
    
    for example in judged:
        example_id = example["id"]
        
        # Parse verdicts
        verdict_a = json.loads(example["judge_a_verdict"]) if example["judge_a_verdict"] else {}
        verdict_b = json.loads(example["judge_b_verdict"]) if example["judge_b_verdict"] else {}
        geo_status = example["geo_filter_status"]
        
        # Resolve
        status = resolve_verdict(verdict_a, verdict_b, geo_status)
        update_final_status(conn, example_id, status)
        
        if status == "accepted":
            accepted += 1
        elif status == "rejected":
            rejected += 1
        else:
            flagged += 1
    
    conn.close()
    return accepted, rejected, flagged


def get_resolution_summary(conn):
    """Get a summary of resolution results."""
    stats = {}
    
    # Count by final status
    rows = conn.execute(
        "SELECT final_status, COUNT(*) as count FROM examples GROUP BY final_status"
    ).fetchall()
    stats["by_status"] = {row["final_status"]: row["count"] for row in rows}
    
    # Count by geo filter status
    rows = conn.execute(
        "SELECT geo_filter_status, COUNT(*) as count FROM examples GROUP BY geo_filter_status"
    ).fetchall()
    stats["by_geo"] = {row["geo_filter_status"]: row["count"] for row in rows}
    
    # Total
    stats["total"] = conn.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
    
    return stats


if __name__ == "__main__":
    # Test resolution logic
    test_cases = [
        ({"verdict": "accept"}, {"verdict": "accept"}, "passed", "accepted"),
        ({"verdict": "reject"}, {"verdict": "reject"}, "passed", "rejected"),
        ({"verdict": "accept"}, {"verdict": "reject"}, "passed", "flagged"),
        ({"verdict": "accept"}, {"verdict": "accept"}, "failed", "rejected"),
    ]
    
    print("Testing resolution logic:")
    for va, vb, geo, expected in test_cases:
        result = resolve_verdict(va, vb, geo)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: {va['verdict']} + {vb['verdict']} + geo={geo} -> {result}")
