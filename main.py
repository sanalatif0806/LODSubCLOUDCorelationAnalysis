#!/usr/bin/env python3
"""
Main entrypoint — runs the full FAIR assessment pipeline in order:

  Step 1 │ LODsubcloudclasscsv.py   → parse kgs_by_topic.json → per-topic CSVs  (data/LODsubclouds/)
  Step 2 │ LODsubcloudclassjson.py  → same source → per-topic JSON files
  Step 3 │ mergefairscore.py        → merge LODsubcloud CSVs with FAIR baseline CSV
  Step 4 │ fujiass.py               → evaluate every dataset via local F-UJI server
  Step 5 │ FAIR-Checkerass.py       → evaluate every dataset via FAIR-Checker API

Usage:
    python main.py [--steps 1,2,3,4,5]   # run all steps (default)
    python main.py --steps 1,2            # run only steps 1 and 2
    python main.py --steps 4              # run only F-UJI assessment
"""

import argparse
import importlib.util
import sys
import traceback
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR  = ROOT_DIR / "src"

# Map step number → (label, module path relative to SRC_DIR)
STEPS: dict[int, tuple[str, Path]] = {
    1: ("LOD subcloud CSV classifier",  SRC_DIR / "LODCloudassment" / "LODsubcloudclasscsv.py"),
    2: ("LOD subcloud JSON classifier", SRC_DIR / "LODCloudassment" / "LODsubcloudclassjson.py"),
    3: ("Merge FAIR scores",            SRC_DIR / "LODCloudassment" / "mergefairscore.py"),
    4: ("F-UJI assessment",             SRC_DIR / "F-UJI assessment" / "fujiass.py"),
    5: ("FAIR-Checker assessment",      SRC_DIR / "FAIR-checker"    / "FAIR-Checkerass.py"),
}


def _run_module(label: str, script_path: Path) -> bool:
    """
    Load and execute a Python script as a module.
    Returns True on success, False on failure.
    """
    print(f"\n{'─' * 60}")
    print(f"  ▶  {label}")
    print(f"     {script_path}")
    print(f"{'─' * 60}\n")

    if not script_path.exists():
        print(f"  ❌  File not found: {script_path}")
        return False

    try:
        spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
        module = importlib.util.module_from_spec(spec)
        # Make sure the script's own directory is on sys.path so its
        # relative imports / Path(__file__).parent logic works correctly.
        script_dir = str(script_path.parent)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        spec.loader.exec_module(module)
        print(f"\n  ✅  {label} — completed successfully")
        return True
    except SystemExit as e:
        # Scripts that call sys.exit / exit() — treat non-zero as failure
        if e.code not in (None, 0):
            print(f"\n  ❌  {label} — exited with code {e.code}")
            return False
        print(f"\n  ✅  {label} — completed (exited 0)")
        return True
    except Exception:
        print(f"\n  ❌  {label} — raised an exception:")
        traceback.print_exc()
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FAIR assessment pipeline — run all scripts from one entrypoint."
    )
    parser.add_argument(
        "--steps",
        default=",".join(str(k) for k in STEPS),
        help=(
            "Comma-separated list of step numbers to run "
            f"(1–{max(STEPS)}). Default: all steps."
        ),
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        default=False,
        help="Abort the pipeline immediately if any step fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Parse requested steps
    try:
        requested = [int(s.strip()) for s in args.steps.split(",") if s.strip()]
    except ValueError:
        print(f"❌  Invalid --steps value: {args.steps!r}")
        sys.exit(1)

    unknown = [s for s in requested if s not in STEPS]
    if unknown:
        print(f"❌  Unknown step(s): {unknown}. Valid steps: {list(STEPS.keys())}")
        sys.exit(1)

    print("\n" + "═" * 60)
    print("  FAIR Assessment Pipeline")
    print("═" * 60)
    print(f"  Root : {ROOT_DIR}")
    print(f"  Steps: {requested}")
    print("═" * 60)

    results: dict[int, bool] = {}

    for step_num in sorted(requested):
        label, path = STEPS[step_num]
        ok = _run_module(label, path)
        results[step_num] = ok

        if not ok and args.stop_on_error:
            print("\n⛔  --stop-on-error set — aborting pipeline.")
            break

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  Pipeline Summary")
    print("═" * 60)
    for step_num, ok in sorted(results.items()):
        label, _ = STEPS[step_num]
        status = "✅ OK  " if ok else "❌ FAIL"
        print(f"  Step {step_num}: {status} — {label}")
    print("═" * 60 + "\n")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
