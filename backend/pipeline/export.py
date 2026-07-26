"""Export accepted examples to JSONL for fine-tuning.

Converts pipeline output to prompt/completion format for Unsloth.
"""

import json
from pathlib import Path

from .config import DB_PATH


TRAINING_PROMPT = """You are SPECTRE, a tactical AI advisor for Arma 3.
Given the current battlefield state and terrain digest, decide the best order
for each friendly unit.

## Current State
{state_json}

## Terrain Digest
{terrain_json}

## Output Format
Return valid JSON with an "orders" array containing one order per friendly unit."""


def export_training_set(db_path=None, output_path=None):
    """Export accepted examples to JSONL.
    
    Args:
        db_path: Path to SQLite database
        output_path: Path to output JSONL file
    """
    import sqlite3
    
    db_path = db_path or DB_PATH
    output_path = output_path or Path(__file__).parent / "training_set.jsonl"
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute(
        """SELECT state_json, terrain_digest_json, teacher_output_json 
           FROM examples WHERE final_status = 'accepted'"""
    ).fetchall()
    
    conn.close()
    
    with open(output_path, "w") as f:
        for row in rows:
            state = json.loads(row["state_json"])
            terrain = json.loads(row["terrain_digest_json"]) if row["terrain_digest_json"] else {}
            orders = json.loads(row["teacher_output_json"])
            
            # Build prompt
            prompt = TRAINING_PROMPT.format(
                state_json=json.dumps(state, indent=2),
                terrain_json=json.dumps(terrain, indent=2)
            )
            
            # Build completion (the orders)
            completion = json.dumps(orders, indent=2)
            
            # Write JSONL
            example = {
                "prompt": prompt,
                "completion": completion
            }
            f.write(json.dumps(example) + "\n")
    
    print(f"Exported {len(rows)} examples to {output_path}")
    return len(rows)


def export_with_reasoning(db_path=None, output_path=None):
    """Export with reasoning included (for distillation).
    
    This format includes the teacher's reasoning as part of the training signal.
    """
    import sqlite3
    
    db_path = db_path or DB_PATH
    output_path = output_path or Path(__file__).parent / "training_set_with_reasoning.jsonl"
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute(
        """SELECT state_json, terrain_digest_json, teacher_output_json
           FROM examples WHERE final_status = 'accepted'"""
    ).fetchall()
    
    conn.close()
    
    with open(output_path, "w") as f:
        for row in rows:
            state = json.loads(row["state_json"])
            terrain = json.loads(row["terrain_digest_json"]) if row["terrain_digest_json"] else {}
            teacher_output = json.loads(row["teacher_output_json"])
            
            # Build prompt with terrain digest
            prompt = TRAINING_PROMPT.format(
                state_json=json.dumps(state, indent=2),
                terrain_json=json.dumps(terrain, indent=2)
            )
            
            # Write JSONL - teacher output IS the completion
            example = {
                "prompt": prompt,
                "completion": json.dumps(teacher_output, indent=2)
            }
            f.write(json.dumps(example) + "\n")
    
    print(f"Exported {len(rows)} examples with reasoning to {output_path}")
    return len(rows)


if __name__ == "__main__":
    # Test export
    count = export_training_set()
    print(f"Exported {count} examples")
