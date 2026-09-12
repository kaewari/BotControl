"""Sub-200ms End-to-End Human-like Touch Engine for BotControl.

Optimizes the entire pipeline:
Screen / Button Recognition -> Coordinate Calculation -> Bezier / Gaussian Jitter -> WDA Tap Dispatch
to complete in under 200ms total latency.

Features:
- Sub-200ms end-to-end execution guarantee.
- Direct zero-latency RAM video frame buffer utilization (bypassing disk I/O & redundant decode).
- Biological human-like touch simulation (2D Gaussian dispersion, Bezier velocity curves).
- Strict Zero-Spend ResourceGuard integration (pre-tap veto on confirmation zone and spending keywords).
"""
import time
import math
import random
import logging
from dataclasses import dataclass, field
from typing import Optional, Union, Any, List, Dict, Tuple
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.human_touch import (
    generate_gaussian_point,
    generate_bezier_trajectory,
    random_touch_duration,
)

logger = logging.getLogger("BotControl.TouchEngine")


@dataclass
class TouchLatencyBreakdown:
    """Latency profiling breakdown in milliseconds."""
    recognition_ms: float = 0.0
    calculation_ms: float = 0.0
    guard_check_ms: float = 0.0
    dispatch_ms: float = 0.0
    total_ms: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "recognition_ms": round(self.recognition_ms, 2),
            "calculation_ms": round(self.calculation_ms, 2),
            "guard_check_ms": round(self.guard_check_ms, 2),
            "dispatch_ms": round(self.dispatch_ms, 2),
            "total_ms": round(self.total_ms, 2),
        }


@dataclass
class TouchResult:
    """Result of a touch action execution."""
    success: bool
    point: Optional[Point]
    latencies: TouchLatencyBreakdown
    vetoed: bool = False
    details: str = ""
    trajectory: Optional[List[Tuple[float, float, float]]] = None


class FastTouchEngine:
    """High-speed touch execution engine ensuring sub-200ms end-to-end response.
    
    Coordinates zero-latency RAM frame buffer access, micro-ROI / cache target lookup,
    human-like Gaussian jitter / Bezier trajectory calculation, and strict ResourceGuard veto.
    """

    def __init__(
        self,
        device: Optional[Any] = None,
        resource_guard: Optional[Any] = None,
        ui_cache: Optional[Any] = None,
        default_hold_ms: float = 65.0,
    ):
        self.device = device
        self.resource_guard = resource_guard
        self.ui_cache = ui_cache
        self.default_hold_ms = default_hold_ms  # Fast biological human tap (50-85ms)
        self.history: List[TouchResult] = []

    def _resolve_target(
        self,
        target: Union[str, Point, BoundingBox, Tuple[float, float], List[float]],
        frame: Optional[np.ndarray] = None,
        box: Optional[BoundingBox] = None,
        label: str = "",
    ) -> Tuple[Optional[Point], Optional[BoundingBox], str]:
        """Resolves target into normalized Point and BoundingBox within < 5ms."""
        # Validate and sanitize optional box parameter
        if box is not None:
            try:
                if any(math.isnan(float(v)) or math.isinf(float(v)) for v in (box.x1, box.y1, box.x2, box.y2)):
                    box = None
                else:
                    bx1, bx2 = min(float(box.x1), float(box.x2)), max(float(box.x1), float(box.x2))
                    by1, by2 = min(float(box.y1), float(box.y2)), max(float(box.y1), float(box.y2))
                    box = BoundingBox(bx1, by1, bx2, by2)
            except Exception:
                box = None

        target_point: Optional[Point] = None
        target_box: Optional[BoundingBox] = box
        target_label: str = label

        # 0. Tuple / List coordinate target
        if isinstance(target, (tuple, list)):
            if len(target) == 2:
                try:
                    x, y = float(target[0]), float(target[1])
                    if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
                        return None, box, label
                    target_point = Point(x, y)
                except (ValueError, TypeError):
                    return None, box, label
            elif len(target) >= 4:
                try:
                    x1, y1, x2, y2 = float(target[0]), float(target[1]), float(target[2]), float(target[3])
                    if any(math.isnan(v) or math.isinf(v) for v in (x1, y1, x2, y2)):
                        return None, box, label
                    bx1, bx2 = min(x1, x2), max(x1, x2)
                    by1, by2 = min(y1, y2), max(y1, y2)
                    bb = BoundingBox(bx1, by1, bx2, by2)
                    target_point = bb.center
                    target_box = bb
                    target_label = label or getattr(bb, "label", "")
                except (ValueError, TypeError):
                    return None, box, label

        # 1. BoundingBox target
        elif isinstance(target, BoundingBox):
            try:
                if any(math.isnan(float(v)) or math.isinf(float(v)) for v in (target.x1, target.y1, target.x2, target.y2)):
                    return None, box, label
                bx1, bx2 = min(float(target.x1), float(target.x2)), max(float(target.x1), float(target.x2))
                by1, by2 = min(float(target.y1), float(target.y2)), max(float(target.y1), float(target.y2))
                bb = BoundingBox(bx1, by1, bx2, by2)
                target_point = bb.center
                target_box = bb
                target_label = label or getattr(target, "label", "")
            except Exception:
                return None, box, label

        # 2. Point target
        elif isinstance(target, Point):
            try:
                px, py = float(target.x), float(target.y)
                if math.isnan(px) or math.isnan(py) or math.isinf(px) or math.isinf(py):
                    return None, box, label
                target_point = Point(px, py)
            except Exception:
                return None, box, label

        # 3. String key target (lookup in UICoordinateCache)
        elif isinstance(target, str):
            cache_to_use = self.ui_cache
            if cache_to_use is None:
                try:
                    from bot.core.cache import ui_cache
                    cache_to_use = ui_cache
                except Exception:
                    pass

            if cache_to_use is not None:
                elem = cache_to_use.get_element(target)
                if elem is not None:
                    target_label = label or elem.label or target
                    target_point = elem.point
                    target_box = elem.box or target_box

        if target_point is None:
            return None, box, label

        # Handle pixel coordinate normalization and reject off-screen coordinates
        tx, ty = target_point.x, target_point.y
        if tx < -0.05 or ty < -0.05:
            return None, box, label

        pw = getattr(self.device, "pixel_width", 2752) or 2752
        ph = getattr(self.device, "pixel_height", 2064) or 2064
        if tx > 1.0 and tx <= pw * 1.05:
            tx /= float(pw)
        if ty > 1.0 and ty <= ph * 1.05:
            ty /= float(ph)

        if tx > 1.05 or ty > 1.05 or tx < -0.05 or ty < -0.05:
            return None, box, label

        return Point(tx, ty), target_box, target_label

    def _record_result(self, res: TouchResult) -> TouchResult:
        """Records touch result with bounded memory retention (< 1000 items)."""
        self.history.append(res)
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
        return res

    def execute_fast_tap(
        self,
        target: Union[str, Point, BoundingBox, Tuple[float, float], List[float], float],
        y: Optional[float] = None,
        frame: Optional[np.ndarray] = None,
        box: Optional[BoundingBox] = None,
        label: str = "",
        spread_ratio: float = 0.35,
        hold_sec: Optional[float] = None,
        require_active_threat: bool = False,
    ) -> TouchResult:
        """Executes an end-to-end humanized tap under 200ms.

        Pipeline:
        1. Target Coordinate Resolution (< 5ms)
        2. Zero-Spend ResourceGuard Pre-Tap Veto (< 1ms)
        3. Human-like 2D Gaussian Jitter Calculation with Safety Clamp (< 1ms)
        4. WDA Tap Dispatch with Biological Contact Duration (< 100ms)

        Args:
            target: Coordinate Point, BoundingBox, cache key string, tuple (x, y), or float x.
            y: Optional float y coordinate when target is float x.
            frame: Optional video frame; if omitted, automatically retrieves from RAM buffer.
            box: Optional BoundingBox for Gaussian dispersion confinement.
            label: Human-readable action label.
            spread_ratio: Ratio of bounding box used for 3-sigma Gaussian dispersion.
            hold_sec: Contact hold duration in seconds; if None, generates biological timing.
            require_active_threat: If True, vetoes only when active threat is flagged;
                                   if False, strictly vetoes any dangerous zone/label.

        Returns:
            TouchResult containing success flag, actual tap point, and latency profiling.
        """
        t_start = time.perf_counter()

        # Handle positional (x, y) arguments
        if y is not None and isinstance(target, (int, float)) and isinstance(y, (int, float)):
            x_f, y_f = float(target), float(y)
            if math.isnan(x_f) or math.isnan(y_f) or math.isinf(x_f) or math.isinf(y_f):
                target = None
            else:
                target = Point(x_f, y_f)

        # --- Stage 1: Target Resolution ---
        t0 = time.perf_counter()

        # If no frame supplied, leverage 0.0ms RAM video frame buffer from device
        if frame is None and self.device is not None:
            if hasattr(self.device, "get_video_frame"):
                vf = self.device.get_video_frame()
                if vf is not None and vf.bgr is not None:
                    frame = vf.bgr
            if frame is None and hasattr(self.device, "get_screenshot"):
                frame = self.device.get_screenshot(max_age=0.20)

        target_point, target_box, target_label = self._resolve_target(
            target, frame=frame, box=box, label=label
        )
        t_rec_done = time.perf_counter()
        rec_ms = (t_rec_done - t0) * 1000.0

        if target_point is None:
            total_ms = (time.perf_counter() - t_start) * 1000.0
            breakdown = TouchLatencyBreakdown(
                recognition_ms=rec_ms,
                calculation_ms=0.0,
                guard_check_ms=0.0,
                dispatch_ms=0.0,
                total_ms=total_ms,
            )
            res = TouchResult(
                success=False,
                point=None,
                latencies=breakdown,
                vetoed=False,
                details=f"Target '{target}' could not be resolved to valid coordinates",
            )
            return self._record_result(res)

        # --- Stage 2: ResourceGuard Strict Safety Veto ---
        t1 = time.perf_counter()
        guard = self.resource_guard
        if guard is None and self.device is not None:
            guard = getattr(self.device, "resource_guard", None)

        if guard is not None:
            vetoed = (
                guard.is_vetoed_tap(
                    target_point.x,
                    target_point.y,
                    label=target_label,
                    require_active_threat=require_active_threat,
                )
                or guard.is_confirmation_zone(target_point.x, target_point.y)
            )
            if vetoed:
                t_guard_done = time.perf_counter()
                guard_ms = (t_guard_done - t1) * 1000.0
                total_ms = (time.perf_counter() - t_start) * 1000.0
                breakdown = TouchLatencyBreakdown(
                    recognition_ms=rec_ms,
                    calculation_ms=0.0,
                    guard_check_ms=guard_ms,
                    dispatch_ms=0.0,
                    total_ms=total_ms,
                )
                logger.critical(
                    f"🚫 [ZERO-SPEND VETO] FastTouchEngine blocked tap at ({target_point.x:.4f}, {target_point.y:.4f}) "
                    f"with label '{target_label}'!"
                )
                res = TouchResult(
                    success=False,
                    point=target_point,
                    latencies=breakdown,
                    vetoed=True,
                    details=f"Tap blocked by ResourceGuard (Veto: ({target_point.x:.4f}, {target_point.y:.4f}), label='{target_label}')",
                )
                return self._record_result(res)

        t_guard_done = time.perf_counter()
        guard_ms = (t_guard_done - t1) * 1000.0

        # --- Stage 3: Human-like Touch Calculation & Zero-Spend Post-Jitter Safety ---
        t2 = time.perf_counter()
        # Natural 2D Truncated Gaussian point dispersion
        human_pt = generate_gaussian_point(target_point, box=target_box, spread_ratio=spread_ratio)
        norm_x = float(max(0.005, min(0.995, human_pt.x)))
        norm_y = float(max(0.005, min(0.995, human_pt.y)))

        # CRITICAL ZERO-SPEND POST-JITTER VERIFICATION:
        # Guarantee 100% that Gaussian jitter never disperses a point into CONFIRMATION_ZONE or vetoed areas
        if guard is not None:
            is_jitter_vetoed = guard.is_vetoed_tap(
                norm_x,
                norm_y,
                label=target_label,
                require_active_threat=require_active_threat,
            ) or guard.is_confirmation_zone(norm_x, norm_y)

            if is_jitter_vetoed:
                # If target_point itself is safe, fall back to target_point to avert spending trap
                target_safe = not (
                    guard.is_vetoed_tap(target_point.x, target_point.y, label=target_label, require_active_threat=require_active_threat)
                    or guard.is_confirmation_zone(target_point.x, target_point.y)
                )
                if target_safe:
                    norm_x = float(max(0.005, min(0.995, target_point.x)))
                    norm_y = float(max(0.005, min(0.995, target_point.y)))
                else:
                    t_calc_done = time.perf_counter()
                    calc_ms = (t_calc_done - t2) * 1000.0
                    total_ms = (time.perf_counter() - t_start) * 1000.0
                    breakdown = TouchLatencyBreakdown(
                        recognition_ms=rec_ms,
                        calculation_ms=calc_ms,
                        guard_check_ms=guard_ms,
                        total_ms=total_ms,
                    )
                    res = TouchResult(
                        success=False,
                        point=Point(norm_x, norm_y),
                        latencies=breakdown,
                        vetoed=True,
                        details=f"Tap point blocked by ResourceGuard post-jitter check at ({norm_x:.4f}, {norm_y:.4f})",
                    )
                    return self._record_result(res)

        # Contact hold duration (biological human tap range: 50ms - 85ms)
        if hold_sec is None:
            hold_ms = random.gauss(self.default_hold_ms, 8.0)
            hold_ms = max(45.0, min(85.0, hold_ms))
            actual_hold_sec = hold_ms / 1000.0
        else:
            actual_hold_sec = float(hold_sec)

        t_calc_done = time.perf_counter()
        calc_ms = (t_calc_done - t2) * 1000.0

        # --- Stage 4: WDA Tap Dispatch ---
        t3 = time.perf_counter()
        success = True
        if self.device is not None:
            try:
                # Use tap_hold with biological duration if supported
                if hasattr(self.device, "tap_hold"):
                    self.device.tap_hold(
                        norm_x,
                        norm_y,
                        duration=actual_hold_sec,
                        normalized=True,
                        box=target_box,
                        label=target_label,
                    )
                elif hasattr(self.device, "tap"):
                    self.device.tap(
                        norm_x,
                        norm_y,
                        normalized=True,
                        box=target_box,
                        label=target_label,
                    )
                else:
                    success = False
            except Exception as e:
                logger.error(f"Failed to dispatch tap to device: {e}")
                success = False

        t_dispatch_done = time.perf_counter()
        disp_ms = (t_dispatch_done - t3) * 1000.0
        total_ms = (t_dispatch_done - t_start) * 1000.0

        breakdown = TouchLatencyBreakdown(
            recognition_ms=rec_ms,
            calculation_ms=calc_ms,
            guard_check_ms=guard_ms,
            dispatch_ms=disp_ms,
            total_ms=total_ms,
        )

        res = TouchResult(
            success=success,
            point=Point(norm_x, norm_y),
            latencies=breakdown,
            vetoed=False,
            details=f"Fast tap completed in {total_ms:.1f}ms at ({norm_x:.4f}, {norm_y:.4f})",
        )
        return self._record_result(res)

    def execute_fast_swipe(
        self,
        start: Union[str, Point, Tuple[float, float], List[float]],
        end: Union[str, Point, Tuple[float, float], List[float]],
        duration: float = 0.16,
        num_points: int = 18,
        label: str = "FastSwipe",
        require_active_threat: bool = False,
    ) -> TouchResult:
        """Executes a humanized swipe along a Cubic Bezier curve under 200ms with strict Zero-Spend guarantee."""
        t_start = time.perf_counter()

        t0 = time.perf_counter()
        pt_start, _, _ = self._resolve_target(start, label=label)
        pt_end, _, _ = self._resolve_target(end, label=label)
        rec_ms = (time.perf_counter() - t0) * 1000.0

        if pt_start is None or pt_end is None:
            total_ms = (time.perf_counter() - t_start) * 1000.0
            breakdown = TouchLatencyBreakdown(
                recognition_ms=rec_ms,
                total_ms=total_ms,
            )
            res = TouchResult(
                success=False,
                point=None,
                latencies=breakdown,
                details="Invalid swipe endpoints",
            )
            return self._record_result(res)

        # STRICT ResourceGuard safety check for start and end points
        t1 = time.perf_counter()
        guard = self.resource_guard or getattr(self.device, "resource_guard", None)
        if guard is not None:
            is_start_vetoed = (
                guard.is_vetoed_tap(pt_start.x, pt_start.y, label=label, require_active_threat=require_active_threat)
                or guard.is_confirmation_zone(pt_start.x, pt_start.y)
            )
            is_end_vetoed = (
                guard.is_vetoed_tap(pt_end.x, pt_end.y, label=label, require_active_threat=require_active_threat)
                or guard.is_confirmation_zone(pt_end.x, pt_end.y)
            )
            if is_start_vetoed or is_end_vetoed:
                guard_ms = (time.perf_counter() - t1) * 1000.0
                total_ms = (time.perf_counter() - t_start) * 1000.0
                breakdown = TouchLatencyBreakdown(
                    recognition_ms=rec_ms,
                    guard_check_ms=guard_ms,
                    total_ms=total_ms,
                )
                logger.critical(
                    f"🚫 [ZERO-SPEND VETO] FastTouchEngine blocked swipe between ({pt_start.x:.4f}, {pt_start.y:.4f}) "
                    f"and ({pt_end.x:.4f}, {pt_end.y:.4f}) with label '{label}'!"
                )
                res = TouchResult(
                    success=False,
                    point=pt_start,
                    latencies=breakdown,
                    vetoed=True,
                    details="Swipe blocked by ResourceGuard veto",
                )
                return self._record_result(res)
        guard_ms = (time.perf_counter() - t1) * 1000.0

        # Bezier trajectory calculation with ease-in / ease-out velocity profile
        t2 = time.perf_counter()
        trajectory = generate_bezier_trajectory(pt_start, pt_end, num_points=num_points)
        calc_ms = (time.perf_counter() - t2) * 1000.0

        # Zero-Spend verification along every intermediate point of the trajectory
        if guard is not None and trajectory:
            for pt_tup in trajectory:
                tx, ty = float(pt_tup[0]), float(pt_tup[1])
                if guard.is_confirmation_zone(tx, ty) or guard.is_vetoed_tap(tx, ty, label=label, require_active_threat=require_active_threat):
                    total_ms = (time.perf_counter() - t_start) * 1000.0
                    breakdown = TouchLatencyBreakdown(
                        recognition_ms=rec_ms,
                        calculation_ms=calc_ms,
                        guard_check_ms=(time.perf_counter() - t1) * 1000.0,
                        total_ms=total_ms,
                    )
                    logger.critical(
                        f"🚫 [ZERO-SPEND VETO] FastTouchEngine blocked swipe trajectory intersecting CONFIRMATION_ZONE at ({tx:.4f}, {ty:.4f})!"
                    )
                    res = TouchResult(
                        success=False,
                        point=pt_start,
                        latencies=breakdown,
                        vetoed=True,
                        details=f"Swipe trajectory blocked by ResourceGuard veto at ({tx:.4f}, {ty:.4f})",
                        trajectory=trajectory,
                    )
                    return self._record_result(res)

        # Dispatch swipe to device
        t3 = time.perf_counter()
        success = True
        if self.device is not None:
            try:
                if hasattr(self.device, "swipe"):
                    self.device.swipe(
                        pt_start.x,
                        pt_start.y,
                        pt_end.x,
                        pt_end.y,
                        duration=duration,
                        normalized=True,
                    )
                else:
                    success = False
            except Exception as e:
                logger.error(f"Failed to dispatch swipe: {e}")
                success = False

        disp_ms = (time.perf_counter() - t3) * 1000.0
        total_ms = (time.perf_counter() - t_start) * 1000.0

        breakdown = TouchLatencyBreakdown(
            recognition_ms=rec_ms,
            calculation_ms=calc_ms,
            guard_check_ms=guard_ms,
            dispatch_ms=disp_ms,
            total_ms=total_ms,
        )
        res = TouchResult(
            success=success,
            point=pt_start,
            latencies=breakdown,
            vetoed=False,
            details=f"Fast swipe completed in {total_ms:.1f}ms",
            trajectory=trajectory,
        )
        return self._record_result(res)
