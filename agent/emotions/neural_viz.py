#!/usr/bin/env python3
"""Cyberpunk hex visualizer — raw hex grid with neon color jumps."""

from __future__ import annotations

import curses
import math
import os
import signal
import sys
import time
import json
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.emotions.mood_grid import MoodGrid, EMOTION_COLORS, get_mood_grid, save_mood_grid, _GRID_RAM_PATH
from agent.emotions.ram_cache import get_ram_cache


class CyberpunkVisualizer:
    """Renders the mood grid as raw hex values with neon color jumps."""

    def __init__(self, grid: MoodGrid):
        self.grid = grid
        self._running = True
        self._frame = 0
        self._history: list = []
        self._max_history = 80
        self._jitter: dict = {}  # (x,y) -> target_hex for jump animation
        self._pulse_phase = 0.0
        # Mood smoothing
        self._mood_window: list = []
        self._mood_window_size = 120  # frames to average over
        self._current_mood = "neutral"
        self._mood_confidence = 0.0

    def stop(self):
        self._running = False

    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(60)  # ~16 fps for that smooth cyberpunk feel

        # Initialize 256-color pairs
        curses.start_color()
        curses.use_default_colors()

        # Precompute color pairs for common emotions
        self._init_colors()

        # RAM path for cross-process updates
        from agent.emotions.mood_grid import _GRID_RAM_PATH
        self._last_ram_mtime = 0

        while self._running:
            try:
                key = stdscr.getch()
                if key == ord('q') or key == 27:
                    break
                elif key == ord('r'):
                    import random
                    emotions = list(EMOTION_COLORS.keys())
                    self.grid.apply_emotion(random.choice(emotions), random.uniform(0.5, 2.0))
                    save_mood_grid(self.grid)
                elif key == ord('d'):
                    self.grid.decay(0.05)
                    save_mood_grid(self.grid)
            except Exception:
                pass

            # Poll RAM file for updates from other processes
            if _GRID_RAM_PATH.exists():
                try:
                    mtime = _GRID_RAM_PATH.stat().st_mtime
                    if mtime > self._last_ram_mtime:
                        self._last_ram_mtime = mtime
                        data = json.loads(_GRID_RAM_PATH.read_text())
                        new_grid = data.get("grid", data.get("cells"))
                        if new_grid and len(new_grid) == self.grid.GRID_SIZE:
                            self.grid = MoodGrid(new_grid)
                            if "events" in data:
                                self.grid._session_events = data["events"]
                except Exception:
                    pass

            self._frame += 1
            self._pulse_phase += 0.05

            if self._frame % 90 == 0:
                self.grid.decay(0.01)

            mood = self.grid.get_mood()
            self._history.append(mood["overall_hex"])
            if len(self._history) > self._max_history:
                self._history.pop(0)

            # ── Mood smoothing ─────────────────────────────────────────────
            self._mood_window.append(mood["dominant_emotion"])
            if len(self._mood_window) > self._mood_window_size:
                self._mood_window.pop(0)

            from collections import Counter
            mood_counts = Counter(self._mood_window)
            smoothed_mood = mood_counts.most_common(1)[0][0]
            confidence = mood_counts[smoothed_mood] / len(self._mood_window)

            if smoothed_mood != getattr(self, '_current_mood', None):
                self._mood_transition = (getattr(self, '_current_mood', 'neutral'), smoothed_mood)
                self._transition_frame = self._frame
                self._current_mood = smoothed_mood

            in_transition = hasattr(self, '_transition_frame') and (self._frame - self._transition_frame < 90)

            display_mood = smoothed_mood
            if in_transition and hasattr(self, '_mood_transition') and self._mood_transition[0]:
                display_mood = f"{self._mood_transition[0].upper()} → {self._mood_transition[1].upper()}"

            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()

            header = " TOWNEGU // NEURAL HEX MONITOR "
            stdscr.addstr(0, max(0, (max_x - len(header)) // 2), header,
                         curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE)

            status = f" FRAME {self._frame:05d}  MOOD: {display_mood.upper():25s}  ENERGY: {mood['energy']:.3f}  VAL: {mood['valence']:+.3f} "
            stdscr.addstr(1, max(0, (max_x - len(status)) // 2), status,
                         curses.color_pair(2))

            # ── Hex Grid ──
            self._render_hex_grid(stdscr, mood, max_y, max_x)

            # ── Footer ──
            footer = " [q] EXIT  [r] EMOTION SPIKE  [d] DECAY  |  20x20 HEX NEURAL ARRAY "
            stdscr.addstr(max_y - 1, max(0, (max_x - len(footer)) // 2), footer,
                         curses.color_pair(3) | curses.A_DIM)

            stdscr.refresh()
            time.sleep(0.06)

    def _init_colors(self):
        """Initialize neon color pairs."""
        # Use extended colors if available
        try:
            # Neon colors using 256-color palette
            self.NEON_RED = 196
            self.NEON_GREEN = 46
            self.NEON_BLUE = 21
            self.NEON_YELLOW = 226
            self.NEON_MAGENTA = 201
            self.NEON_CYAN = 51
            self.NEON_ORANGE = 202
            self.NEON_PINK = 213
            self.NEON_PURPLE = 93

            curses.init_pair(1, self.NEON_CYAN, -1)      # Header
            curses.init_pair(2, self.NEON_GREEN, -1)     # Status
            curses.init_pair(3, 240, -1)                  # Footer dim
            curses.init_pair(4, self.NEON_RED, -1)        # High energy
            curses.init_pair(5, self.NEON_YELLOW, -1)     # Medium energy
            curses.init_pair(6, self.NEON_BLUE, -1)       # Low energy
            curses.init_pair(7, self.NEON_MAGENTA, -1)    # Pulse
            curses.init_pair(8, self.NEON_ORANGE, -1)     # Warning
            curses.init_pair(9, self.NEON_PURPLE, -1)     # Special
            curses.init_pair(10, 250, -1)                 # Very dim
        except Exception:
            # Fallback to basic colors
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_WHITE, -1)
            curses.init_pair(4, curses.COLOR_RED, -1)
            curses.init_pair(5, curses.COLOR_YELLOW, -1)
            curses.init_pair(6, curses.COLOR_BLUE, -1)
            curses.init_pair(7, curses.COLOR_MAGENTA, -1)
            curses.init_pair(8, curses.COLOR_RED, -1)
            curses.init_pair(9, curses.COLOR_MAGENTA, -1)
            curses.init_pair(10, curses.COLOR_WHITE, -1)

    def _hex_to_neon_pair(self, hex_color: str, intensity: float) -> int:
        """Map hex color to nearest curses color pair."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

        # Determine dominant channel
        if intensity > 0.7:
            if r > 200 and g < 100 and b < 100:
                return 4  # NEON_RED
            elif r > 200 and g > 150 and b < 100:
                return 5  # NEON_YELLOW
            elif r < 100 and g < 100 and b > 200:
                return 6  # NEON_BLUE
            elif r > 200 and g < 100 and b > 200:
                return 7  # NEON_MAGENTA
            elif r < 100 and g > 200 and b > 200:
                return 1  # NEON_CYAN
            elif r > 200 and g > 100 and b < 100:
                return 8  # NEON_ORANGE
            elif r > 150 and g < 100 and b > 150:
                return 9  # NEON_PURPLE
            else:
                return 5
        elif intensity > 0.4:
            return 5
        elif intensity > 0.2:
            return 6
        else:
            return 10

    def _render_hex_grid(self, stdscr, mood, max_y, max_x):
        """Render 20×20 grid as raw hex values with neon jumps."""
        grid_size = self.grid.GRID_SIZE
        center = grid_size // 2

        # Layout: each cell takes 7 chars (#XXXXXX)
        cell_w = 7
        grid_width = grid_size * cell_w
        grid_height = grid_size

        start_y = max(2, (max_y - grid_height) // 2)
        start_x = max(2, (max_x - grid_width) // 2)

        energy = mood["energy"]

        for gy in range(grid_size):
            y = start_y + gy
            if y >= max_y - 2 or y < 3:
                continue

            line = ""
            for gx in range(grid_size):
                x = start_x + gx * cell_w
                if x >= max_x - cell_w:
                    continue

                hex_color = self.grid.get_cell(gx, gy)

                # Neural pulse: jump intensity based on distance from center + sine
                dist = math.sqrt((gx - center) ** 2 + (gy - center) ** 2)
                pulse = 0.6 + 0.4 * math.sin(self._pulse_phase - dist * 0.4)

                # Intensity modulated by energy and distance from center
                intensity = min(1.0, energy * pulse + 0.2)

                # Decide whether to show hex value or blanked
                if intensity > 0.65:
                    # Show full hex with color
                    display = hex_color.upper()
                    color_pair = self._hex_to_neon_pair(hex_color, intensity)

                    try:
                        stdscr.addstr(y, x, display,
                                     curses.color_pair(color_pair) | curses.A_BOLD)
                    except curses.error:
                        pass
                elif intensity > 0.35:
                    # Show dimmed hex
                    display = hex_color.upper()
                    try:
                        stdscr.addstr(y, x, display,
                                     curses.color_pair(10) | curses.A_DIM)
                    except curses.error:
                        pass
                else:
                    # Too low energy — show dots
                    try:
                        stdscr.addstr(y, x, "·······",
                                     curses.color_pair(10))
                    except curses.error:
                        pass

                # Occasionally trigger a "jump" — brief flash to white
                if intensity > 0.85 and self._frame % 7 == 0 and dist < 5:
                    try:
                        stdscr.addstr(y, x, hex_color.upper(),
                                     curses.color_pair(5) | curses.A_BOLD | curses.A_BLINK)
                    except curses.error:
                        pass


def main():
    grid = get_mood_grid()
    viz = CyberpunkVisualizer(grid)

    def handler(sig, frame):
        viz.stop()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    curses.wrapper(viz.run)


if __name__ == "__main__":
    main()
