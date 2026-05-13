"""Gateway statistics tracker."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class BackendStats:
    requests:    int = 0
    errors:      int = 0
    input_toks:  int = 0
    output_toks: int = 0
    total_ms:    float = 0.0

    @property
    def avg_latency(self) -> float:
        return self.total_ms / self.requests if self.requests > 0 else 0.0


class StatsTracker:
    def __init__(self) -> None:
        self.backends: dict[str, BackendStats] = defaultdict(BackendStats)
        self.start_time = time.time()

    def record_request(
        self,
        backend_id: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        is_error: bool = False,
    ) -> None:
        s = self.backends[backend_id]
        s.requests += 1
        if is_error:
            s.errors += 1
        s.input_toks  += input_tokens
        s.output_toks += output_tokens
        s.total_ms    += duration_ms

    def get_summary(self) -> dict:
        return {
            "uptime_seconds": int(time.time() - self.start_time),
            "backends": {
                bid: {
                    "requests": s.requests,
                    "errors": s.errors,
                    "input_tokens": s.input_toks,
                    "output_tokens": s.output_toks,
                    "avg_latency_ms": round(s.avg_latency, 2),
                }
                for bid, s in self.backends.items()
            },
        }


_GLOBAL_STATS = StatsTracker()


def get_stats() -> StatsTracker:
    return _GLOBAL_STATS
