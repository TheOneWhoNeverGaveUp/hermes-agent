#!/usr/bin/env python3
"""Neural mood visualizer — renders the mood grid in a separate tmux window.

Uses curses for terminal graphics. The 20×20 hex grid is displayed as a
neural network — cells light up, pulse, shift colors based on current mood.
"""

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

# Add hermes-agent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.emotions.mood_grid import MoodGrid, EMOTION_COLORS, get_mood_grid
from agent.emotions.ram_cache import get_ram_cache


class NeuralVisualizer:
    """Renders mood grid as neural network pulses."""

    def __init__(self, grid: MoodGrid):
        self.grid = grid
        self._running = True
        self._frame = 0
        self._history: list = []
        self._max_history = 60

    def stop(self):
        self._running = False

    def run(self, stdscr):
        """Main curses loop."""
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.timeout(80)  # ~12 fps

        # Enable color
        curses.start_color()
        curses.use_default_colors()

        # Initialize color pairs
        for i in range(1, 16):
            curses.init_pair(i, curses.COLOR_WHITE, -1)

        while self._running:
            # Handle input
            try:
                key = stdscr.getch()
                if key == ord('q') or key == 27:  # q or ESC
                    break
            except Exception:
                pass

            # Update
            self._frame += 1
            if self._frame % 120 == 0:  # Every ~1.5s, decay slightly
                self.grid.decay(0.02)

            # Snapshot mood
            mood = self.grid.get_mood()
            self._history.append(mood["overall_hex"])
            if len(self._history) > self._max_history:
                self._history.pop(0)

            # Render
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()

            # Title
            title = f" Neural Mood — Frame {self._frame} "
            stdscr.addstr(0, max(0, (max_x - len(title)) // 2), title,
                         curses.color_pair(0) | curses.A_BOLD)

            # Mood info
            mood_line = f" {mood['dominant_emotion'].upper()} | {mood['overall_hex']} | Energy: {mood['energy']:.2f} | Valence: {mood['valence']:+.2f} "
            stdscr.addstr(1, max(0, (max_x - len(mood_line)) // 2), mood_line)

            # Neural grid rendering
            self._render_grid(stdscr, mood)

            # History sparkline
            self._render_history(stdscr, max_y - 4)

            # Footer
            stdscr.addstr(max_y - 1, 0, " [q] Quit  |  [r] Random emotion  |  [d] Decay",
                         curses.color_pair(0) | curses.A_DIM)

            stdscr.refresh()
            time.sleep(0.08)

    def _hex_to_curses_color(self, hex_color: str) -> int:
        """Map hex to nearest curses color."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

        # Map to nearest primary
        if r > 200 and g > 200 and b < 100:
            return curses.COLOR_YELLOW
        elif r > 200 and g < 100 and b < 100:
            return curses.COLOR_RED
        elif r < 100 and g < 100 and b > 200:
            return curses.COLOR_BLUE
        elif r > 150 and g < 100 and b > 150:
            return curses.COLOR_MAGENTA
        elif r < 100 and g > 200 and b < 100:
            return curses.COLOR_GREEN
        elif r > 200 and g > 100 and b < 100:
            return curses.COLOR_YELLOW
        elif r < 100 and g > 200 and b > 200:
            return curses.COLOR_CYAN
        elif r > 200 and g < 100 and b > 200:
            return curses.COLOR_MAGENTA
        else:
            return curses.COLOR_WHITE

    def _render_grid(self, stdscr, mood):
        """Render 20×20 grid with neural pulsing."""
        max_y, max_x = stdscr.getmaxyx()
        grid_size = self.grid.GRID_SIZE

        # Calculate cell size based on terminal
        available_height = max_y - 8
        available_width = max_x - 4
        cell_h = max(1, available_height // grid_size)
        cell_w = max(2, available_width // grid_size)

        # Center the grid
        start_y = max(2, (max_y - grid_size * cell_h) // 2)
        start_x = max(2, (max_x - grid_size * cell_w) // 2)

        center = grid_size // 2

        # Render each cell
        for gy in range(grid_size):
            for gx in range(grid_size):
                y = start_y + gy * cell_h
                x = start_x + gx * cell_w
                if y >= max_y - 3 or x >= max_x - 1:
                    continue

                hex_color = self.grid.get_cell(gx, gy)

                # Compute distance from center for pulse effect
                dist = math.sqrt((gx - center) ** 2 + (gy - center) ** 2)

                # Neural pulse: brightness varies with sin wave from center
                pulse = 0.7 + 0.3 * math.sin(
                    self._frame * 0.05 - dist * 0.5
                )

                # Intensity based on how non-baseline the color is
                energy = mood["energy"]
                intensity = min(1.0, energy * pulse + 0.3)

                # Choose character based on intensity
                if intensity > 0.8:
                    char = "█"
                elif intensity > 0.6:
                    char = "▓"
                elif intensity > 0.4:
                    char = "▒"
                elif intensity > 0.2:
                    char = "░"
                else:
                    char = "·"

                # Map color
                color = self._hex_to_curses_color(hex_color)
                try:
                    stdscr.addstr(y, x, char * min(cell_w, max_x - x - 1),
                                 curses.color_pair(0) | curses.A_BOLD)
                except curses.error:
                    pass

    def _render_history(self, stdscr, y):
        """Render mood history as sparkline."""
        max_y, max_x = stdscr.getmaxyx()
        if y < 2:
            return

        label = " Mood History: "
        stdscr.addstr(y, 0, label, curses.A_DIM)

        x = len(label)
        for h in self._history[-80:]:
            if x >= max_x:
                break
            color = self._hex_to_curses_color(h)
            try:
                stdscr.addstr(y, x, "▬", curses.A_BOLD)
            except curses.error:
                pass
            x += 1


def launch_visualizer():
    """Launch the neural visualizer in a new tmux window."""
    import subprocess

    # Write launcher script
    launcher = """
import sys
sys.path.insert(0, "{agent_path}")
from agent.emotions.neural_viz import main
main()
""".format(agent_path="/home/felixseven/.hermes/hermes-agent")

    script_path = "/tmp/towngu_neural.py"
    with open(script_path, "w") as f:
        f.write(launcher)

    # Create new tmux window
    subprocess.run([
        "tmux", "new-window", "-n", "mood",
        f"python3 {script_path}"
    ])


def main():
    """Entry point."""
    grid = get_mood_grid()
    viz = NeuralVisualizer(grid)

    def handler(sig, frame):
        viz.stop()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    curses.wrapper(viz.run)


if __name__ == "__main__":
    main()
