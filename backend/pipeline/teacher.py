"""Teacher model for generating tactical decisions.

Calls the teacher model via OpenRouter to generate tactical decisions
for each scenario. The output includes intent, anchor waypoints,
constraints, and structured reasoning.
"""

import json
import time
from typing import Optional

from .config import (
    TEACHER_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    MAX_RETRIES, BATCH_SIZE
)


TEACHER_PROMPT = """You are SPECTRE, a tactical AI advisor for Arma 3.
Given the current battlefield state and terrain digest, decide the best order
for each friendly unit.

## Current State
{state_json}

## Terrain Digest (OAKOC Analysis)
{terrain_digest_json}

## Task
For each friendly unit, output:
1. intent: one of [attack, defend, move, hold, recon, evacuate, support]
2. target: [x, y] coordinates of objective
3. anchors: 2-5 intermediate waypoints the unit should pass through
4. constraints: any avoid zones or preferences
5. reasoning: structured tactical analysis (see format below)

## Reasoning Format (REQUIRED)
Your reasoning must follow this structure:
{{
  "situation_assessment": "What you observe about the terrain, threats, and unit positions. Reference specific grid coordinates and threat types.",
  "tactical_choice": "What you decided and the immediate logic behind it.",
  "tradeoffs": "What alternatives you considered and why this option was selected over them.",
  "what_if_rejected": "Why the rejected alternatives would have failed or been worse."
}}

This reasoning is critical — it teaches the model HOW to think about tactical decisions, not just WHAT to decide.

## Output Format
Return valid JSON matching this schema:
{{
  "orders": [
    {{
      "unit_id": "friendly_0",
      "intent": "attack",
      "target": [x, y],
      "anchors": [[x1, y1], [x2, y2], ...],
      "constraints": {{
        "avoid_zones": [{{"pos": [x, y], "radius": r}}],
        "prefer_surface": "road" | "forest" | null
      }},
      "reasoning": {{
        "situation_assessment": "...",
        "tactical_choice": "...",
        "tradeoffs": "...",
        "what_if_rejected": "..."
      }}
    }}
  ]
}}
"""


def format_prompt(state_json, terrain_digest_json=None):
    """Format the teacher prompt with state and terrain data."""
    state_str = json.dumps(state_json, indent=2)
    
    if terrain_digest_json:
        terrain_str = json.dumps(terrain_digest_json, indent=2)
    else:
        terrain_str = "No terrain digest available yet."
    
    return TEACHER_PROMPT.format(
        state_json=state_str,
        terrain_digest_json=terrain_str
    )


def call_openrouter(prompt, model=None, max_tokens=4096):
    """Call OpenRouter API."""
    import httpx
    
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    
    model = model or TEACHER_MODEL
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ArpitTeli/spectre-app",
        "X-Title": "SPECTRE Training Pipeline"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }
    
    response = httpx.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120.0
    )
    
    if response.status_code != 200:
        raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
    
    return response.json()["choices"][0]["message"]["content"]


def call_teacher(prompt, model=None):
    """Call the teacher model via OpenRouter."""
    return call_openrouter(prompt, model)


def generate_teacher_output(state_json, terrain_digest_json=None, model=None):
    """Generate tactical decisions for a scenario.
    
    Returns:
        tuple: (teacher_output_dict, raw_response_string)
    """
    prompt = format_prompt(state_json, terrain_digest_json)
    
    for attempt in range(MAX_RETRIES):
        try:
            raw_response = call_teacher(prompt, model)
            
            # Parse JSON response
            teacher_output = json.loads(raw_response)
            
            # Validate basic structure
            if "orders" not in teacher_output:
                raise ValueError("Response missing 'orders' key")
            
            return teacher_output, raw_response
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error on attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(1)
            
        except Exception as e:
            print(f"API error on attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
    
    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts")


def generate_batch(terrain_digest_fn=None, model=None):
    """Generate teacher outputs for a batch of pending examples.
    
    Args:
        terrain_digest_fn: Function to get terrain digest for a scenario
        model: Override model selection
    
    Returns:
        list: List of (example_id, teacher_output, raw_response) tuples
    """
    from .db import get_db, get_examples_by_status, update_teacher_output, update_terrain_digest
    
    conn = get_db()
    pending = get_examples_by_status(conn, "sampled", limit=BATCH_SIZE)
    
    results = []
    for example in pending:
        example_id = example["id"]
        state_json = json.loads(example["state_json"])
        scenario_params = json.loads(example["scenario_params"])
        
        # Get terrain digest if available
        terrain_digest = None
        if terrain_digest_fn:
            try:
                terrain_digest = terrain_digest_fn(scenario_params)
                update_terrain_digest(conn, example_id, terrain_digest)
            except Exception as e:
                print(f"Warning: Could not get terrain digest for example {example_id}: {e}")
        
        # Generate teacher output
        try:
            teacher_output, raw_response = generate_teacher_output(
                state_json, terrain_digest, model
            )
            update_teacher_output(conn, example_id, model or TEACHER_MODEL,
                                 teacher_output, raw_response)
            results.append((example_id, teacher_output, raw_response))
            print(f"Generated output for example {example_id}")
            
        except Exception as e:
            print(f"Error generating output for example {example_id}: {e}")
    
    conn.close()
    return results


if __name__ == "__main__":
    # Test with a sample state
    sample_state = {
        "map": "stratis",
        "objective": "attack",
        "threat_level": "medium",
        "friendly_units": [
            {"unit_id": "friendly_0", "type": "mbt", "pos": [2592, 288], "status": "ready"},
            {"unit_id": "friendly_1", "type": "infantry", "pos": [2650, 350], "status": "ready"}
        ],
        "known_contacts": [
            {"contact_id": "enemy_0", "type": "ifv", "pos": [4000, 2000], "confidence": 0.9, "engagement_radius": 800}
        ],
        "mission": {
            "start": [2592, 288],
            "end": [5152, 3552],
            "description": "Move from [2592, 288] to [5152, 3552] and attack"
        }
    }
    
    print("Testing teacher generation...")
    try:
        output, raw = generate_teacher_output(sample_state)
        print(f"Generated {len(output['orders'])} orders")
        print(f"Raw response length: {len(raw)} chars")
    except Exception as e:
        print(f"Error: {e}")
