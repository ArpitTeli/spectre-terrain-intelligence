"""Gemini judge for tactical validation.

Single judge (Gemini 2.5 Pro) evaluates batches of orders.
Supports batching 10 examples per request to stay within rate limits.
"""

import json
import time
import re
from typing import List, Dict

from .config import GEMINI_API_KEY, MAX_RETRIES


JUDGE_PROMPT = """You are a tactical validation judge for Arma 3 military simulation.

Evaluate each of the {count} orders below. For each order, assess:
1. Tactical coherence: Does the order logically follow from the situation?
2. Reasoning quality: Is the reasoning sound and internally consistent?

## Rules
- Score below 6 on either aspect = reject
- Both aspects must score 6+ to accept
- Do NOT evaluate spatial accuracy (handled separately)
- Do NOT rewrite or suggest changes

## Examples to Evaluate
{examples_json}

## Output Format
Return a JSON array with exactly {count} verdicts, one per example, in the same order:
[
  {{
    "example_index": 0,
    "verdict": "accept" | "reject",
    "tactical_coherence": {{"score": 1-10, "issues": []}},
    "reasoning_quality": {{"score": 1-10, "issues": []}},
    "overall_assessment": "brief explanation"
  }},
  ...
]

Return ONLY the JSON array. No markdown, no explanation."""


def extract_json(text):
    """Extract JSON from a response that may contain markdown code blocks."""
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No valid JSON found", text, 0)


def call_gemini(prompt):
    """Call Gemini API."""
    import httpx

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192
        }
    }

    response = httpx.post(url, json=payload, timeout=120.0)

    if response.status_code != 200:
        raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

    result = response.json()
    content = result["candidates"][0]["content"]["parts"][0]["text"]
    usage = result.get("usageMetadata", {})
    return content, {
        "prompt_tokens": usage.get("promptTokenCount", 0),
        "completion_tokens": usage.get("candidatesTokenCount", 0),
        "total_tokens": usage.get("totalTokenCount", 0)
    }


def build_batch_examples(examples_data):
    """Build the examples section of the prompt for a batch."""
    parts = []
    for i, (state, orders) in enumerate(examples_data):
        order_text = json.dumps(orders, indent=2)
        parts.append(f"### Example {i}\n**Situation:** {json.dumps(state, indent=2)}\n**Orders:** {order_text}")
    return "\n\n".join(parts)


def judge_batch(examples_data):
    """Judge a batch of examples in one API call.
    
    Args:
        examples_data: list of (state_json_dict, teacher_output_dict) tuples
    
    Returns:
        list of verdict dicts
    """
    count = len(examples_data)
    examples_text = build_batch_examples(examples_data)
    prompt = JUDGE_PROMPT.format(count=count, examples_json=examples_text)

    for attempt in range(MAX_RETRIES):
        try:
            raw_response, usage = call_gemini(prompt)
            verdicts = extract_json(raw_response)

            # Handle single dict response
            if isinstance(verdicts, dict):
                verdicts = [verdicts]

            # Validate count
            if len(verdicts) != count:
                raise ValueError(f"Expected {count} verdicts, got {len(verdicts)}")

            for v in verdicts:
                v["_usage"] = usage
                if "verdict" not in v:
                    raise ValueError(f"Verdict missing 'verdict' key")

            return verdicts

        except Exception as e:
            print(f"Gemini judge error on attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES - 1:
                return [{"verdict": "reject", "error": str(e)} for _ in range(count)]
            time.sleep(2 ** attempt)

    return [{"verdict": "reject", "error": "Max retries exceeded"} for _ in range(count)]


def judge_single(example):
    """Judge a single example (convenience wrapper)."""
    state = json.loads(example["state_json"]) if isinstance(example["state_json"], str) else example["state_json"]
    teacher_output = json.loads(example["teacher_output_json"]) if isinstance(example["teacher_output_json"], str) else example["teacher_output_json"]
    verdicts = judge_batch([(state, teacher_output)])
    return verdicts[0]


def run_judges(batch_size=None, batch_api_size=10):
    """Run Gemini judge on all pending examples.
    
    Groups examples into batches of batch_api_size for efficient API usage.
    
    Returns:
        tuple: (accepted_count, rejected_count)
    """
    from .db import get_db, get_examples_by_status, update_judge_verdict

    conn = get_db()
    pending = get_examples_by_status(conn, "teacher_done")

    if batch_size:
        pending = pending[:batch_size]

    accepted = 0
    rejected = 0

    # Process in batches
    for i in range(0, len(pending), batch_api_size):
        batch = pending[i:i + batch_api_size]
        print(f"  Judging batch {i // batch_api_size + 1}: examples {i + 1}-{i + len(batch)}")

        examples_data = []
        for example in batch:
            state = json.loads(example["state_json"])
            teacher_output = json.loads(example["teacher_output_json"])
            examples_data.append((state, teacher_output))

        verdicts = judge_batch(examples_data)

        for example, verdict in zip(batch, verdicts):
            # Store verdict as both judge_a and judge_b (same model, single judge)
            update_judge_verdict(conn, example["id"], verdict, verdict)

            if verdict.get("verdict") == "accept":
                accepted += 1
            else:
                rejected += 1

        # Rate limit: 25 req/day for free tier
        time.sleep(1)

    conn.close()
    return accepted, rejected


if __name__ == "__main__":
    print("Testing Gemini judge...")
    test_state = {
        "map": "stratis",
        "objective": "attack",
        "threat_level": "medium",
        "friendly_units": [
            {"unit_id": "friendly_0", "type": "mbt", "pos": [2592, 288], "status": "ready"}
        ],
        "known_contacts": [
            {"contact_id": "enemy_0", "type": "ifv", "pos": [4000, 2000], "confidence": 0.9, "engagement_radius": 800}
        ]
    }
    test_orders = {
        "orders": [{
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
        }]
    }

    verdict = judge_batch([(test_state, test_orders)])
    print(json.dumps(verdict, indent=2))
