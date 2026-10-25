"""Per-caller rate limits at the gateway: a fixed one-minute window per (caller, route group).

Redis holds the counters, so limits hold across API processes; the in-memory limiter is for tests.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Protocol

LIMITS_PER_MINUTE = {"w1": 30, "w2": 30, "upload": 10}


class Limiter(Protocol):
    def hit(self, caller: str, group: str) -> tuple[bool, int]: ...   # (allowed, seconds until reset)


class RedisLimiter:
    def __init__(self, redis, limits: dict[str, int] = LIMITS_PER_MINUTE):
        self.r, self.limits = redis, limits

    def hit(self, caller: str, group: str) -> tuple[bool, int]:
        window = int(time.time() // 60)
        key = f"rl:{group}:{caller}:{window}"
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 61)
        count, _ = pipe.execute()
        return count <= self.limits[group], 60 - int(time.time()) % 60


class MemoryLimiter:
    def __init__(self, limits: dict[str, int] = LIMITS_PER_MINUTE, clock=time.time):
        self.limits, self.clock = limits, clock
        self.counts: dict[str, int] = defaultdict(int)

    def hit(self, caller: str, group: str) -> tuple[bool, int]:
        now = self.clock()
        key = f"{group}:{caller}:{int(now // 60)}"
        self.counts[key] += 1
        return self.counts[key] <= self.limits[group], 60 - int(now) % 60
