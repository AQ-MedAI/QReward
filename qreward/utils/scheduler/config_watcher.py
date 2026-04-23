"""Configuration watcher for hot-reloading schedule parameters at runtime."""

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_ENV_PREFIX = "QREWARD_SCHEDULE_"
_UPDATABLE_FIELDS = frozenset({
    "timeout", "retry_times", "retry_interval", "limit_size", "limit_window",
    "hedged_request_time", "hedged_request_proportion",
    "hedged_request_max_times", "speed_up_max_multiply", "debug",
    "adaptive_limit", "adaptive_limit_min", "adaptive_limit_max",
    "adaptive_error_threshold", "adaptive_latency_threshold",
    "adaptive_window_seconds", "priority",
})


class ConfigWatcher:
    """Watches a configuration source and hot-reloads ScheduleConfig changes.

    Supports three source modes:
    - **file**: Watches a JSON file for changes (polls by mtime).
    - **env**: Reads environment variables with ``QREWARD_SCHEDULE_`` prefix.
    - **callback**: Invokes a user-supplied callable that returns a dict.

    Example:
        >>> watcher = ConfigWatcher(
        ...     config, source="file", file_path="config.json"
        ... )
        >>> watcher.start()
        >>> # ... later ...
        >>> watcher.stop()
    """

    def __init__(
        self,
        config: Any,
        source: str = "callback",
        file_path: Optional[str] = None,
        callback: Optional[Callable[[], dict[str, Any]]] = None,
        poll_interval: float = 5.0,
        cooldown: float = 5.0,
    ) -> None:
        """Initialize the config watcher.

        Args:
            config: The ScheduleConfig instance to update.
            source: Source mode - "file", "env", or "callback".
            file_path: Path to JSON config file (required for "file" mode).
            callback: Callable returning config dict (required for
                "callback" mode).
            poll_interval: Seconds between polls.
            cooldown: Minimum seconds between successive updates.
        """
        if source not in ("file", "env", "callback"):
            raise ValueError(
                f"source must be 'file', 'env', or 'callback', got {source!r}"
            )
        if source == "file" and not file_path:
            raise ValueError("file_path is required for 'file' source")
        if source == "callback" and callback is None:
            raise ValueError("callback is required for 'callback' source")

        self._config = config
        self._source = source
        self._file_path = file_path
        self._callback = callback
        self._poll_interval = poll_interval
        self._cooldown = cooldown
        self._last_update_time: float = -float("inf")
        self._last_mtime: float = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the watcher daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.debug("ConfigWatcher started (source=%s)", self._source)

    def stop(self) -> None:
        """Stop the watcher thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)
            self._thread = None
        logger.debug("ConfigWatcher stopped")

    @property
    def is_running(self) -> bool:
        """Check if the watcher thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def poll_once(self) -> bool:
        """Perform a single poll and update if changed.

        Returns:
            True if config was updated, False otherwise.
        """
        now = time.monotonic()
        if now - self._last_update_time < self._cooldown:
            return False

        new_values = self._read_source()
        if not new_values:
            return False

        filtered = {
            k: v
            for k, v in new_values.items()
            if k in _UPDATABLE_FIELDS
        }
        if not filtered:
            return False

        self._config.update(**filtered)
        self._last_update_time = now
        logger.debug("Config updated: %s", filtered)
        return True

    def _poll_loop(self) -> None:
        """Background polling loop."""
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                logger.warning("ConfigWatcher poll error: %s", exc)
            self._stop_event.wait(self._poll_interval)

    def _read_source(self) -> Optional[dict[str, Any]]:
        """Read configuration from the configured source."""
        if self._source == "file":
            return self._read_file()
        elif self._source == "env":
            return self._read_env()
        elif self._source == "callback":
            return self._read_callback()
        return None

    def _read_file(self) -> Optional[dict[str, Any]]:
        """Read config from a JSON file, only if mtime changed."""
        if not self._file_path or not os.path.isfile(self._file_path):
            return None
        mtime = os.path.getmtime(self._file_path)
        if mtime == self._last_mtime:
            return None
        self._last_mtime = mtime
        with open(self._file_path, "r") as fh:
            return json.load(fh)

    def _read_env(self) -> Optional[dict[str, Any]]:
        """Read config from environment variables with QREWARD_SCHEDULE_
        prefix."""
        result: dict[str, Any] = {}
        for key, value in os.environ.items():
            if not key.startswith(_ENV_PREFIX):
                continue
            field_name = key[len(_ENV_PREFIX):].lower()
            if field_name not in _UPDATABLE_FIELDS:
                continue
            result[field_name] = _coerce_value(field_name, value)
        return result or None

    def _read_callback(self) -> Optional[dict[str, Any]]:
        """Read config from user callback."""
        if self._callback is None:
            return None
        return self._callback()


def _coerce_value(field_name: str, raw: str) -> Any:
    """Coerce a string environment variable value to the correct type."""
    bool_fields = {"debug", "adaptive_limit"}
    int_fields = {
        "retry_times", "limit_size", "hedged_request_max_times",
        "speed_up_max_multiply", "adaptive_limit_min",
        "adaptive_limit_max", "priority",
    }
    float_fields = {
        "timeout", "retry_interval", "limit_window",
        "hedged_request_time", "hedged_request_proportion",
        "adaptive_error_threshold", "adaptive_latency_threshold",
        "adaptive_window_seconds",
    }
    if field_name in bool_fields:
        return raw.lower() in ("true", "1", "yes", "on")
    if field_name in int_fields:
        return int(raw)
    if field_name in float_fields:
        return float(raw)
    return raw
