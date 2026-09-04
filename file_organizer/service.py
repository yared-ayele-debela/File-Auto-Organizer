"""
Systemd user service integration and diagnostic status utilities.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from file_organizer.config import AppConfig

SERVICE_NAME = "file-organizer.service"
USER_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_UNIT_PATH = USER_SYSTEMD_DIR / SERVICE_NAME


def run_systemctl_user(*args: str) -> tuple[int, str]:
    """Execute a systemctl --user command and return (exit_code, stdout/stderr)."""
    if not shutil.which("systemctl"):
        return -1, "systemctl command not found on this system."

    cmd = ["systemctl", "--user", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = proc.stdout.strip() or proc.stderr.strip()
        return proc.returncode, output
    except OSError as e:
        return -1, f"Failed to run systemctl: {e}"


def get_service_status() -> dict[str, str | bool]:
    """
    Query systemd user manager for the service status.

    Returns:
        dict containing 'installed', 'active', 'enabled', 'status_text', 'unit_path'.
    """
    installed = SYSTEMD_UNIT_PATH.is_file()

    code_active, active_str = run_systemctl_user("is-active", SERVICE_NAME)
    is_active = (code_active == 0 and active_str == "active")

    code_enabled, enabled_str = run_systemctl_user("is-enabled", SERVICE_NAME)
    is_enabled = (code_enabled == 0 and enabled_str == "enabled")

    _, full_status = run_systemctl_user("status", SERVICE_NAME, "--no-pager")

    return {
        "installed": installed,
        "active": is_active,
        "active_state": active_str if code_active in {0, 3} else "unknown",
        "enabled": is_enabled,
        "enabled_state": enabled_str if code_enabled in {0, 1} else "unknown",
        "unit_path": str(SYSTEMD_UNIT_PATH),
        "status_text": full_status,
    }


def reload_or_restart_service() -> tuple[bool, str]:
    """Reload daemon and restart the user service."""
    c1, out1 = run_systemctl_user("daemon-reload")
    if c1 != 0:
        return False, f"Failed to reload systemd user daemon: {out1}"

    c2, out2 = run_systemctl_user("restart", SERVICE_NAME)
    if c2 != 0:
        return False, f"Failed to restart {SERVICE_NAME}: {out2}"

    return True, f"Successfully reloaded and restarted {SERVICE_NAME}."


def get_recent_logs(lines: int = 15) -> str:
    """Retrieve recent journalctl logs for the user service."""
    if not shutil.which("journalctl"):
        return "journalctl not available."
    cmd = ["journalctl", "--user", "-u", SERVICE_NAME, f"-n{lines}", "--no-pager"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.stdout.strip() or "(No logs found)"
    except OSError as e:
        return f"Error reading logs: {e}"


RED_BOLD = "\033[1;91m"
YELLOW_BOLD = "\033[1;93m"
RESET = "\033[0m"

ASCII_ART = r"""
 ______ _ _       ____                        _              
|  ____(_) |     / __ \                      (_)             
| |__   _| | ___| |  | |_ __ __ _  __ _ _ __  _ _______ _ __ 
|  __| | | |/ _ \ |  | | '__/ _` |/ _` | '_ \| |_  / _ \ '__|
| |    | | |  __/ |__| | | | (_| | (_| | | | | |/ /  __/ |   
|_|    |_|_|\___|\____/|_|  \__, |\__,_|_| |_|_/___\___|_|   
                             __/ |                           
                            |___/                            """

STATUS_BANNER = f"{RED_BOLD}{ASCII_ART}{RESET}\n            {YELLOW_BOLD}[ FILE AUTO-ORGANIZER STATUS ]{RESET}\n"


def display_status(config: AppConfig) -> None:
    """Print an end-user readable status overview."""
    info = get_service_status()
    active_badge = "\033[32m● ACTIVE\033[0m" if info["active"] else "\033[31m○ INACTIVE\033[0m"
    enabled_badge = "\033[32mENABLED\033[0m" if info["enabled"] else "\033[33mDISABLED\033[0m"

    print(STATUS_BANNER)
    print(f"Service Unit:     {SERVICE_NAME} ({active_badge} / {enabled_badge})")
    print(f"Unit File:        {info['unit_path']} (Exists: {info['installed']})")
    print(f"Config Source:    {config.config_source or 'Default built-in'}")
    print(f"Watch Directory:  {config.watch_directory} (Exists: {config.watch_directory.exists()})")
    print(f"Conflict Mode:    {config.conflict_resolution}")
    print(f"Log File:         {config.logging.file}")
    print(f"Categories ({len(config.categories)}):")
    for name, cat in config.categories.items():
        exts = ", ".join(cat.extensions[:6])
        if len(cat.extensions) > 6:
            exts += f", ... (+{len(cat.extensions)-6} more)"
        print(f"  • {name:<14} -> {cat.folder.name}/ [{exts}]")

    print("\n--- Recent Systemd Journal Logs ---")
    print(get_recent_logs(lines=8))
    print("=" * 60 + "\n")
