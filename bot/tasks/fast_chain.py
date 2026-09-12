"""Fast Chain Action Execution for BotControl.

Executes sequential tap actions with:
- Gaussian inter-tap cadence (110ms - 180ms, mean 145ms, std 22ms, clamped to [105ms, 200ms])
- 2D Gaussian point dispersion within the inner 70% safe bounding box
- Biological touch hold duration (85ms - 210ms)
- Anti-ban non-repetition guarantees
- Responsive cancellation halting immediately on stop_requested
"""
import time
import random
from typing import Any, Callable, List, Optional, Tuple

from bot.core.coordinates import Point, BoundingBox


class FastChainExecutor:
    """Executes fast action chains with biological touch hold and Gaussian cadence."""

    def __init__(self, device: Any, stop_predicate: Optional[Callable[[], bool]] = None):
        self.device = device
        self.stop_predicate = stop_predicate or (lambda: False)

    def execute_chain(
        self,
        targets: List[Tuple[Point, Optional[BoundingBox]]],
        mean_cadence: float = 0.145,
        std_cadence: float = 0.022,
    ) -> bool:
        """Executes sequential actions with Gaussian cadence and biological touch hold.

        Args:
            targets: List of (Point, Optional[BoundingBox]) to tap sequentially.
            mean_cadence: Mean inter-tap delay in seconds (default 0.145s = 145ms).
            std_cadence: Standard deviation of inter-tap delay (default 0.022s = 22ms).

        Returns:
            bool: True if all targets executed successfully, False if cancelled mid-sequence.
        """
        if not targets:
            return True

        for i, (point, box) in enumerate(targets):
            if self.stop_predicate():
                return False

            # Dispatch tap through device to preserve 2D Gaussian point and biological touch hold
            if box is not None:
                self.device.tap(point.x, point.y, normalized=True, box=box)
            else:
                self.device.tap(point.x, point.y, normalized=True)

            # Apply Gaussian inter-tap cadence if not the last target
            if i < len(targets) - 1:
                cadence = random.gauss(mean_cadence, std_cadence)
                clamped_cadence = max(0.105, min(0.200, cadence))
                slept = 0.0
                step = 0.015
                while slept < clamped_cadence:
                    if self.stop_predicate():
                        return False
                    sleep_time = min(step, clamped_cadence - slept)
                    time.sleep(sleep_time)
                    slept += sleep_time

        return True
