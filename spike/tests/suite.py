"""Run the test suite on every core (#87).

    python spike/tests/suite.py            the full suite: before a merge
    python spike/tests/suite.py --quick    the quick set, seconds: after every change
    python spike/tests/suite.py test_aids test_publish_v2.PublishV2Tests   just these files or classes

Each test class (each test, for a class marked slow) runs in one of a pool of worker processes (one per core, --jobs to change it). The three fixture
lessons are built once for the whole run, one per worker to start with, into a folder every worker shares
(tests/lessons.py, GESSO_TEST_CACHE), then the classes run, the slow ones first.

The quick set leaves out the classes marked @lessons.slow: the ones that build or publish a fixture lesson, run the
outline model, or otherwise take seconds. `python -m unittest discover -s spike/tests` still runs everything in one
process, as before; it's just slower.
"""

from __future__ import annotations

import argparse
import io
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import unittest
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _classes(only: list[str]) -> list[tuple[str, bool]]:
    """(module.Class, slow) for every test class, in file order; a slow class is split into its tests
    (module.Class.test), so one long class doesn't hold up the run (its setUpClass is cheap: lessons.py), unless it says whole = True."""
    sys.path.insert(0, str(HERE))
    out = []
    for path in sorted(HERE.glob("test_*.py")):
        module = __import__(path.stem)
        for name, obj in vars(module).items():
            if (isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj.__module__ == path.stem
                    and unittest.defaultTestLoader.getTestCaseNames(obj)):
                cid = f"{path.stem}.{name}"
                slow = bool(getattr(obj, "slow", False))
                for tid in [f"{cid}.{t}" for t in unittest.defaultTestLoader.getTestCaseNames(obj)] \
                        if slow and not getattr(obj, "whole", False) else [cid]:
                    if not only or any(tid == o or tid.startswith(o + ".") for o in only):
                        out.append((tid, slow))
    return out


def _warm(name: str) -> float:
    sys.path.insert(0, str(HERE))
    import lessons

    start = time.time()
    lessons.warm(name)
    return time.time() - start


def _run(cid: str) -> dict:
    sys.path.insert(0, str(HERE))
    out = io.StringIO()
    start = time.time()
    suite = unittest.defaultTestLoader.loadTestsFromName(cid)
    result = unittest.TextTestRunner(stream=out, verbosity=1).run(suite)
    return {"id": cid, "seconds": time.time() - start, "run": result.testsRun, "ok": result.wasSuccessful(),
            "failures": len(result.failures) + len(result.errors), "skipped": len(result.skipped),
            "output": out.getvalue()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("only", nargs="*", help="test files or classes (test_aids, test_aids.AidsTests); default all")
    ap.add_argument("--quick", action="store_true", help="leave out the classes marked @lessons.slow")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args(argv)
    start = time.time()
    picked = [(c, slow) for c, slow in _classes(a.only) if not (a.quick and slow)]
    slow_first = [c for c, slow in picked if slow] + [c for c, slow in picked if not slow]
    cache = tempfile.mkdtemp(prefix="gesso-tests-")
    os.environ["GESSO_TEST_CACHE"] = cache  # the workers inherit it: one shared build of each fixture
    results = []
    try:
        with ProcessPoolExecutor(max_workers=max(1, a.jobs), mp_context=multiprocessing.get_context("spawn")) as pool:
            if any(slow for _, slow in picked):
                import lessons

                warm = [pool.submit(_warm, n) for n in lessons.NAMES]  # first in the queue: one fixture a worker
            else:
                warm = []
            jobs = [pool.submit(_run, c) for c in slow_first]
            for f in warm:
                f.result()  # a build that fails shows up here, before a page of failed tests
            for f in as_completed(jobs):
                r = f.result()
                results.append(r)
                if not r["ok"]:
                    sys.stdout.write(r["output"])
                sys.stdout.write("." if r["ok"] else "F")
                sys.stdout.flush()
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    print()
    for r in sorted(results, key=lambda r: -r["seconds"])[:10]:
        print(f"{r['seconds']:6.1f}s  {r['id']} ({r['run']} tests)")
    run = sum(r["run"] for r in results)
    bad = [r["id"] for r in results if not r["ok"]]
    skipped = sum(r["skipped"] for r in results)
    print(f"{'quick set' if a.quick else 'suite'}: {run} tests in {len(results)} jobs, {time.time() - start:.1f}s "
          f"on {a.jobs} workers" + (f", {skipped} skipped" if skipped else ""))
    if bad:
        print("FAILED: " + ", ".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
