"""Configuration Hot Reload Example

Demonstrates how to dynamically update schedule configuration at runtime
without restarting the application. Supports three configuration sources:
  - callback: A user-supplied function returning a config dict
  - env:      Environment variables with QREWARD_SCHEDULE_ prefix
  - file:     A JSON file watched for mtime changes

Key classes:
  ScheduleConfig  → Holds all schedule parameters, supports update() and on_change()
  ConfigWatcher   → Background thread that polls a source and applies changes
"""

import json
import os
import tempfile
import time

from qreward.utils.scheduler import ConfigWatcher, ScheduleConfig


# --- Example 1: Programmatic config update ---
def demo_programmatic_update():
    print("=== Programmatic Config Update ===\n")
    config = ScheduleConfig(timeout=10, retry_times=3)
    print(f"  Initial: timeout={config.timeout}, retry_times={config.retry_times}")

    # Register a change listener
    config.on_change(
        lambda cfg: print(f"  [onChange] timeout={cfg.timeout}, retry_times={cfg.retry_times}")
    )

    # Update config at runtime
    config.update(timeout=30, retry_times=5)
    print(f"  Updated: timeout={config.timeout}, retry_times={config.retry_times}")

    # Take a snapshot
    snap = config.snapshot()
    print(f"  Snapshot keys: {list(snap.keys())[:5]}...\n")


# --- Example 2: ConfigWatcher with callback source ---
def demo_callback_watcher():
    print("=== ConfigWatcher - Callback Source ===\n")
    config = ScheduleConfig(timeout=10)
    call_count = 0

    def dynamic_config():
        nonlocal call_count
        call_count += 1
        # Simulate config changes over time
        if call_count >= 3:
            return {"timeout": 60, "retry_times": 10}
        return {"timeout": 10 + call_count * 5}

    watcher = ConfigWatcher(
        config, source="callback", callback=dynamic_config,
        poll_interval=0.5, cooldown=0,
    )

    print(f"  Before: timeout={config.timeout}")
    watcher.start()
    time.sleep(2)  # Let the watcher poll a few times
    watcher.stop()
    print(f"  After:  timeout={config.timeout}, retry_times={config.retry_times}\n")


# --- Example 3: ConfigWatcher with file source ---
def demo_file_watcher():
    print("=== ConfigWatcher - File Source ===\n")
    config = ScheduleConfig(timeout=10, retry_times=3)

    # Create a temporary config file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp_file:
        json.dump({"timeout": 45, "limit_size": 200}, tmp_file)
        tmp_path = tmp_file.name

    try:
        watcher = ConfigWatcher(
            config, source="file", file_path=tmp_path,
            poll_interval=0.5, cooldown=0,
        )

        print(f"  Before: timeout={config.timeout}, limit_size={config.limit_size}")
        watcher.poll_once()
        print(f"  After:  timeout={config.timeout}, limit_size={config.limit_size}")

        # Modify the file
        time.sleep(0.1)  # Ensure mtime changes
        with open(tmp_path, "w") as fh:
            json.dump({"timeout": 90, "limit_size": 500}, fh)

        watcher.poll_once()
        print(f"  Updated: timeout={config.timeout}, limit_size={config.limit_size}\n")
    finally:
        os.unlink(tmp_path)


# --- Example 4: ConfigWatcher with environment variables ---
def demo_env_watcher():
    print("=== ConfigWatcher - Environment Variables ===\n")
    config = ScheduleConfig(timeout=10)

    # Set environment variables
    os.environ["QREWARD_SCHEDULE_TIMEOUT"] = "120"
    os.environ["QREWARD_SCHEDULE_RETRY_TIMES"] = "8"

    try:
        watcher = ConfigWatcher(config, source="env", cooldown=0)
        print(f"  Before: timeout={config.timeout}, retry_times={config.retry_times}")
        watcher.poll_once()
        print(f"  After:  timeout={config.timeout}, retry_times={config.retry_times}\n")
    finally:
        del os.environ["QREWARD_SCHEDULE_TIMEOUT"]
        del os.environ["QREWARD_SCHEDULE_RETRY_TIMES"]


if __name__ == "__main__":
    demo_programmatic_update()
    demo_callback_watcher()
    demo_file_watcher()
    demo_env_watcher()
