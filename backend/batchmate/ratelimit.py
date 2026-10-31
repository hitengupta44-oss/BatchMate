"""Fixed-window rate limit on Upstash Redis REST. No-op when Upstash isn't configured."""
from __future__ import annotations

import json
import time
import urllib.request

from . import config


def allow(key: str, limit: int | None = None, window_s: int = 60) -> bool:
    if not (config.UPSTASH_URL and config.UPSTASH_TOKEN):
        return True
    limit = limit or config.RATE_LIMIT_PER_MIN
    bucket = f"rl:{key}:{int(time.time() // window_s)}"
    body = json.dumps([["INCR", bucket], ["EXPIRE", bucket, str(window_s)]]).encode()
    req = urllib.request.Request(f"{config.UPSTASH_URL}/pipeline", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {config.UPSTASH_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            count = json.loads(r.read())[0]["result"]
        return int(count) <= limit
    except Exception:
        return True  # fail open: never block a demo because Redis hiccuped
