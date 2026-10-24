"""Run unittest modules in separate spawned processes (no shared test fixtures)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import io
import multiprocessing
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_module(filename: str) -> dict:
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=filename)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {"module": filename, "tests": result.testsRun, "success": result.wasSuccessful(),
            "details": stream.getvalue()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    modules = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(run_module, modules))
    for result in results:
        print(f"{result['module']}: {result['tests']} tests — {'PASS' if result['success'] else 'FAIL'}", flush=True)
        if not result["success"]:
            print(result["details"], flush=True)
    print(f"Total: {sum(r['tests'] for r in results)} tests; workers={args.workers}")
    sys.exit(0 if results and all(r["success"] for r in results) else 1)
