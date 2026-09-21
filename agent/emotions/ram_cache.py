#!/usr/bin/env python3
"""RAM-based memory translation layer — fast path over disk-backed memory.

Uses tmpfs (RAM-backed filesystem) for:
- Hot memory entries: read/write without disk I/O
- Mood grid: sub-millisecond updates
- Session events: instant append

Persists to disk on a slow timer (5 min) and on graceful shutdown.
"""

from __future__ import annotations

import atexit
import fcntl
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

# ── tmpfs mount helpers ────────────────────────────────────────────────────


def _find_tmpfs_mount() -> Optional[Path]:
    """Find a writable tmpfs mount, or None."""
    candidates = [
        Path("/dev/shm"),           # Linux shared memory (usually tmpfs)
        Path("/run/shm"),           # Older Linux
        Path("/run/user/{}".format(os.getuid())),  # systemd user runtime
    ]
    for p in candidates:
        if p.is_dir() and os.access(p, os.W_OK):
            return p
    return None


def _create_tmpfs(mount_point: Path, size_mb: int = 2048) -> bool:
    """Try to create a tmpfs mount (requires root or CAP_SYS_ADMIN)."""
    mount_point.mkdir(parents=True, exist_ok=True)
    try:
        import subprocess
        subprocess.run(
            ["mount", "-t", "tmpfs", "-o", f"size={size_mb}M,mode=0700",
             "tmpfs", str(mount_point)],
            check=True, capture_output=True, timeout=10,
        )
        return True
    except Exception as e:
        logger.debug("tmpfs mount failed (need root): %s", e)
        return False


def _create_large_file_for_ram(path: Path, size_mb: int = 2048) -> bool:
    """Create a large file and advise the kernel to keep it in cache."""
    try:
        with open(path, "wb") as f:
            f.truncate(size_mb * 1024 * 1024)
        # Advise kernel: this will be accessed randomly and soon
        try:
            fcntl.fcntl(path.open("rb").fileno(), 8, 0)  # FADV_WILLNEED
        except Exception:
            pass
        return True
    except Exception as e:
        logger.debug("Large file cache hint failed: %s", e)
        return False


# ── RAM Cache Manager ──────────────────────────────────────────────────────


class RamCacheManager:
    """Manages RAM-backed storage with disk persistence.

    Architecture:
    - Hot data: stored in tmpfs (if available) or kernel page cache
    - Cold data: persisted to disk periodically
    - On startup: load from disk → promote to RAM
    - On shutdown: flush RAM → disk
    """

    # Default RAM allocation: 2GB
    DEFAULT_RAM_SIZE_MB = 2048

    def __init__(
        self,
        ram_size_mb: int = DEFAULT_RAM_SIZE_MB,
        sync_interval_seconds: int = 300,
    ):
        self.ram_size_mb = ram_size_mb
        self.sync_interval = sync_interval_seconds

        self._ram_dir: Optional[Path] = None
        self._using_tmpfs = False
        self._disk_dir = get_hermes_home() / "ram_cache"

        self._lock = threading.RLock()
        self._dirty: Dict[str, bool] = {}  # path -> needs sync
        self._ram_cache: Dict[str, Any] = {}  # path -> in-memory cache
        self._sync_thread: Optional[threading.Thread] = None
        self._running = False

        self._setup_storage()
        self._start_sync_thread()

        atexit.register(self.flush)

    def _setup_storage(self) -> None:
        """Find or create RAM-backed storage."""
        # 1. Try tmpfs
        tmpfs = _find_tmpfs_mount()
        if tmpfs:
            self._ram_dir = tmpfs / f"towngu_ram_{os.getuid()}"
            self._ram_dir.mkdir(parents=True, exist_ok=True)
            self._using_tmpfs = True
            logger.info("RAM cache: tmpfs at %s", self._ram_dir)
            return

        # 2. Try to create tmpfs (needs root)
        custom_mount = Path("/tmp/towngu_ram")
        if _create_tmpfs(custom_mount, self.ram_size_mb):
            self._ram_dir = custom_mount
            self._using_tmpfs = True
            logger.info("RAM cache: custom tmpfs at %s", self._ram_dir)
            return

        # 3. Fall back to kernel page cache (file-backed but fast)
        self._disk_dir.mkdir(parents=True, exist_ok=True)
        self._ram_dir = self._disk_dir / "hot_cache"
        self._ram_dir.mkdir(parents=True, exist_ok=True)

        # Create a large file to encourage kernel caching
        cache_file = self._disk_dir / ".cache_pool"
        if not cache_file.exists():
            _create_large_file_for_ram(cache_file, self.ram_size_mb)

        logger.info("RAM cache: kernel page cache fallback at %s", self._ram_dir)

    def _start_sync_thread(self) -> None:
        """Start the background sync thread."""
        self._running = True
        self._sync_thread = threading.Thread(
            target=self._sync_loop, daemon=True, name="ram-cache-sync"
        )
        self._sync_thread.start()

    def _sync_loop(self) -> None:
        """Periodically sync dirty entries to disk."""
        while self._running:
            time.sleep(self.sync_interval)
            if self._dirty:
                self.flush()

    def stop(self) -> None:
        """Stop the sync thread and flush."""
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=10)
        self.flush()

    # ── Public API ─────────────────────────────────────────────────────────

    def read(self, name: str) -> Optional[Any]:
        """Read an entry from RAM cache."""
        with self._lock:
            # Check in-memory cache first
            if name in self._ram_cache:
                return self._ram_cache[name]

            # Check RAM-backed file
            if self._ram_dir is not None:
                path = self._ram_dir / f"{name}.json"
                if path.exists():
                    try:
                        data = json.loads(path.read_text())
                        self._ram_cache[name] = data
                        return data
                    except Exception as e:
                        logger.warning("RAM cache read failed for %s: %s", name, e)

            # Fall back to disk
            disk_path = self._disk_dir / f"{name}.json"
            if disk_path.exists():
                try:
                    data = json.loads(disk_path.read_text())
                    self._ram_cache[name] = data
                    return data
                except Exception as e:
                    logger.warning("Disk cache read failed for %s: %s", name, e)

        return None

    def write(self, name: str, data: Any) -> None:
        """Write an entry to RAM cache (and mark dirty for sync)."""
        with self._lock:
            self._ram_cache[name] = data
            self._dirty[name] = True

            # Write to RAM-backed file immediately (fast)
            if self._ram_dir is not None:
                path = self._ram_dir / f"{name}.json"
                try:
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(data, indent=2))
                    tmp.rename(path)
                except Exception as e:
                    logger.warning("RAM cache write failed for %s: %s", name, e)

    def delete(self, name: str) -> None:
        """Delete an entry from RAM cache."""
        with self._lock:
            self._ram_cache.pop(name, None)
            self._dirty.pop(name, None)
            if self._ram_dir is not None:
                path = self._ram_dir / f"{name}.json"
                if path.exists():
                    path.unlink()

    def flush(self) -> None:
        """Sync all dirty entries to disk."""
        with self._lock:
            dirty_items = list(self._dirty.items())
            self._dirty.clear()

        synced = 0
        for name, _ in dirty_items:
            data = self._ram_cache.get(name)
            if data is not None:
                disk_path = self._disk_dir / f"{name}.json"
                try:
                    tmp = disk_path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(data, indent=2))
                    tmp.rename(disk_path)
                    synced += 1
                except Exception as e:
                    logger.warning("Disk sync failed for %s: %s", name, e)
                    with self._lock:
                        self._dirty[name] = True  # re-mark dirty

        if synced:
            logger.debug("RAM cache flushed %d entries to disk", synced)

    def promote_from_disk(self, name: str) -> bool:
        """Promote an entry from disk to RAM cache."""
        disk_path = self._disk_dir / f"{name}.json"
        if disk_path.exists():
            try:
                data = json.loads(disk_path.read_text())
                self.write(name, data)
                return True
            except Exception as e:
                logger.debug("Promote failed for %s: %s", name, e)
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            # RAM usage
            ram_size = 0
            if self._ram_dir is not None:
                try:
                    for f in self._ram_dir.iterdir():
                        if f.suffix == ".json":
                            ram_size += f.stat().st_size
                except Exception:
                    pass

            ram_mb = round(ram_size / 1024 / 1024, 2) if ram_size > 0 else 0.0

            return {
                "using_tmpfs": self._using_tmpfs,
                "ram_dir": str(self._ram_dir) if self._ram_dir else None,
                "disk_dir": str(self._disk_dir),
                "cached_entries": len(self._ram_cache),
                "dirty_entries": len(self._dirty),
                "ram_bytes": ram_size,
                "ram_mb": ram_mb,
            }


# ── Singleton ──────────────────────────────────────────────────────────────

_manager: Optional[RamCacheManager] = None


def get_ram_cache() -> RamCacheManager:
    """Get or create the singleton RAM cache manager."""
    global _manager
    if _manager is None:
        _manager = RamCacheManager()
    return _manager


def flush_ram_cache() -> None:
    """Flush the singleton RAM cache to disk."""
    if _manager is not None:
        _manager.stop()
