"""Pipeline orchestrator.

Runs the full synthetic data generation pipeline:
1. Sample scenarios
2. Generate teacher outputs
3. Plan routes (TODO: integrate path planner)
4. Geometric filter
5. Dual judge
6. Resolve verdicts
7. Export for fine-tuning
"""

import json
import sys
from pathlib import Path

from .config import TARGET_EXAMPLES, BATCH_SIZE
from .db import init_db, get_stats, get_db
from .sampler import generate_batch
from .teacher import generate_batch as generate_teacher_batch
from .geo_filter import run_geo_filter
from .judge import run_judges
from .resolver import run_resolver
from .export import export_training_set


def init_pipeline():
    """Initialize the pipeline database."""
    print("Initializing pipeline database...")
    conn = init_db()
    stats = get_stats(conn)
    conn.close()
    print(f"Database ready. Current stats: {stats}")
    return stats


def stage_sample(count=None):
    """Stage 1: Generate scenarios."""
    count = count or BATCH_SIZE
    print(f"\n--- Stage 1: Sampling {count} scenarios ---")
    
    conn = get_db()
    existing = get_stats(conn)["total"]
    conn.close()
    
    if existing >= TARGET_EXAMPLES:
        print(f"Already have {existing} examples (target: {TARGET_EXAMPLES}). Skipping.")
        return 0
    
    scenarios = generate_batch(count)
    print(f"Generated {len(scenarios)} scenarios")
    
    # Insert into database
    from .db import insert_example
    conn = get_db()
    for scenario in scenarios:
        insert_example(conn, scenario["scenario_params"], scenario["state_json"])
    conn.close()
    
    print(f"Inserted {len(scenarios)} scenarios into database")
    return len(scenarios)


def stage_teacher(count=None):
    """Stage 2: Generate teacher outputs."""
    count = count or BATCH_SIZE
    print(f"\n--- Stage 2: Generating teacher outputs (batch of {count}) ---")
    
    results = generate_teacher_batch(model=None)
    print(f"Generated {len(results)} teacher outputs")
    return len(results)


def stage_geo_filter(count=None):
    """Stage 4: Run geometric filter."""
    count = count or BATCH_SIZE
    print(f"\n--- Stage 4: Running geometric filter ---")
    
    passed, failed = run_geo_filter(count)
    print(f"Geo filter: {passed} passed, {failed} failed")
    return passed, failed


def stage_judge(count=None):
    """Stage 5-6: Run dual judges."""
    count = count or BATCH_SIZE
    print(f"\n--- Stage 5-6: Running dual judges ---")
    
    accepted, rejected, flagged = run_judges(count)
    print(f"Judges: {accepted} accepted, {rejected} rejected, {flagged} flagged")
    return accepted, rejected, flagged


def stage_resolve(count=None):
    """Stage 7: Resolve verdicts."""
    count = count or BATCH_SIZE
    print(f"\n--- Stage 7: Resolving verdicts ---")
    
    accepted, rejected, flagged = run_resolver(count)
    print(f"Resolved: {accepted} accepted, {rejected} rejected, {flagged} flagged")
    return accepted, rejected, flagged


def stage_export():
    """Stage 8: Export training set."""
    print(f"\n--- Stage 8: Exporting training set ---")
    
    count = export_training_set()
    print(f"Exported {count} examples")
    return count


def run_pipeline(stages=None, count=None):
    """Run the full pipeline or specific stages.
    
    Args:
        stages: List of stage names to run (None = all)
        count: Number of examples to process per stage
    """
    all_stages = ["sample", "teacher", "geo_filter", "judge", "resolve", "export"]
    stages_to_run = stages or all_stages
    
    print("=" * 60)
    print("SPECTRE Training Data Pipeline")
    print("=" * 60)
    
    # Initialize
    init_pipeline()
    
    # Run stages
    for stage in stages_to_run:
        if stage == "sample":
            stage_sample(count)
        elif stage == "teacher":
            stage_teacher(count)
        elif stage == "geo_filter":
            stage_geo_filter(count)
        elif stage == "judge":
            stage_judge(count)
        elif stage == "resolve":
            stage_resolve(count)
        elif stage == "export":
            stage_export()
        else:
            print(f"Unknown stage: {stage}")
    
    # Print final stats
    print("\n" + "=" * 60)
    print("Pipeline Complete")
    print("=" * 60)
    
    conn = get_db()
    stats = get_stats(conn)
    conn.close()
    
    print(f"Total examples: {stats['total']}")
    print(f"Accepted: {stats['accepted']}")
    print(f"By status: {stats['by_status']}")
    print(f"By geo status: {stats['by_geo_status']}")


def show_status():
    """Show current pipeline status."""
    conn = get_db()
    stats = get_stats(conn)
    conn.close()
    
    print("Pipeline Status:")
    print(f"  Total examples: {stats['total']}")
    print(f"  Accepted: {stats['accepted']}")
    print(f"  By status: {stats['by_status']}")
    print(f"  By geo status: {stats['by_geo_status']}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SPECTRE Training Pipeline")
    parser.add_argument("command", choices=["run", "status", "init", "sample", "teacher", "geo_filter", "judge", "resolve", "export"])
    parser.add_argument("--count", type=int, default=None, help="Number of examples to process")
    parser.add_argument("--stages", nargs="+", help="Specific stages to run")
    
    args = parser.parse_args()
    
    if args.command == "run":
        run_pipeline(stages=args.stages, count=args.count)
    elif args.command == "status":
        show_status()
    elif args.command == "init":
        init_pipeline()
    elif args.command == "sample":
        stage_sample(args.count)
    elif args.command == "teacher":
        stage_teacher(args.count)
    elif args.command == "geo_filter":
        stage_geo_filter(args.count)
    elif args.command == "judge":
        stage_judge(args.count)
    elif args.command == "resolve":
        stage_resolve(args.count)
    elif args.command == "export":
        stage_export()
