"""Scenario sampler for synthetic training data.

Generates random but realistic battlefield scenarios:
- Terrain window selection
- Unit composition (2-6 friendly units)
- Enemy composition (1-4 threats)
- Objective assignment
- Known contacts with engagement radii
"""

import random
import json
import numpy as np
from pathlib import Path

from .config import MAP_NAME, MAPS_DIR, UNIT_TYPES


# Unit compositions (2-6 units per scenario)
UNIT_COMPOSITIONS = [
    # Light recon
    ["light", "infantry"],
    ["mrap", "infantry"],
    # Standard patrol
    ["ifv", "infantry", "infantry"],
    ["mrap", "light", "infantry"],
    # Mechanized
    ["mbt", "ifv", "infantry"],
    ["mbt", "apc", "infantry", "infantry"],
    ["ifv", "apc", "infantry", "infantry"],
    # Heavy assault
    ["mbt", "ifv", "apc", "infantry", "infantry"],
    ["mbt", "ifv", "mrap", "infantry", "infantry"],
    # Combined arms
    ["mbt", "ifv", "apc", "mrap", "light", "infantry"],
    ["mbt", "ifv", "truck", "infantry", "infantry", "infantry"],
    # Support
    ["spg", "ifv", "mrap", "infantry", "infantry"],
    ["spaa", "ifv", "apc", "infantry"],
    # Aviation
    ["helicopter", "infantry", "infantry"],
    ["helicopter", "mrap", "light", "infantry"],
]

# Enemy compositions
ENEMY_COMPOSITIONS = [
    # Light resistance
    [{"type": "infantry", "count": 2}],
    [{"type": "mrap", "count": 1}],
    [{"type": "light", "count": 2}],
    # Medium threat
    [{"type": "ifv", "count": 1}, {"type": "infantry", "count": 2}],
    [{"type": "apc", "count": 1}, {"type": "infantry", "count": 3}],
    [{"type": "mrap", "count": 2}, {"type": "infantry", "count": 2}],
    # Heavy threat
    [{"type": "mbt", "count": 1}],
    [{"type": "mbt", "count": 1}, {"type": "ifv", "count": 1}],
    [{"type": "mbt", "count": 2}],
    # Mixed
    [{"type": "mbt", "count": 1}, {"type": "ifv", "count": 2}, {"type": "infantry", "count": 3}],
    [{"type": "apc", "count": 2}, {"type": "infantry", "count": 4}],
]

# Objectives
OBJECTIVES = ["attack", "defend", "patrol", "evacuate", "recon", "hold", "support"]

# Threat levels
THREAT_LEVELS = ["low", "medium", "high"]

# Engagement radii by unit type
ENGAGEMENT_RADII = {
    "mbt": 1200,
    "ifv": 800,
    "apc": 600,
    "mrap": 500,
    "light": 400,
    "truck": 300,
    "spg": 1500,
    "spaa": 1000,
    "eng": 300,
    "infantry": 300,
    "helicopter": 1500,
    "boat": 800,
}


def load_cost_grid(map_name=None):
    """Load the raw cost grid for terrain validation."""
    map_name = map_name or MAP_NAME
    grid_path = MAPS_DIR / f"{map_name}_costgrid.npz"
    if not grid_path.exists():
        return None
    return np.load(grid_path)["grid"]


def find_valid_start_end(grid, window, min_distance=2000, max_distance=6000):
    """Find valid start and end points on land."""
    if grid is None:
        # If no grid, just return random points
        sx = random.randint(window["x_min"], window["x_max"])
        sy = random.randint(window["y_min"], window["y_max"])
        ex = random.randint(window["x_min"], window["x_max"])
        ey = random.randint(window["y_min"], window["y_max"])
        return (sx, sy), (ex, ey)
    
    # Grid is 128x128, 64m per cell
    grid_dim = grid.shape[0]
    cell_size = 64
    
    for _ in range(100):  # Try 100 times
        # Random start
        sx = random.randint(window["x_min"], window["x_max"])
        sy = random.randint(window["y_min"], window["y_max"])
        
        # Check if on land
        gx = int(sx / cell_size) % grid_dim
        gy = int(sy / cell_size) % grid_dim
        if grid[gy, gx, 1] == 4:  # Water
            continue
        
        # Random end at appropriate distance
        angle = random.uniform(0, 2 * np.pi)
        distance = random.uniform(min_distance, max_distance)
        ex = int(sx + distance * np.cos(angle))
        ey = int(sy + distance * np.sin(angle))
        
        # Clamp to window
        ex = max(window["x_min"], min(window["x_max"], ex))
        ey = max(window["y_min"], min(window["y_max"], ey))
        
        # Check if on land
        gx = int(ex / cell_size) % grid_dim
        gy = int(ey / cell_size) % grid_dim
        if grid[gy, gx, 1] == 4:  # Water
            continue
        
        return (sx, sy), (ex, ey)
    
    # Fallback: just return points
    sx = random.randint(window["x_min"], window["x_max"])
    sy = random.randint(window["y_min"], window["y_max"])
    ex = random.randint(window["x_min"], window["x_max"])
    ey = random.randint(window["y_min"], window["y_max"])
    return (sx, sy), (ex, ey)


def generate_scenario(map_name=None):
    """Generate a random but realistic scenario."""
    map_name = map_name or MAP_NAME
    grid = load_cost_grid(map_name)
    
    # Terrain window (main land area for Stratis)
    window = {"x_min": 1000, "x_max": 7000, "y_min": 1000, "y_max": 7000}
    
    # Find valid start/end
    (start_x, start_y), (end_x, end_y) = find_valid_start_end(grid, window)
    
    # Pick unit composition
    units = random.choice(UNIT_COMPOSITIONS)
    
    # Generate unit positions (spread around start)
    friendly_units = []
    for i, unit_type in enumerate(units):
        offset_x = random.randint(-300, 300)
        offset_y = random.randint(-300, 300)
        friendly_units.append({
            "unit_id": f"friendly_{i}",
            "type": unit_type,
            "pos": [start_x + offset_x, start_y + offset_y],
            "status": "ready"
        })
    
    # Pick enemy composition
    enemy_comp = random.choice(ENEMY_COMPOSITIONS)
    
    # Generate enemy positions (between start and end)
    known_contacts = []
    contact_id = 0
    for group in enemy_comp:
        for _ in range(group["count"]):
            # Position along route with randomness
            t = random.uniform(0.25, 0.75)
            enemy_x = int(start_x + t * (end_x - start_x) + random.randint(-800, 800))
            enemy_y = int(start_y + t * (end_y - start_y) + random.randint(-800, 800))
            
            # Clamp to window
            enemy_x = max(window["x_min"], min(window["x_max"], enemy_x))
            enemy_y = max(window["y_min"], min(window["y_max"], enemy_y))
            
            known_contacts.append({
                "contact_id": f"enemy_{contact_id}",
                "type": group["type"],
                "pos": [enemy_x, enemy_y],
                "confidence": round(random.uniform(0.6, 1.0), 2),
                "engagement_radius": ENGAGEMENT_RADII.get(group["type"], 500)
            })
            contact_id += 1
    
    # Pick objective and threat level
    objective = random.choice(OBJECTIVES)
    threat_level = random.choice(THREAT_LEVELS)
    
    # Adjust threat level based on enemy composition
    enemy_count = sum(g["count"] for g in enemy_comp)
    if enemy_count >= 5 or any(g["type"] == "mbt" for g in enemy_comp):
        threat_level = "high"
    elif enemy_count >= 3:
        threat_level = "medium"
    else:
        threat_level = "low"
    
    # Build scenario params
    scenario_params = {
        "map_name": map_name,
        "start": [start_x, start_y],
        "end": [end_x, end_y],
        "objective": objective,
        "threat_level": threat_level,
        "enemy_count": enemy_count,
        "friendly_count": len(units),
    }
    
    # Build state JSON for the LLM
    state_json = {
        "map": map_name,
        "objective": objective,
        "threat_level": threat_level,
        "friendly_units": friendly_units,
        "known_contacts": known_contacts,
        "mission": {
            "start": [start_x, start_y],
            "end": [end_x, end_y],
            "description": f"Move from [{start_x}, {start_y}] to [{end_x}, {end_y}] and {objective}"
        }
    }
    
    return scenario_params, state_json


def generate_batch(count, map_name=None):
    """Generate a batch of scenarios."""
    scenarios = []
    for _ in range(count):
        scenario_params, state_json = generate_scenario(map_name)
        scenarios.append({
            "scenario_params": scenario_params,
            "state_json": state_json
        })
    return scenarios


if __name__ == "__main__":
    # Test sampler
    for i in range(5):
        params, state = generate_scenario()
        print(f"\nScenario {i+1}:")
        print(f"  Objective: {params['objective']}")
        print(f"  Threat: {params['threat_level']}")
        print(f"  Friendly: {params['friendly_count']} units")
        print(f"  Enemy: {params['enemy_count']} contacts")
        print(f"  Route: {state['mission']['start']} -> {state['mission']['end']}")
