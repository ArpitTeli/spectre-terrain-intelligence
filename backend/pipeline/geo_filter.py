"""Geometric filter for validating spatial claims.

Catches spatial contradictions in teacher output:
- Claims "outside engagement range" but target is inside
- Claims "avoiding threat" but route passes through it
- Claims "using cover" but waypoints are in open ground

This is deterministic and cheap — runs before judge calls.
"""

import math
import json
from typing import List, Dict, Any


def distance(pos1, pos2):
    """Calculate Euclidean distance between two points."""
    return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)


def point_in_zone(point, zone_pos, zone_radius):
    """Check if a point is within a circular zone."""
    return distance(point, zone_pos) <= zone_radius


def line_intersects_circle(p1, p2, center, radius):
    """Check if a line segment intersects a circle."""
    # Project line onto circle
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    
    fx = p1[0] - center[0]
    fy = p1[1] - center[1]
    
    a = dx * dx + dy * dy
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    
    if a == 0:
        # Line is a point
        return c <= 0
    
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return False
    
    discriminant = math.sqrt(discriminant)
    t1 = (-b - discriminant) / (2 * a)
    t2 = (-b + discriminant) / (2 * a)
    
    # Check if intersection is within line segment
    if (0 <= t1 <= 1) or (0 <= t2 <= 1):
        return True
    
    # Check if line is entirely inside circle
    if t1 < 0 and t2 > 1:
        return True
    
    return False


def check_avoidance_claims(order, contacts):
    """Check if reasoning claims avoidance but target is inside threat radius."""
    flags = []
    
    reasoning = order.get("reasoning", {})
    if isinstance(reasoning, dict):
        reasoning_text = " ".join(str(v) for v in reasoning.values()).lower()
    else:
        reasoning_text = str(reasoning).lower()
    
    target = order.get("target")
    if not target:
        return flags
    
    # Check for avoidance claims
    avoidance_phrases = [
        "outside", "avoid", "stay clear", "out of range", "beyond",
        "keeping distance", "maintaining distance", "outside engagement",
        "safe distance", "clear of"
    ]
    
    claims_avoidance = any(phrase in reasoning_text for phrase in avoidance_phrases)
    
    if claims_avoidance:
        for contact in contacts:
            contact_pos = contact.get("pos", [])
            contact_radius = contact.get("engagement_radius", 500)
            
            if not contact_pos:
                continue
            
            dist = distance(target, contact_pos)
            
            if dist < contact_radius:
                flags.append({
                    "type": "avoidance_contradiction",
                    "unit_id": order.get("unit_id"),
                    "contact_id": contact.get("contact_id"),
                    "distance": round(dist, 1),
                    "engagement_radius": contact_radius,
                    "issue": f"Reasoning claims avoidance but target is {dist:.0f}m inside {contact_radius}m threat radius"
                })
    
    return flags


def check_route_through_threats(order, contacts):
    """Check if route passes through threat zones."""
    flags = []
    
    waypoints = order.get("anchors", [])
    target = order.get("target")
    
    if target and not waypoints:
        waypoints = [target]
    elif not waypoints:
        return flags
    
    for contact in contacts:
        contact_pos = contact.get("pos", [])
        contact_radius = contact.get("engagement_radius", 500)
        
        if not contact_pos:
            continue
        
        # Check each route segment
        for i in range(len(waypoints) - 1):
            p1 = waypoints[i]
            p2 = waypoints[i + 1]
            
            if line_intersects_circle(p1, p2, contact_pos, contact_radius):
                # Check if reasoning mentions this threat
                reasoning = order.get("reasoning", {})
                if isinstance(reasoning, dict):
                    reasoning_text = " ".join(str(v) for v in reasoning.values()).lower()
                else:
                    reasoning_text = str(reasoning).lower()
                
                contact_type = contact.get("type", "unknown")
                if contact_type not in reasoning_text and "threat" not in reasoning_text:
                    flags.append({
                        "type": "unacknowledged_threat",
                        "unit_id": order.get("unit_id"),
                        "contact_id": contact.get("contact_id"),
                        "segment": [p1, p2],
                        "issue": f"Route passes through {contact_type} threat zone without mentioning it"
                    })
    
    return flags


def check_cover_claims(order, raw_grid):
    """Check if reasoning claims cover but waypoints are exposed."""
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
                    "unit_id": order.get("unit_id"),
                    "waypoint": wp,
                    "vegetation": float(vegetation),
                    "buildings": float(buildings),
                    "issue": f"Reasoning claims cover at [{wp[0]}, {wp[1]}] but cell has low vegetation ({vegetation}) and no buildings"
                })
                break  # Only flag once per order
    
    return flags


def validate_example(example, raw_grid=None):
    """Validate a single example's teacher output.
    
    Args:
        example: dict with state_json, teacher_output_json
        raw_grid: optional raw cost grid for cover validation
    
    Returns:
        dict: {passed: bool, flags: list}
    """
    state = json.loads(example["state_json"]) if isinstance(example["state_json"], str) else example["state_json"]
    teacher_output = json.loads(example["teacher_output_json"]) if isinstance(example["teacher_output_json"], str) else example["teacher_output_json"]
    
    contacts = state.get("known_contacts", [])
    orders = teacher_output.get("orders", [])
    
    all_flags = []
    
    for order in orders:
        # Check avoidance claims
        all_flags.extend(check_avoidance_claims(order, contacts))
        
        # Check route through threats
        all_flags.extend(check_route_through_threats(order, contacts))
        
        # Check cover claims
        if raw_grid is not None:
            all_flags.extend(check_cover_claims(order, raw_grid))
    
    return {
        "passed": len(all_flags) == 0,
        "flags": all_flags,
        "flag_count": len(all_flags)
    }


def run_geo_filter(batch_size=None):
    """Run geometric filter on all pending examples.
    
    Returns:
        tuple: (passed_count, failed_count, flagged_examples)
    """
    from .db import get_db, get_examples_by_status, update_geo_filter
    from .config import MAPS_DIR, MAP_NAME
    
    # Load raw grid for cover validation
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


if __name__ == "__main__":
    # Test with sample data
    sample_example = {
        "state_json": {
            "known_contacts": [
                {"contact_id": "enemy_0", "type": "mbt", "pos": [4000, 2000], "engagement_radius": 1200}
            ]
        },
        "teacher_output_json": {
            "orders": [
                {
                    "unit_id": "friendly_0",
                    "target": [4000, 2500],  # Inside threat radius!
                    "anchors": [[3000, 1500], [3500, 2000]],
                    "reasoning": {
                        "situation_assessment": "Enemy MBT at [4000, 2000]",
                        "tactical_choice": "Attacking directly",
                        "tradeoffs": "None considered",
                        "what_if_rejected": "Staying outside engagement range would be slower"
                    }
                }
            ]
        }
    }
    
    result = validate_example(sample_example)
    print(f"Passed: {result['passed']}")
    print(f"Flags: {result['flag_count']}")
    for flag in result["flags"]:
        print(f"  - {flag['type']}: {flag['issue']}")
