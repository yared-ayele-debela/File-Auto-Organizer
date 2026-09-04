"""
Real-time filesystem watcher for File Auto-Organizer.

Uses the watchdog library for inotify-backed filesystem events, includes
file stability checks to prevent race conditions on partially-downloaded files,
and threading locks to prevent duplicate processing.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from file_organizer.config import AppConfig, StabilityConfig
from file_organizer.logger import get_logger
from file_organizer.organizer import is_inside_destination, organize_file

logger = get_logger()


class ActiveProcessingTracker:
    """
    Thread-safe set to track file paths currently being stabilized or moved.
    Prevents duplicate concurrent processing of the same file across multiple events.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_paths: set[Path] = set()

    def acquire(self, path: Path) -> bool:
        """
        Attempt to acquire processing rights for a path.

        Returns:
            True if path was not being processed and is now registered.
            False if path is already being processed.
        """
        resolved = path.resolve()
        with self._lock:
            if resolved in self._active_paths:
                return False
            self._active_paths.add(resolved)
            return True

    def release(self, path: Path) -> None:
        """Release processing rights for a path."""
        resolved = path.resolve()
        with self._lock:
            self._active_paths.discard(resolved)

    def is_active(self, path: Path) -> bool:
        """Check whether a path is currently being processed."""
        resolved = path.resolve()
        with self._lock:
            return resolved in self._active_paths


def wait_until_file_is_stable(
    file_path: Path,
    config: StabilityConfig,
    stop_event: threading.Event | None = None,
) -> bool:
    """
    Wait until a file has completed writing and is ready to be moved.

    Guards against race conditions from browser downloads (.crdownload, .part),
    torrents, slow network writes, or multi-step saves.

    Checks:
      1. Not in ignored_extensions (e.g. .crdownload, .part).
      2. File exists and is accessible.
      3. File size is non-zero (or wait until non-zero) and remains constant
         over `min_stable_checks` intervals of `check_interval_seconds`.
      4. File can be opened in binary read mode without sharing/lock errors.

    Args:
        file_path: Path to the candidate file.
        config: Stability configuration settings.
        stop_event: Optional threading.Event to abort early on shutdown.

    Returns:
        True if file is stable and ready to organize; False if timed out, deleted, or ignored.
    """
    # 1. Ignore temporary download extensions
    lower_suffix = file_path.suffix.lower()
    for ignored_ext in config.ignored_extensions:
        if file_path.name.lower().endswith(ignored_ext):
            logger.debug(f"File has temporary extension '{lower_suffix}', skipping: {file_path.name}")
            return False

    start_time = time.time()
    consecutive_stable_checks = 0
    last_size: int | None = None

    while True:
        if stop_event and stop_event.is_set():
            return False

        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > config.max_wait_seconds:
            logger.warning(
                f"Timed out waiting for file to stabilize after {elapsed:.1f}s: {file_path.name}"
            )
            return False

        # Verify existence
        if not file_path.exists() or not file_path.is_file():
            logger.debug(f"File disappeared or is not a file during stability check: {file_path.name}")
            return False

        try:
            current_stat = file_path.stat()
            current_size = current_stat.st_size
        except OSError as e:
            logger.debug(f"Could not stat '{file_path.name}': {e}")
            consecutive_stable_checks = 0
            time.sleep(config.check_interval_seconds)
            continue

        # If file size is 0, it might just be created. Wait unless it's genuinely empty.
        if current_size == 0 and last_size is None:
            # First check with size 0, give it a moment to begin writing
            last_size = 0
            time.sleep(config.check_interval_seconds)
            continue

        if current_size == last_size:
            consecutive_stable_checks += 1
            if consecutive_stable_checks >= config.min_stable_checks:
                # Test opening file to ensure no exclusive locks or incomplete writes
                try:
                    with open(file_path, "rb") as f:
                        f.read(1)
                    return True
                except (OSError, PermissionError) as e:
                    logger.debug(f"File '{file_path.name}' size stable but locked/unreadable: {e}")
                    consecutive_stable_checks = 0
        else:
            # File is actively changing
            consecutive_stable_checks = 0
            last_size = current_size

        time.sleep(config.check_interval_seconds)


class OrganizerEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler that queues and processes filesystem modifications.
    """

    def __init__(
        self,
        config: AppConfig,
        executor: ThreadPoolExecutor,
        dry_run: bool = False,
        stop_event: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.executor = executor
        self.dry_run = dry_run
        self.stop_event = stop_event or threading.Event()
        self.tracker = ActiveProcessingTracker()

    def _should_handle_path(self, path: Path) -> bool:
        """Check if path is candidate for organization."""
        # Never handle directory events
        if path.is_dir():
            return False

        # Ignore hidden files if configured
        if self.config.ignore_hidden and path.name.startswith("."):
            return False

        # Ignore temporary download extensions
        lower_name = path.name.lower()
        for ignored_ext in self.config.stability.ignored_extensions:
            if lower_name.endswith(ignored_ext):
                return False

        # Check if already inside destination folder
        if is_inside_destination(path, self.config):
            return False

        # If non-recursive, ensure parent is exactly watch_directory
        if not self.config.recursive:
            try:
                if path.parent.resolve() != self.config.watch_directory.resolve():
                    return False
            except OSError:
                return False

        return True

    def _dispatch_process(self, file_path: Path) -> None:
        """Acquire lock and dispatch stability check + organize to worker thread pool."""
        if not self._should_handle_path(file_path):
            return

        if not self.tracker.acquire(file_path):
            # Already being processed by another worker
            return

        self.executor.submit(self._worker_process, file_path)

    def _worker_process(self, file_path: Path) -> None:
        """Worker thread entry: wait for file stability, then organize."""
        try:
            logger.debug(f"Observed candidate file: {file_path.name}. Waiting for stability...")
            is_stable = wait_until_file_is_stable(
                file_path=file_path,
                config=self.config.stability,
                stop_event=self.stop_event,
            )

            if not is_stable:
                logger.debug(f"File did not stabilize or was discarded: {file_path.name}")
                return

            # File is stable, execute organization
            organize_file(
                source_path=file_path,
                config=self.config,
                dry_run=self.dry_run,
            )
        except Exception as e:
            logger.exception(f"Unexpected error processing '{file_path}': {e}")
        finally:
            self.tracker.release(file_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, (DirCreatedEvent, DirModifiedEvent)):
            return
        if event.is_directory:
            return
        dest = Path(event.src_path)
        self._dispatch_process(dest)

    def on_modified(self, event: FileSystemEvent) -> None:
        if isinstance(event, (DirCreatedEvent, DirModifiedEvent)):
            return
        if event.is_directory:
            return
        dest = Path(event.src_path)
        self._dispatch_process(dest)

    def on_moved(self, event: FileSystemEvent) -> None:
        if isinstance(event, DirMovedEvent):
            return
        if event.is_directory:
            return
        # In move/rename events (e.g. .crdownload -> .pdf), dest_path is the new file
        dest = Path(event.dest_path)
        self._dispatch_process(dest)


class DirectoryWatcher:
    """
    Manages the watchdog observer thread and thread pool executor.
    """

    def __init__(
        self,
        config: AppConfig,
        dry_run: bool = False,
        max_workers: int = 4,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="OrganizerWorker"
        )
        self.event_handler = OrganizerEventHandler(
            config=self.config,
            executor=self.executor,
            dry_run=self.dry_run,
            stop_event=self.stop_event,
        )
        self.observer = Observer()

    def start(self) -> None:
        """Start the watchdog observer."""
        watch_dir = self.config.watch_directory
        if not watch_dir.exists():
            watch_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created watch directory: {watch_dir}")

        self.observer.schedule(
            event_handler=self.event_handler,
            path=str(watch_dir),
            recursive=self.config.recursive,
        )
        self.observer.start()
        mode_str = " [DRY-RUN MODE]" if self.dry_run else ""
        logger.info(
            f"Started watching directory: '{watch_dir}' (recursive={self.config.recursive}){mode_str}"
        )

    def stop(self) -> None:
        """Stop the watcher and shutdown worker threads cleanly."""
        logger.info("Stopping directory watcher...")
        self.stop_event.set()
        self.observer.stop()
        self.observer.join(timeout=5.0)
        self.executor.shutdown(wait=True, cancel_futures=False)
        logger.info("Directory watcher stopped cleanly.")

    def update_config(self, new_config: AppConfig) -> None:
        """Dynamically update configuration rules without restarting observer."""
        self.config = new_config
        self.event_handler.config = new_config
        logger.info("Watcher configuration reloaded successfully.")
