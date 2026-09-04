"""
CLI entry point for File Auto-Organizer.

Provides commands to watch directories, scan existing files, inspect status,
validate configuration, and control background services.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from typing import Sequence

from file_organizer import __version__
from file_organizer.config import (
    AppConfig,
    create_default_user_config,
    find_config_file,
    load_config,
    resolve_path,
)
from file_organizer.logger import get_logger, setup_logger
from file_organizer.organizer import organize_directory
from file_organizer.service import display_status, reload_or_restart_service
from file_organizer.watcher import DirectoryWatcher


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="file-organizer",
        description="Professional-grade real-time file auto-organizer for Ubuntu Linux.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-c", "--config",
        dest="config_path",
        type=str,
        default=None,
        help="Path to YAML or JSON configuration file.",
    )
    parser.add_argument(
        "-d", "--dir",
        dest="watch_dir",
        type=str,
        default=None,
        help="Target directory to watch or scan (overrides config watch_directory).",
    )
    parser.add_argument(
        "-n", "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Simulate actions without moving files or creating folders.",
    )
    parser.add_argument(
        "-v", "--verbose",
        dest="verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Operational commands")

    # Command: watch
    watch_parser = subparsers.add_parser(
        "watch",
        help="Start watching directory in real-time (runs in foreground or under systemd).",
    )
    watch_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of background worker threads for file stabilization and moves (default: 4).",
    )

    # Command: scan / organize
    scan_parser = subparsers.add_parser(
        "scan",
        aliases=["organize"],
        help="Scan and organize all existing files currently in the target directory once.",
    )

    # Command: status
    subparsers.add_parser(
        "status",
        help="Display service status, active configuration, and recent logs.",
    )

    # Command: reload
    subparsers.add_parser(
        "reload",
        help="Reload systemd user service and re-read configuration.",
    )

    # Command: config
    config_parser = subparsers.add_parser(
        "config",
        help="Inspect or initialize configuration files.",
    )
    config_parser.add_argument(
        "--init",
        action="store_true",
        help="Generate default configuration file at ~/.config/file-organizer/config.yaml.",
    )
    config_parser.add_argument(
        "--path",
        action="store_true",
        help="Print path of the active configuration file.",
    )
    config_parser.add_argument(
        "--dump",
        action="store_true",
        help="Display active configuration values.",
    )

    return parser


def apply_cli_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    """Apply command line overrides (directory, dry-run, etc.) to config."""
    if getattr(args, "watch_dir", None):
        config.set_watch_directory(args.watch_dir)
    return config


def cmd_watch(config: AppConfig, args: argparse.Namespace) -> int:
    """Execute real-time watcher daemon loop."""
    logger = get_logger()
    workers = getattr(args, "workers", 4)

    watcher = DirectoryWatcher(
        config=config,
        dry_run=args.dry_run,
        max_workers=workers,
    )

    # Graceful shutdown handler
    def handle_shutdown(signum: int, frame: object) -> None:
        signame = signal.Signals(signum).name
        logger.info(f"Received {signame}. Initiating graceful shutdown...")
        watcher.stop()
        sys.exit(0)

    # SIGHUP handler for dynamic configuration reload
    def handle_sighup(signum: int, frame: object) -> None:
        logger.info("Received SIGHUP. Reloading configuration from disk...")
        try:
            new_config = load_config(args.config_path)
            new_config = apply_cli_overrides(new_config, args)
            watcher.update_config(new_config)
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_sighup)

    watcher.start()

    # Keep main thread alive while background observer runs
    try:
        while True:
            time.sleep(1.0)
    except (KeyboardInterrupt, SystemExit):
        watcher.stop()

    return 0


def cmd_scan(config: AppConfig, args: argparse.Namespace) -> int:
    """Execute one-time batch scan and organize."""
    moved, skipped = organize_directory(
        watch_dir=config.watch_directory,
        config=config,
        dry_run=args.dry_run,
    )
    return 0 if moved >= 0 else 1


def cmd_status(config: AppConfig) -> int:
    """Display diagnostic status."""
    display_status(config)
    return 0


def cmd_reload() -> int:
    """Restart systemd service."""
    success, message = reload_or_restart_service()
    if success:
        print(f"\033[32m✔ {message}\033[0m")
        return 0
    else:
        print(f"\033[31m✘ {message}\033[0m", file=sys.stderr)
        return 1


def cmd_config(config: AppConfig, args: argparse.Namespace) -> int:
    """Handle config subcommand actions."""
    if args.init:
        created = create_default_user_config(force=True)
        print(f"\033[32m✔ Default configuration initialized at: {created}\033[0m")
        return 0

    if args.path:
        active_path = config.config_source or find_config_file()
        if active_path:
            print(str(active_path))
        else:
            print("(Using built-in default configuration; no custom file found)")
        return 0

    if args.dump:
        print(f"Config Source: {config.config_source}")
        print(f"Watch Directory: {config.watch_directory}")
        print(f"Recursive: {config.recursive}")
        print(f"Conflict Resolution: {config.conflict_resolution}")
        print(f"Ignore Hidden: {config.ignore_hidden}")
        print(f"Unmatched Category: {config.unmatched_category}")
        print(f"Stability: interval={config.stability.check_interval_seconds}s, "
              f"min_checks={config.stability.min_stable_checks}, "
              f"max_wait={config.stability.max_wait_seconds}s")
        print(f"Logging File: {config.logging.file}")
        print(f"Categories ({len(config.categories)}):")
        for name, cat in config.categories.items():
            print(f"  [{name}] -> {cat.folder}")
            print(f"    extensions: {', '.join(cat.extensions)}")
        return 0

    # Default action if no flags provided: show config file path and help
    active_path = config.config_source or find_config_file()
    print(f"Active config file: {active_path or 'Built-in default'}")
    print("Use --dump to view all rules or --init to generate ~/.config/file-organizer/config.yaml")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load configuration
    try:
        config = load_config(args.config_path)
    except Exception as e:
        sys.stderr.write(f"Error loading configuration: {e}\n")
        return 1

    config = apply_cli_overrides(config, args)

    # Initialize logger
    setup_logger(
        log_file=config.logging.file,
        level=config.logging.level,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
        verbose=args.verbose,
    )

    # Route subcommands
    command = args.command or "watch"

    if command == "watch":
        return cmd_watch(config, args)
    elif command in {"scan", "organize"}:
        return cmd_scan(config, args)
    elif command == "status":
        return cmd_status(config)
    elif command == "reload":
        return cmd_reload()
    elif command == "config":
        return cmd_config(config, args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
