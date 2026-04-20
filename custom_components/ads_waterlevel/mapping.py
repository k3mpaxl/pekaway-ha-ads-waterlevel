"""Helpers to build and evaluate tank-level mapping curves."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def ch_human_to_ain(channel: int) -> int:
    """Accept 1..4 (board label) or 0..3 (AIN). Return AIN 0..3."""
    ch = int(channel)
    if 1 <= ch <= 4:
        return ch - 1
    if 0 <= ch <= 3:
        return ch
    raise ValueError(f"Invalid channel: {channel}")


def build_linear_mapping(
    v_max: float, invert: bool, steps: int = 10
) -> list[tuple[float, float]]:
    """Build a linear V→L curve 0..v_max → 0..100 L (optionally inverted)."""
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        v = round(v_max * i / steps, 3)
        level = round(100.0 * i / steps, 1)
        if invert:
            level = round(100.0 - level, 1)
        pts.append((v, level))
    return pts


def normalize_mapping_points(
    items: Iterable[dict[str, Any]], v_max: float, invert: bool
) -> list[tuple[float, float]]:
    """Normalize a raw list of {v, l} dicts into a sorted mapping."""
    pts: list[tuple[float, float]] = []
    for it in items:
        pts.append((float(it["v"]), float(it["l"])))
    pts.sort(key=lambda x: x[0])

    have_zero = any(abs(v) < 1e-6 for v, _ in pts)
    have_max = any(abs(v - v_max) < 1e-6 for v, _ in pts)
    if not have_zero:
        pts = [(0.0, 100.0 if invert else 0.0), *pts]
    if not have_max:
        pts = [*pts, (v_max, 0.0 if invert else 100.0)]
    return pts


def interp(points: list[tuple[float, float]], x: float) -> float:
    """Linear interpolation over sorted (x→y) points."""
    if not points:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]
