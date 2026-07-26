"""SQLite database for the training pipeline.

Single table design — one row per training example.
Each pipeline stage reads rows in a given status, does its work,
writes results, and advances the status.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

from .config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Stage 1: Sampler output
    scenario_params TEXT NOT NULL,
    state_json TEXT NOT NULL,
    terrain_digest_json TEXT,
    
    -- Stage 2: Teacher output
    teacher_model TEXT,
    teacher_output_json TEXT,
    teacher_raw_response TEXT,
    
    -- Stage 3: Planner output
    planner_output_json TEXT,
    
    -- Stage 4: Geometric filter
    geo_filter_result TEXT,
    geo_filter_status TEXT DEFAULT 'pending',
    
    -- Stage 5-6: Dual judge
    judge_a_model TEXT,
    judge_a_verdict TEXT,
    judge_b_model TEXT,
    judge_b_verdict TEXT,
    
    -- Stage 7: Resolution
    final_status TEXT DEFAULT 'pending',
    
    -- Stage 8: Review
    reviewed_by_human INTEGER DEFAULT 0,
    human_notes TEXT,
    
    -- Metadata
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_final_status ON examples(final_status);
CREATE INDEX IF NOT EXISTS idx_geo_status ON examples(geo_filter_status);
CREATE INDEX IF NOT EXISTS idx_created ON examples(created_at);
"""


def get_db(db_path=None):
    """Get a database connection."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """Initialize the database schema."""
    conn = get_db(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_example(conn, scenario_params, state_json):
    """Insert a new example from the sampler."""
    cursor = conn.execute(
        """INSERT INTO examples (scenario_params, state_json, final_status)
           VALUES (?, ?, 'sampled')""",
        (json.dumps(scenario_params), json.dumps(state_json))
    )
    conn.commit()
    return cursor.lastrowid


def update_teacher_output(conn, example_id, teacher_model, teacher_output, raw_response):
    """Update with teacher model output."""
    conn.execute(
        """UPDATE examples 
           SET teacher_model = ?, teacher_output_json = ?, teacher_raw_response = ?,
               final_status = 'teacher_done', updated_at = ?
           WHERE id = ?""",
        (teacher_model, json.dumps(teacher_output), raw_response,
         datetime.now().isoformat(), example_id)
    )
    conn.commit()


def update_terrain_digest(conn, example_id, terrain_digest):
    """Update with OAKOC terrain digest."""
    conn.execute(
        """UPDATE examples 
           SET terrain_digest_json = ?, updated_at = ?
           WHERE id = ?""",
        (json.dumps(terrain_digest), datetime.now().isoformat(), example_id)
    )
    conn.commit()


def update_planner_output(conn, example_id, planner_output):
    """Update with path planner output."""
    conn.execute(
        """UPDATE examples 
           SET planner_output_json = ?, updated_at = ?
           WHERE id = ?""",
        (json.dumps(planner_output), datetime.now().isoformat(), example_id)
    )
    conn.commit()


def update_geo_filter(conn, example_id, geo_result, status):
    """Update with geometric filter result."""
    final_status = 'geo_passed' if status == 'passed' else 'geo_failed'
    conn.execute(
        """UPDATE examples 
           SET geo_filter_result = ?, geo_filter_status = ?, final_status = ?,
               updated_at = ?
           WHERE id = ?""",
        (json.dumps(geo_result) if geo_result else None, status, final_status,
         datetime.now().isoformat(), example_id)
    )
    conn.commit()


def update_judge_verdict(conn, example_id, judge_a_verdict, judge_b_verdict):
    """Update with judge verdicts."""
    conn.execute(
        """UPDATE examples 
           SET judge_a_verdict = ?, judge_b_verdict = ?, final_status = 'judged',
               updated_at = ?
           WHERE id = ?""",
        (json.dumps(judge_a_verdict) if judge_a_verdict else None,
         json.dumps(judge_b_verdict) if judge_b_verdict else None,
         datetime.now().isoformat(), example_id)
    )
    conn.commit()


def update_final_status(conn, example_id, status):
    """Update the final status."""
    conn.execute(
        """UPDATE examples 
           SET final_status = ?, updated_at = ?
           WHERE id = ?""",
        (status, datetime.now().isoformat(), example_id)
    )
    conn.commit()


def get_examples_by_status(conn, status, limit=None):
    """Get examples in a given status."""
    query = "SELECT * FROM examples WHERE final_status = ? ORDER BY id"
    if limit:
        query += f" LIMIT {limit}"
    return conn.execute(query, (status,)).fetchall()


def get_examples_by_geo_status(conn, status, limit=None):
    """Get examples by geometric filter status."""
    query = "SELECT * FROM examples WHERE geo_filter_status = ? ORDER BY id"
    if limit:
        query += f" LIMIT {limit}"
    return conn.execute(query, (status,)).fetchall()


def get_stats(conn):
    """Get pipeline statistics."""
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
    stats["by_geo_status"] = {row["geo_filter_status"]: row["count"] for row in rows}
    
    # Total count
    stats["total"] = conn.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
    
    # Flatten status counts for UI
    by_status = stats["by_status"]
    stats["sampled"] = by_status.get("sampled", 0)
    stats["teacher_done"] = by_status.get("teacher_done", 0)
    stats["geo_passed"] = by_status.get("geo_passed", 0)
    stats["geo_failed"] = by_status.get("geo_failed", 0)
    stats["judged"] = by_status.get("judged", 0)
    stats["accepted"] = by_status.get("accepted", 0)
    stats["rejected"] = by_status.get("rejected", 0)
    stats["flagged"] = by_status.get("flagged", 0)
    
    # Target for UI display
    from .config import TARGET_EXAMPLES
    stats["target"] = TARGET_EXAMPLES
    
    return stats
