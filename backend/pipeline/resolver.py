"""Resolution logic for judge verdicts.

With a single Gemini judge, the flow is simpler:
- Judge accepts -> accepted
- Judge rejects -> rejected
- Geo filter failed -> rejected
"""

import json


def resolve_verdict(verdict, geo_status):
    """Resolve the final status based on judge and geo filter.
    
    Args:
        verdict: Judge verdict dict (single judge)
        geo_status: Geometric filter status ("passed" or "failed")
    
    Returns:
        str: Final status ("accepted" or "rejected")
    """
    if geo_status == "failed":
        return "rejected"
    
    if verdict.get("verdict") == "accept":
        return "accepted"
    else:
        return "rejected"


def run_resolver(batch_size=None):
    """Resolve all judged examples.
    
    Returns:
        tuple: (accepted, rejected) counts
    """
    from .db import get_db, get_examples_by_status, update_final_status
    
    conn = get_db()
    judged = get_examples_by_status(conn, "judged")
    
    if batch_size:
        judged = judged[:batch_size]
    
    accepted = 0
    rejected = 0
    
    for example in judged:
        example_id = example["id"]
        
        verdict = json.loads(example["judge_a_verdict"]) if example["judge_a_verdict"] else {}
        geo_status = example["geo_filter_status"]
        
        status = resolve_verdict(verdict, geo_status)
        update_final_status(conn, example_id, status)
        
        if status == "accepted":
            accepted += 1
        else:
            rejected += 1
    
    conn.close()
    return accepted, rejected
