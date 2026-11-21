"""Blast Radius selector, v1 (rule-based, no coverage map yet).

Per commit we decide which tests to run, then spread them over workers.
Safe rule of thumb: when unsure, run everything (a miss costs 300 s).
"""

import json
import os
import re
import sys
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
MAX_WORKERS = 8
WORKER_COST = 2.0  # seconds charged per worker used


def changed_files(patch: str) -> list[str]:
    """Paths touched by a unified diff."""
    return re.findall(r"^\+\+\+ b/(\S+)", patch, re.M)


def is_comment_only(patch: str) -> bool:
    """True if every added/removed line is blank or a '#' comment."""
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line[:1] in "+-":
            body = line[1:].strip()
            if body and not body.startswith("#"):
                return False
    return True


def split(tests: list[dict], count: int) -> list[list[int]]:
    """Longest test first onto the least-loaded worker (greedy balancing)."""
    workers: list[list[int]] = [[] for _ in range(count)]
    loads = [0.0] * count
    for t in sorted(tests, key=lambda t: t["seconds"], reverse=True):
        i = loads.index(min(loads))
        workers[i].append(t["number"])
        loads[i] += t["seconds"]
    return [w for w in workers if w]


def best_split(tests: list[dict]) -> list[list[int]]:
    """Pick the worker count (1..8) with the lowest simulated cost."""
    if not tests:
        return []
    best, best_cost = None, None
    for n in range(1, MAX_WORKERS + 1):
        w = split(tests, n)
        by_num = {t["number"]: t["seconds"] for t in tests}
        cost = max(sum(by_num[x] for x in ws) for ws in w) + WORKER_COST * len(w)
        if best_cost is None or cost < best_cost:
            best, best_cost = w, cost
    return best


def select(patch: str, tests: list[dict]) -> list[dict]:
    files = changed_files(patch)
    py_only = files and all(f.endswith(".py") for f in files)
    if py_only and is_comment_only(patch):
        return []  # comment edits: run nothing
    if files and all(f.startswith("tests/fixtures/optimizer/") for f in files):
        return [t for t in tests if t["file"] == "tests/test_optimizer.py"]
    return tests  # unknown: be safe, run everything


def main() -> None:
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    for p in sorted((DATA / "commits").glob("*.patch")):
        chosen = select(p.read_text(errors="replace"), tests)
        print(json.dumps({"commit": p.stem, "workers": best_split(chosen)}))


if __name__ == "__main__":
    main()
