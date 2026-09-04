# File Auto-Organizer for Ubuntu Linux

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![systemd](https://img.shields.io/badge/systemd-user%20service-brightgreen.svg)](https://systemd.io/)
[![Watchdog](https://img.shields.io/badge/filesystem-watchdog-orange.svg)](https://github.com/gorakhargosh/watchdog)

An advanced, production-grade automated file organizer for Ubuntu Linux. It continuously monitors a target directory (such as `~/Downloads`) in real time using native `inotify` kernel events (via `watchdog`), protects against race conditions on partially-downloaded files, automatically creates destination subfolders, safely resolves filename collisions, logs all actions to a rotating audit file, and runs persistently in the background as a `systemd` user service.

---

## Key Features

- **Real-Time inotify Monitoring**: Powered by the Python `watchdog` library for event-driven filesystem tracking without polling overhead.
- **Race Condition & Partial Download Protection**:
  - Automatically suppresses events on temporary/incomplete files (`.crdownload`, `.part`, `.tmp`, `.temp`, `.download`, `.aria2`, `.partial`, `.lock`).
  - Verifies file stability before moving: polls file size across configurable intervals to ensure writes have completed and tests file openability.
  - Utilizes thread-safe synchronization (`threading.Lock` active registry) to avoid duplicate concurrent processing across rapid create/modify events.
- **Configurable Extension Mapping (YAML / JSON)**:
  - Default categories: **PDFs**, **Documents**, **Spreadsheets**, **Presentations**, **Images**, **Videos**, **Audio**, **Archives**, **Installers**, and **Code**.
  - Greedy compound extension resolution (e.g. `.tar.gz`, `.tar.bz2`, `.tar.xz` matched before `.gz`).
  - Custom destination folders (relative subfolders or absolute external paths).
  - Configurable fallback for unmatched extensions (`leave` in place or move to a custom folder like `Other`).
- **Safe Path & Collision Handling**:
  - Auto-creates destination directories (`pathlib.Path.mkdir(parents=True, exist_ok=True)`).
  - Cyclic move prevention: ignores files that already reside inside destination category directories.
  - Conflict resolution strategies:
    - `numeric`: appends incrementing counters, e.g. `report (1).pdf` or `archive (1).tar.gz`.
    - `timestamp`: appends formatted timestamps, e.g. `report_20260904_120000.pdf`.
    - `skip`: keeps existing files untouched and logs warnings.
- **Audit Logging & Dry-Run Mode**:
  - Persistent rotating log file (`RotatingFileHandler`) with customizable maximum byte size and retention counts.
  - Colored interactive console output when run directly in a terminal.
  - `--dry-run` flag to simulate and preview actions without modifying files or directories.
- **Native systemd Integration**:
  - Packaged as a standard `systemd` user service (`~/.config/systemd/user/file-organizer.service`).
  - Automatically restarts on system reboot or unexpected failure.
  - Live configuration reload via `SIGHUP` (`file-organizer reload` or `systemctl --user reload file-organizer`).
- **One-Command Installation & Management**:
  - Includes `install.sh` and `uninstall.sh`.
  - Self-contained Python virtual environment at `~/.local/share/file-organizer/venv`.
  - CLI binary symlinked to `~/.local/bin/file-organizer`.

---

## Directory Structure

```text
Tools/
├── file_organizer/              # Python application package
│   ├── __init__.py              # Package version and metadata
│   ├── __main__.py              # python3 -m file_organizer entry point
│   ├── cli.py                   # Argument parsing and CLI subcommands
│   ├── config.py                # Dataclasses, YAML/JSON loader, validation
│   ├── logger.py                # Console formatter & RotatingFileHandler
│   ├── organizer.py             # Categorization, collisions, atomic moves
│   ├── service.py               # systemd status and journalctl inspection
│   └── watcher.py               # Watchdog observer, stability checker, locks
├── config/
│   └── default_config.yaml      # Master configuration template
├── systemd/
│   └── file-organizer.service   # systemd user unit definition
├── tests/                       # Unit tests (pytest)
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_organizer.py
│   └── test_watcher.py
├── install.sh                   # Automated installation script
├── uninstall.sh                 # Uninstallation and purge script
├── pyproject.toml               # Modern packaging metadata
├── requirements.txt             # Direct dependencies
└── README.md                    # Documentation
```

---

## Installation

### Prerequisites (Ubuntu Linux)
Ensure Python 3, `python3-venv`, and `python3-pip` are installed:
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

### Automated Install
Run `install.sh` from the repository:
```bash
./install.sh
```

The script will:
1. Create a dedicated virtual environment at `~/.local/share/file-organizer/venv`.
2. Install dependencies (`watchdog`, `PyYAML`, `pytest`).
3. Install default configuration to `~/.config/file-organizer/config.yaml` (without overwriting existing configurations).
4. Symlink the CLI executable to `~/.local/bin/file-organizer`.
5. Install, enable, and start the systemd user service `file-organizer.service`.

> [!NOTE]
> If `~/.local/bin` is not yet in your `$PATH`, add it to your `~/.bashrc` or `~/.zshrc`:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```

---

## Usage

### CLI Commands

```bash
# Check service status, active configuration, and recent logs
file-organizer status

# Perform a one-time scan and organize all files in ~/Downloads
file-organizer scan

# Dry-run simulation (see what would be moved without modifying files)
file-organizer scan --dry-run

# Run watcher directly in the foreground (useful for debugging)
file-organizer watch -v

# Organize a custom folder
file-organizer -d /path/to/my/folder scan

# Inspect active configuration
file-organizer config --dump

# Reload configuration on the running background service
file-organizer reload
```

---

## Configuration

The configuration file is located at:
```bash
~/.config/file-organizer/config.yaml
```

### Example Configuration

```yaml
# Directory to monitor (default: ~/Downloads)
watch_directory: "~/Downloads"

# Non-recursive monitoring to avoid processing files in destination subfolders
recursive: false

# Collision handling: numeric, timestamp, or skip
conflict_resolution: "numeric"

# Partial download & stability guards
stability:
  check_interval_seconds: 1.0
  min_stable_checks: 2
  max_wait_seconds: 30.0
  ignored_extensions:
    - ".crdownload"
    - ".part"
    - ".tmp"
    - ".temp"
    - ".download"
    - ".aria2"
    - ".partial"
    - ".lock"

# Ignore hidden files starting with a dot
ignore_hidden: true

# Unmatched file strategy: "leave" or destination folder name e.g. "Other"
unmatched_category: "leave"

# Rotating audit log
logging:
  file: "~/.local/state/file-organizer/file-organizer.log"
  max_bytes: 10485760   # 10 MB
  backup_count: 5
  level: "INFO"

# Category mappings
categories:
  PDFs:
    folder: "PDFs"
    extensions: [".pdf"]

  Documents:
    folder: "Documents"
    extensions: [".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".tex", ".epub"]

  Spreadsheets:
    folder: "Spreadsheets"
    extensions: [".xlsx", ".xls", ".csv", ".tsv", ".ods", ".numbers"]

  Images:
    folder: "Images"
    extensions: [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".tiff"]

  Videos:
    folder: "Videos"
    extensions: [".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm"]

  Audio:
    folder: "Audio"
    extensions: [".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"]

  Archives:
    folder: "Archives"
    extensions: [".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".7z", ".rar", ".iso"]

  Installers:
    folder: "Installers"
    extensions: [".deb", ".appimage", ".rpm", ".sh", ".run", ".flatpakref"]

  Code:
    folder: "Code"
    extensions: [".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".c", ".rs", ".go"]
```

After modifying the configuration file, reload the service:
```bash
file-organizer reload
```

---

## systemd Service Management

The service runs under the systemd user manager (`systemctl --user`).

```bash
# Check service status
systemctl --user status file-organizer.service

# View live streaming logs
journalctl --user -u file-organizer.service -f

# Restart the service
systemctl --user restart file-organizer.service

# Stop the service
systemctl --user stop file-organizer.service

# Disable service autostart
systemctl --user disable file-organizer.service
```

---

## Running Unit Tests

Unit tests are written with `pytest` and cover configuration parsing, extension matching, collision resolution, stability detection, and the CLI interface:

```bash
~/.local/share/file-organizer/venv/bin/pytest tests/ -v
```

Output:
```text
tests/test_cli.py::test_build_parser_options PASSED
tests/test_cli.py::test_apply_cli_overrides PASSED
tests/test_cli.py::test_cli_scan_dry_run PASSED
tests/test_cli.py::test_cli_scan_real PASSED
tests/test_cli.py::test_cli_config_dump PASSED
tests/test_config.py::test_normalize_extension PASSED
tests/test_config.py::test_resolve_path PASSED
tests/test_config.py::test_parse_raw_dict_defaults PASSED
tests/test_config.py::test_load_config_default_fallback PASSED
tests/test_config.py::test_custom_yaml_loading PASSED
tests/test_organizer.py::test_extract_extension PASSED
tests/test_organizer.py::test_get_category_for_file PASSED
tests/test_organizer.py::test_resolve_collision_numeric PASSED
tests/test_organizer.py::test_resolve_collision_compound_extension PASSED
tests/test_organizer.py::test_resolve_collision_skip PASSED
tests/test_organizer.py::test_resolve_collision_timestamp PASSED
tests/test_organizer.py::test_organize_file_success PASSED
tests/test_organizer.py::test_organize_file_collision PASSED
tests/test_organizer.py::test_organize_file_dry_run PASSED
tests/test_organizer.py::test_organize_file_hidden_ignored PASSED
tests/test_organizer.py::test_is_inside_destination PASSED
tests/test_organizer.py::test_organize_directory PASSED
tests/test_watcher.py::test_active_processing_tracker PASSED
tests/test_watcher.py::test_active_processing_tracker_concurrency PASSED
tests/test_watcher.py::test_stability_ignored_extension PASSED
tests/test_watcher.py::test_stability_stable_file PASSED
tests/test_watcher.py::test_stability_growing_file PASSED
tests/test_watcher.py::test_event_handler_ignores_temp_and_hidden PASSED
============================== 28 passed ==============================
```

---

## Uninstallation

To remove the background service and launcher:
```bash
./uninstall.sh
```

To also remove configuration files and historical logs:
```bash
./uninstall.sh --purge
```

---

## License

MIT License. See [pyproject.toml](file:///home/yared/H_:%29/Tools/pyproject.toml) for details.
# File-Auto-Organizer
