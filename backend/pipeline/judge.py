"""Dual judge system for tactical validation.

Two independent judges evaluate each example:
- Judge A: checks tactical coherence (does the order make sense?)
- Judge B: checks reasoning quality (is the logic sound?)

Uses different providers via OpenRouter to avoid correlated blind spots.
"""

import json
import time
from typing import Dict, Any, Optional

from .config import (
    JUDGE_A_MODEL, JUDGE_B_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    MAX_RETRIES
)


JUDGE_PROMPT = """You are a tactical validation judge for Arma 3.
Evaluate whether this order is tactically sound given the situation.

## Situation
{state_json}

## Order Under Evaluation
{order_json}

## Your Task
Evaluate ONLY these two aspects:
1. Tactical coherence: Does the order logically follow from the situation?
2. Reasoning quality: Is the reasoning sound and internally consistent?

## Output Format
Return valid JSON:
{{
  "verdict": "accept" | "reject",
  "tactical_coherence": {{
    "score": 1-10,
    "issues": ["list of any issues"]
  }},
  "reasoning_quality": {{
    "score": 1-10,
    "issues": ["list of any issues"]
  }},
  "overall_assessment": "Brief explanation of your verdict"
}}

## Rules
- Do NOT evaluate spatial accuracy (that's handled separately)
- Do NOT rewrite or suggest changes
- Focus on tactical logic and reasoning consistency
- Score below 6 on either aspect = reject
- Both aspects must score 6+ to accept
"""


def call_openrouter_judge(prompt, model):
    """Call OpenRouter API for judge."""
    import httpx
    
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ArpitTeli/spectre-app",
        "X-Title": "SPECTRE Training Pipeline"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.3,  # Lower temperature for more consistent judging
        "response_format": {"type": "json_object"}
    }
    
    response = httpx.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60.0
    )
    
    if response.status_code != 200:
        raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
    
    return response.json()["choices"][0]["message"]["content"]


def call_judge(prompt, model):
    """Call judge via OpenRouter."""
    return call_openrouter_judge(prompt, model)


def evaluate_order(state_json, order_json, model):
    """Evaluate a single order with a judge model.
    
    Returns:
        dict: Judge verdict with scores and reasoning
    """
    prompt = JUDGE_PROMPT.format(
        state_json=json.dumps(state_json, indent=2),
        order_json=json.dumps(order_json, indent=2)
    )
    
    for attempt in range(MAX_RETRIES):
        try:
            raw_response = call_judge(prompt, model)
            verdict = json.loads(raw_response)
            
            # Validate structure
            if "verdict" not in verdict:
                raise ValueError("Response missing 'verdict'")
            if verdict["verdict"] not in ["accept", "reject"]:
                raise ValueError(f"Invalid verdict: {verdict['verdict']}")
            
            return verdict
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error on attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES - 1:
                return {
                    "verdict": "reject",
                    "error": f"JSON decode failed: {e}"
                }
            time.sleep(1)
            
        except Exception as e:
            print(f"API error on attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES - 1:
                return {
                    "verdict": "reject",
                    "error": str(e)
                }
            time.sleep(2 ** attempt)
    
    return {"verdict": "reject", "error": "Max retries exceeded"}


def judge_example(example, judge_a_model=None, judge_b_model=None):
    """Evaluate an example with both judges.
    
    Args:
        example: dict with state_json, teacher_output_json
        judge_a_model: Override for judge A model
        judge_b_model: Override for judge B model
    
    Returns:
        tuple: (judge_a_verdict, judge_b_verdict)
    """
    state = json.loads(example["state_json"]) if isinstance(example["state_json"], str) else example["state_json"]
    teacher_output = json.loads(example["teacher_output_json"]) if isinstance(example["teacher_output_json"], str) else example["teacher_output_json"]
    
    orders = teacher_output.get("orders", [])
    
    # Evaluate each order
    all_verdicts_a = []
    all_verdicts_b = []
    
    for order in orders:
        # Judge A
        verdict_a = evaluate_order(state, order, judge_a_model or JUDGE_A_MODEL)
        all_verdicts_a.append(verdict_a)
        
        # Judge B
        verdict_b = evaluate_order(state, order, judge_b_model or JUDGE_B_MODEL)
        all_verdicts_b.append(verdict_b)
    
    # Aggregate verdicts
    combined_a = {
        "verdict": "accept" if all(v.get("verdict") == "accept" for v in all_verdicts_a) else "reject",
        "order_verdicts": all_verdicts_a
    }
    
    combined_b = {
        "verdict": "accept" if all(v.get("verdict") == "accept" for v in all_verdicts_b) else "reject",
        "order_verdicts": all_verdicts_b
    }
    
    return combined_a, combined_b


def run_judges(batch_size=None):
    """Run judges on all geo-filtered examples.
    
    Returns:
        tuple: (accepted_count, rejected_count, flagged_count)
    """
    from .db import get_db, get_examples_by_status, update_judge_verdict
    
    conn = get_db()
    pending = get_examples_by_status(conn, "geo_passed")
    
    if batch_size:
        pending = pending[:batch_size]
    
    accepted = 0
    rejected = 0
    flagged = 0
    
    for example in pending:
        example_id = example["id"]
        
        verdict_a, verdict_b = judge_example(example)
        update_judge_verdict(conn, example_id, verdict_a, verdict_b)
        
        if verdict_a["verdict"] == "accept" and verdict_b["verdict"] == "accept":
            accepted += 1
        elif verdict_a["verdict"] == "reject" and verdict_b["verdict"] == "reject":
            rejected += 1
        else:
            flagged += 1  # Disagreement
    
    conn.close()
    return accepted, rejected, flagged


if __name__ == "__main__":
    # Test with sample data
    sample_example = {
        "state_json": {
            "map": "stratis",
            "objective": "attack",
            "threat_level": "medium",
            "friendly_units": [
                {"unit_id": "friendly_0", "type": "mbt", "pos": [2592, 288], "status": "ready"}
            ],
            "known_contacts": [
                {"contact_id": "enemy_0", "type": "ifv", "pos": [4000, 2000], "confidence": 0.9, "engagement_radius": 800}
            ]
        },
        "teacher_output_json": {
            "orders": [
                {
                    "unit_id": "friendly_0",
                    "intent": "attack",
                    "target": [4000, 2000],
                    "anchors": [[3000, 1000], [3500, 1500]],
                    "constraints": {},
                    "reasoning": {
                        "situation_assessment": "Enemy IFV at [4000, 2000]",
                        "tactical_choice": "Attacking directly with MBT",
                        "tradeoffs": "Could flank but direct attack maintains momentum",
                        "what_if_rejected": "Flanking would take longer"
                    }
                }
            ]
        }
    }
    
    print("Testing judge system...")
    verdict_a, verdict_b = judge_example(sample_example)
    print(f"Judge A: {verdict_a['verdict']}")
    print(f"Judge B: {verdict_b['verdict']}")
