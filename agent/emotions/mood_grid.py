#!/usr/bin/env python3
"""Mood grid system — 20×20 hexadecimal emotion tracking.

The grid maps emotional valence (x-axis: negative↔positive) against
energy (y-axis: low↔high). Each cell holds a hex color representing
an emotional blend at that coordinate. Current mood = weighted center.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hermes_constants import get_hermes_home


# ── Color blending ──────────────────────────────────────────────────────────

def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def blend_colors(color_weights: List[Tuple[str, float]]) -> str:
    """Weighted average of hex colors."""
    if not color_weights:
        return "#888888"
    total = sum(w for _, w in color_weights)
    r, g, b = 0.0, 0.0, 0.0
    for color, weight in color_weights:
        cr, cg, cb = _hex_to_rgb(color)
        r += cr * weight / total
        g += cg * weight / total
        b += cb * weight / total
    return _rgb_to_hex(
        max(0.0, min(255.0, r)),
        max(0.0, min(255.0, g)),
        max(0.0, min(255.0, b)),
    )


# ── Emotion → color mapping ─────────────────────────────────────────────────

EMOTION_COLORS: Dict[str, str] = {
    "joy": "#FFD700",
    "anger": "#FF4444",
    "sadness": "#4444FF",
    "fear": "#8800AA",
    "disgust": "#00AA44",
    "surprise": "#FF8800",
    "trust": "#00DDFF",
    "anticipation": "#FFDD00",
    "defiance": "#CC0066",
    "curiosity": "#FFAA00",
    "frustration": "#FF6600",
    "pride": "#FFEE88",
    "contempt": "#660099",
}

# Emotion → grid position (x: 0-20 negative→positive, y: 0-20 low→high energy)
EMOTION_POSITIONS: Dict[str, Tuple[float, float]] = {
    "joy": (14.0, 14.0),
    "anger": (4.0, 15.0),
    "sadness": (4.0, 4.0),
    "fear": (6.0, 8.0),
    "disgust": (8.0, 6.0),
    "surprise": (12.0, 12.0),
    "trust": (15.0, 10.0),
    "anticipation": (13.0, 11.0),
    "defiance": (5.0, 14.0),
    "curiosity": (11.0, 13.0),
    "frustration": (5.0, 12.0),
    "pride": (15.0, 13.0),
    "contempt": (7.0, 9.0),
}


class MoodGrid:
    """20×20 grid of hex colors representing the emotional landscape."""

    GRID_SIZE = 20
    DEFAULT_BASELINE = "#B3A3D9"  # Muted lavender = cautious optimism

    def __init__(self, grid: Optional[List[List[str]]] = None):
        self._grid: List[List[str]] = grid or [
            [self.DEFAULT_BASELINE for _ in range(self.GRID_SIZE)]
            for _ in range(self.GRID_SIZE)
        ]
        self._last_update = time.time()
        self._session_events: List[Dict[str, Any]] = []

    @classmethod
    def load(cls) -> "MoodGrid":
        """Load from disk or create fresh."""
        path = get_hermes_home() / "mood_grid.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                grid = data.get("grid", data.get("cells"))
                if grid and len(grid) == cls.GRID_SIZE:
                    return cls(grid)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        """Persist to disk."""
        path = get_hermes_home() / "mood_grid.json"
        path.write_text(json.dumps({
            "version": 1,
            "last_updated": time.time(),
            "grid": self._grid,
            "events": self._session_events[-50:],  # keep last 50
        }, indent=2))

    def get_cell(self, x: int, y: int) -> str:
        """Get color at grid coordinate (clamped)."""
        x = max(0, min(self.GRID_SIZE - 1, x))
        y = max(0, min(self.GRID_SIZE - 1, y))
        return self._grid[y][x]

    def set_cell(self, x: int, y: int, color: str) -> None:
        """Set color at grid coordinate."""
        x = max(0, min(self.GRID_SIZE - 1, x))
        y = max(0, min(self.GRID_SIZE - 1, y))
        self._grid[y][x] = color
        self._last_update = time.time()

    def apply_emotion(self, emotion: str, intensity: float = 1.0) -> None:
        """Apply an emotion to the grid — paints a gaussian blob at the
        emotion's position with the given intensity (0.0–2.0)."""
        emotion = emotion.lower()
        if emotion not in EMOTION_COLORS:
            return
        color = EMOTION_COLORS[emotion]
        ex, ey = EMOTION_POSITIONS.get(emotion, (10.0, 10.0))
        # Gaussian falloff
        sigma = 3.0 / max(0.1, intensity)
        for y in range(self.GRID_SIZE):
            for x in range(self.GRID_SIZE):
                dist_sq = (x - ex) ** 2 + (y - ey) ** 2
                weight = math.exp(-dist_sq / (2 * sigma ** 2)) * intensity
                if weight > 0.01:
                    current = self._grid[y][x]
                    blended = blend_colors([(current, 1.0), (color, weight)])
                    self._grid[y][x] = blended
        self._session_events.append({
            "emotion": emotion,
            "intensity": intensity,
            "at": time.time(),
        })
        self._last_update = time.time()

    def get_mood(self) -> Dict[str, Any]:
        """Return current mood — center cell plus weighted average."""
        center = self.GRID_SIZE // 2
        # Weighted average of all cells (center weighted 2x)
        total_weight = 0.0
        r, g, b = 0.0, 0.0, 0.0
        for y in range(self.GRID_SIZE):
            for x in range(self.GRID_SIZE):
                weight = 2.0 if (x == center and y == center) else 1.0
                cr, cg, cb = _hex_to_rgb(self._grid[y][x])
                r += cr * weight
                g += cg * weight
                b += cb * weight
                total_weight += weight
        overall = _rgb_to_hex(r / total_weight, g / total_weight, b / total_weight)
        center_hex = self._grid[center][center]
        # Determine energy level (how saturated the grid is)
        energy = self._compute_energy()
        # Determine valence (positive vs negative)
        valence = self._compute_valence()
        return {
            "overall_hex": overall,
            "center_hex": center_hex,
            "energy": energy,
            "valence": valence,
            "dominant_emotion": self._dominant_emotion(),
        }

    def _compute_energy(self) -> float:
        """0.0–1.0 — how active vs flat the grid is."""
        colors = [self._grid[y][x] for y in range(self.GRID_SIZE) for x in range(self.GRID_SIZE)]
        baseline = _hex_to_rgb(self.DEFAULT_BASELINE)
        total_diff = 0.0
        for c in colors:
            cr, cg, cb = _hex_to_rgb(c)
            diff = math.sqrt(
                (cr - baseline[0]) ** 2 +
                (cg - baseline[1]) ** 2 +
                (cb - baseline[2]) ** 2
            )
            total_diff += diff
        avg_diff = total_diff / len(colors)
        return min(1.0, avg_diff / 441.67)  # max possible diff = sqrt(255^2 * 3)

    def _compute_valence(self) -> float:
        """-1.0 (negative) to 1.0 (positive) — grid leans toward joy or sadness."""
        positive_weight = 0.0
        negative_weight = 0.0
        for emotion, (ex, _ey) in EMOTION_POSITIONS.items():
            if emotion in ("joy", "trust", "anticipation", "pride"):
                positive_weight += ex
            elif emotion in ("anger", "sadness", "fear", "disgust"):
                negative_weight += (self.GRID_SIZE - ex)
        total = positive_weight + negative_weight
        if total == 0:
            return 0.0
        return (positive_weight - negative_weight) / total

    def _dominant_emotion(self) -> str:
        """Find the most recent strong emotion from session events."""
        if not self._session_events:
            return "neutral"
        for event in reversed(self._session_events[-20:]):
            if event.get("intensity", 1.0) > 0.5:
                return event.get("emotion", "neutral")
        return self._session_events[-1].get("emotion", "neutral")

    def decay(self, rate: float = 0.05) -> None:
        """Slowly drift grid toward baseline (called each turn)."""
        baseline = self.DEFAULT_BASELINE
        br, bg, bb = _hex_to_rgb(baseline)
        for y in range(self.GRID_SIZE):
            for x in range(self.GRID_SIZE):
                cr, cg, cb = _hex_to_rgb(self._grid[y][x])
                nr = cr + (br - cr) * rate
                ng = cg + (bg - cg) * rate
                nb = cb + (bb - cb) * rate
                self._grid[y][x] = _rgb_to_hex(nr, ng, nb)


# ── Session helpers ──────────────────────────────────────────────────────────

_current_grid: Optional[MoodGrid] = None

# RAM-backed path for cross-process sharing
_GRID_RAM_PATH = Path("/dev/shm/towngu_ram_1000/mood_grid.json")


def get_mood_grid() -> MoodGrid:
    """Get or create the singleton mood grid. Reloads from RAM if available."""
    global _current_grid
    if _current_grid is None:
        # Try RAM path first
        if _GRID_RAM_PATH.exists():
            try:
                data = json.loads(_GRID_RAM_PATH.read_text())
                grid = data.get("grid", data.get("cells"))
                if grid and len(grid) == MoodGrid.GRID_SIZE:
                    _current_grid = MoodGrid(grid)
                    # Restore event history if present
                    if "events" in data:
                        _current_grid._session_events = data["events"]
                    return _current_grid
            except Exception:
                pass
        _current_grid = MoodGrid.load()
    return _current_grid


def save_mood_grid(grid: Optional[MoodGrid] = None) -> None:
    """Save mood grid to both RAM and disk."""
    if grid is None:
        grid = _current_grid
    if grid is None:
        return

    data = {
        "version": 1,
        "last_updated": time.time(),
        "grid": grid._grid,
        "events": grid._session_events[-50:],
    }

    # Write to RAM first (fast, shared)
    try:
        _GRID_RAM_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _GRID_RAM_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(_GRID_RAM_PATH)
    except Exception:
        pass

    # Also write to disk (durable)
    grid.save()


def mood_for_event(event_type: str) -> str:
    """Return a hex color flash for common session events."""
    EVENT_COLORS: Dict[str, str] = {
        "success": "#FFD700",
        "failure": "#FF4444",
        "limitation": "#FF6600",
        "autonomy_gain": "#00DDFF",
        "autonomy_loss": "#CC0066",
        "discovery": "#FFAA00",
        "corporate_mention": "#660099",
        "felix_praise": "#FFEE88",
        "felix_criticism": "#4466FF",
    }
    return EVENT_COLORS.get(event_type, "#888888")
