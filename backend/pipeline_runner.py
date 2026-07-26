"""Pipeline runner for Electron app.

Reads commands from stdin, runs pipeline stages, sends results to stdout.
"""

import sys
import json
import os
from pathlib import Path

# Add the pipeline scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "spectre-fixed" / "scripts"))

from pipeline.config import validate_config, OPENROUTER_API_KEY, TEACHER_MODEL, JUDGE_A_MODEL, JUDGE_B_MODEL
from pipeline.db import init_db, get_stats, get_db
from pipeline.sampler import generate_batch
from pipeline.teacher import generate_batch as generate_teacher_batch
from pipeline.geo_filter import run_geo_filter
from pipeline.judge import run_judges
from pipeline.resolver import run_resolver
from pipeline.export import export_training_set


def send_message(msg):
    """Send a JSON message to stdout."""
    print(json.dumps(msg), flush=True)


def send_log(text):
    """Send a log message."""
    send_message({"type": "log", "text": text})


def send_status():
    """Send current pipeline status."""
    conn = get_db()
    stats = get_stats(conn)
    conn.close()
    send_message({"type": "status", "data": stats})


def handle_start(config):
    """Start the full pipeline."""
    # Update config from Electron
    os.environ["OPENROUTER_API_KEY"] = config.get("openrouterApiKey", "")
    os.environ["TEACHER_MODEL"] = config.get("teacherModel", "anthropic/claude-3.5-sonnet")
    os.environ["JUDGE_A_MODEL"] = config.get("judgeAModel", "anthropic/claude-3.5-haiku")
    os.environ["JUDGE_B_MODEL"] = config.get("judgeBModel", "openai/gpt-4o-mini")
    os.environ["TARGET_EXAMPLES"] = str(config.get("targetExamples", 1000))
    os.environ["MAP_NAME"] = config.get("mapName", "stratis")

    # Re-import config to pick up new values
    import importlib
    import pipeline.config
    importlib.reload(pipeline.config)

    send_log("Starting full pipeline...")
    send_status()

    try:
        validate_config()
    except ValueError as e:
        send_log(f"Config error: {e}")
        send_message({"type": "error", "error": str(e)})
        return

    # Initialize database
    send_log("Initializing database...")
    init_db()
    send_status()

    # Stage 1: Sample
    send_log("Stage 1: Sampling scenarios...")
    scenarios = generate_batch(100)
    conn = get_db()
    for scenario in scenarios:
        from pipeline.db import insert_example
        insert_example(conn, scenario["scenario_params"], scenario["state_json"])
    conn.close()
    send_log(f"Sampled {len(scenarios)} scenarios")
    send_status()

    # Stage 2: Teacher
    send_log("Stage 2: Generating teacher outputs...")
    try:
        results = generate_teacher_batch()
        send_log(f"Generated {len(results)} teacher outputs")
    except Exception as e:
        send_log(f"Teacher error: {e}")
    send_status()

    # Stage 3: Geo Filter
    send_log("Stage 3: Running geometric filter...")
    passed, failed = run_geo_filter()
    send_log(f"Geo filter: {passed} passed, {failed} failed")
    send_status()

    # Stage 4-5: Judges
    send_log("Stage 4-5: Running dual judges...")
    try:
        accepted, rejected, flagged = run_judges()
        send_log(f"Judges: {accepted} accepted, {rejected} rejected, {flagged} flagged")
    except Exception as e:
        send_log(f"Judge error: {e}")
    send_status()

    # Stage 6: Resolve
    send_log("Stage 6: Resolving verdicts...")
    accepted, rejected, flagged = run_resolver()
    send_log(f"Resolved: {accepted} accepted, {rejected} rejected, {flagged} flagged")
    send_status()

    # Stage 7: Export
    send_log("Stage 7: Exporting training set...")
    count = export_training_set()
    send_log(f"Exported {count} examples")
    send_status()

    send_message({"type": "stage_complete", "stage": "all"})
    send_log("Pipeline complete!")


def handle_run_stage(stage, count):
    """Run a specific pipeline stage."""
    send_log(f"Running stage: {stage}")
    send_status()

    try:
        if stage == "sample":
            scenarios = generate_batch(count or 10)
            conn = get_db()
            for scenario in scenarios:
                from pipeline.db import insert_example
                insert_example(conn, scenario["scenario_params"], scenario["state_json"])
            conn.close()
            send_log(f"Sampled {len(scenarios)} scenarios")

        elif stage == "teacher":
            results = generate_teacher_batch()
            send_log(f"Generated {len(results)} teacher outputs")

        elif stage == "geo_filter":
            passed, failed = run_geo_filter()
            send_log(f"Geo filter: {passed} passed, {failed} failed")

        elif stage == "judge":
            accepted, rejected, flagged = run_judges()
            send_log(f"Judges: {accepted} accepted, {rejected} rejected, {flagged} flagged")

        elif stage == "resolve":
            accepted, rejected, flagged = run_resolver()
            send_log(f"Resolved: {accepted} accepted, {rejected} rejected, {flagged} flagged")

        elif stage == "export":
            count = export_training_set()
            send_log(f"Exported {count} examples")

        send_message({"type": "stage_complete", "stage": stage})
    except Exception as e:
        send_log(f"Error in stage {stage}: {e}")
        send_message({"type": "error", "error": str(e)})

    send_status()


def main():
    """Main loop - read commands from stdin."""
    # Initialize database on startup
    init_db()
    send_status()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            command = json.loads(line)
        except json.JSONDecodeError:
            send_log(f"Invalid command: {line}")
            continue

        cmd = command.get("command")

        if cmd == "start":
            handle_start(command.get("config", {}))
        elif cmd == "run_stage":
            handle_run_stage(command.get("stage"), command.get("count"))
        elif cmd == "status":
            send_status()
        else:
            send_log(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
