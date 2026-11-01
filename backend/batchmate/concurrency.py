"""Run independent recalls at the same time. Meko searches are slow (seconds each) but independent,
so a question waits for the slowest one instead of the sum of all of them."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def parallel(**calls):
    """parallel(a=lambda: ..., b=lambda: ...) → {"a": ..., "b": ...}"""
    if not calls:
        return {}
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = {name: pool.submit(fn) for name, fn in calls.items()}
        return {name: f.result() for name, f in futures.items()}
