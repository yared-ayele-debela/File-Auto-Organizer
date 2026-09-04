"""
Configuration management for File Auto-Organizer.

Handles loading, validating, and normalizing configuration from YAML/JSON files,
system locations, environment variables, or defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # Handled gracefully if JSON is used or YAML missing

DEFAULT_CONFIG_LOCATIONS = [
    Path.home() / ".config" / "file-organizer" / "config.yaml",
    Path.home() / ".config" / "file-organizer" / "config.yml",
    Path.home() / ".config" / "file-organizer" / "config.json",
]

DEFAULT_WATCH_DIR = Path.home() / "Downloads"
DEFAULT_LOG_FILE = Path.home() / ".local" / "state" / "file-organizer" / "file-organizer.log"

DEFAULT_CONFIG_DATA: dict[str, Any] = {
    "watch_directory": "~/Downloads",
    "recursive": False,
    "conflict_resolution": "numeric",
    "stability": {
        "check_interval_seconds": 1.0,
        "min_stable_checks": 2,
        "max_wait_seconds": 30.0,
        "ignored_extensions": [
            ".crdownload",
            ".part",
            ".tmp",
            ".temp",
            ".download",
            ".aria2",
            ".partial",
            ".lock",
        ],
    },
    "ignore_hidden": True,
    "unmatched_category": "leave",
    "logging": {
        "file": "~/.local/state/file-organizer/file-organizer.log",
        "max_bytes": 10485760,
        "backup_count": 5,
        "level": "INFO",
    },
    "categories": {
        "PDFs": {
            "folder": "PDFs",
            "extensions": [".pdf"],
        },
        "Documents": {
            "folder": "Documents",
            "extensions": [
                ".doc", ".docx", ".odt", ".rtf", ".txt",
                ".md", ".tex", ".epub", ".pages", ".djvu", ".rst", ".wps"
            ],
        },
        "Spreadsheets": {
            "folder": "Spreadsheets",
            "extensions": [".xlsx", ".xls", ".csv", ".tsv", ".ods", ".numbers"],
        },
        "Presentations": {
            "folder": "Presentations",
            "extensions": [".pptx", ".ppt", ".odp", ".key"],
        },
        "Images": {
            "folder": "Images",
            "extensions": [
                ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
                ".bmp", ".tiff", ".tif", ".ico", ".heic", ".heif",
                ".psd", ".ai", ".raw", ".cr2", ".nef", ".arw"
            ],
        },
        "Videos": {
            "folder": "Videos",
            "extensions": [
                ".mp4", ".mkv", ".avi", ".mov", ".flv",
                ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts"
            ],
        },
        "Audio": {
            "folder": "Audio",
            "extensions": [
                ".mp3", ".wav", ".ogg", ".flac", ".aac",
                ".m4a", ".wma", ".opus", ".mid", ".midi", ".alac"
            ],
        },
        "Archives": {
            "folder": "Archives",
            "extensions": [
                ".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst",
                ".tgz", ".tbz2", ".txz", ".tar", ".gz", ".bz2", ".xz",
                ".zst", ".7z", ".rar", ".iso", ".dmg", ".cab"
            ],
        },
        "Installers": {
            "folder": "Installers",
            "extensions": [
                ".deb", ".appimage", ".rpm", ".sh", ".run",
                ".flatpakref", ".flatpak", ".apk", ".exe", ".msi"
            ],
        },
        "Code": {
            "folder": "Code",
            "extensions": [
                ".py", ".js", ".ts", ".jsx", ".tsx", ".html",
                ".htm", ".css", ".scss", ".json", ".yaml", ".yml",
                ".xml", ".c", ".cpp", ".h", ".hpp", ".rs", ".go",
                ".java", ".kt", ".sql", ".php", ".rb", ".lua",
                ".swift", ".toml", ".dockerfile"
            ],
        },
    },
}


@dataclass(frozen=True)
class StabilityConfig:
    """Configuration for race condition guarding and stability checking."""
    check_interval_seconds: float = 1.0
    min_stable_checks: int = 2
    max_wait_seconds: float = 30.0
    ignored_extensions: frozenset[str] = field(default_factory=lambda: frozenset([
        ".crdownload", ".part", ".tmp", ".temp", ".download", ".aria2", ".partial", ".lock"
    ]))


@dataclass
class CategoryConfig:
    """Configuration for a single file category."""
    name: str
    folder: Path
    extensions: tuple[str, ...]
    raw_folder: str = ""
    is_custom_absolute: bool = False


@dataclass(frozen=True)
class LoggingConfig:
    """Configuration for logging."""
    file: Path = DEFAULT_LOG_FILE
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    level: str = "INFO"


@dataclass
class AppConfig:
    """Complete application configuration."""
    watch_directory: Path = DEFAULT_WATCH_DIR
    recursive: bool = False
    conflict_resolution: str = "numeric"  # "numeric", "timestamp", "skip"
    stability: StabilityConfig = field(default_factory=StabilityConfig)
    ignore_hidden: bool = True
    unmatched_category: str | None = "leave"
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    categories: dict[str, CategoryConfig] = field(default_factory=dict)
    # Reverse lookup map: normalized extension (e.g. '.tar.gz') -> CategoryConfig
    extension_map: dict[str, CategoryConfig] = field(default_factory=dict)
    # List of compound extensions (multi-part like .tar.gz) sorted by length descending
    compound_extensions: tuple[str, ...] = field(default_factory=tuple)
    config_source: Path | None = None

    def set_watch_directory(self, new_dir: Path | str) -> None:
        """Update watch directory and re-anchor relative category folders."""
        self.watch_directory = resolve_path(new_dir)
        for cat in self.categories.values():
            if not cat.is_custom_absolute:
                cat.folder = resolve_path(cat.raw_folder, base_dir=self.watch_directory)


def normalize_extension(ext: str) -> str:
    """Ensure extension starts with a dot and is lowercase."""
    ext = ext.strip().lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return ext


def resolve_path(path_str: str | Path, base_dir: Path | None = None) -> Path:
    """Expand environment variables and ~ in paths, and resolve relative paths."""
    expanded = Path(os.path.expandvars(os.path.expanduser(str(path_str))))
    if not expanded.is_absolute() and base_dir is not None:
        return (base_dir / expanded).resolve()
    return expanded.resolve()


def find_config_file(cli_path: Path | str | None = None) -> Path | None:
    """
    Search for a configuration file in order of priority:
      1. Explicit CLI argument
      2. FILE_ORGANIZER_CONFIG environment variable
      3. User configuration directory (~/.config/file-organizer/config.yaml, etc.)
      4. Workspace/current directory (config/default_config.yaml)
    """
    if cli_path:
        p = Path(cli_path).expanduser().resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Specified configuration file does not exist: {cli_path}")

    env_path = os.environ.get("FILE_ORGANIZER_CONFIG")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.is_file():
            return p

    for default_path in DEFAULT_CONFIG_LOCATIONS:
        if default_path.is_file():
            return default_path

    # Check local repository / package default
    pkg_default = Path(__file__).parent.parent / "config" / "default_config.yaml"
    if pkg_default.is_file():
        return pkg_default.resolve()

    return None


def parse_raw_dict(data: dict[str, Any], config_source: Path | None = None) -> AppConfig:
    """Parse and validate a dictionary into an AppConfig instance."""
    # Watch directory
    watch_dir_raw = data.get("watch_directory", "~/Downloads")
    watch_directory = resolve_path(watch_dir_raw)

    recursive = bool(data.get("recursive", False))
    conflict_resolution = str(data.get("conflict_resolution", "numeric")).lower()
    if conflict_resolution not in {"numeric", "timestamp", "skip"}:
        conflict_resolution = "numeric"

    ignore_hidden = bool(data.get("ignore_hidden", True))
    unmatched_category = data.get("unmatched_category", "leave")
    if unmatched_category and str(unmatched_category).lower() in {"leave", "none", "null", ""}:
        unmatched_category = None

    # Stability
    stab_raw = data.get("stability", {})
    check_interval = float(stab_raw.get("check_interval_seconds", 1.0))
    min_stable = int(stab_raw.get("min_stable_checks", 2))
    max_wait = float(stab_raw.get("max_wait_seconds", 30.0))
    ignored_exts = {
        normalize_extension(e)
        for e in stab_raw.get("ignored_extensions", [
            ".crdownload", ".part", ".tmp", ".temp", ".download", ".aria2", ".partial", ".lock"
        ])
    }
    stability = StabilityConfig(
        check_interval_seconds=max(0.1, check_interval),
        min_stable_checks=max(1, min_stable),
        max_wait_seconds=max(1.0, max_wait),
        ignored_extensions=frozenset(ignored_exts),
    )

    # Logging
    log_raw = data.get("logging", {})
    log_file_raw = log_raw.get("file", str(DEFAULT_LOG_FILE))
    log_file = resolve_path(log_file_raw)
    max_bytes = int(log_raw.get("max_bytes", 10 * 1024 * 1024))
    backup_count = int(log_raw.get("backup_count", 5))
    level = str(log_raw.get("level", "INFO")).upper()
    logging_cfg = LoggingConfig(
        file=log_file,
        max_bytes=max_bytes,
        backup_count=backup_count,
        level=level,
    )

    # Categories
    categories_raw = data.get("categories", {})
    categories: dict[str, CategoryConfig] = {}
    extension_map: dict[str, CategoryConfig] = {}
    compound_ext_set: set[str] = set()

    for cat_name, cat_info in categories_raw.items():
        folder_raw = str(cat_info.get("folder", cat_name))
        is_custom_absolute = Path(os.path.expanduser(folder_raw)).is_absolute()
        folder_path = resolve_path(folder_raw, base_dir=watch_directory)
        raw_extensions = cat_info.get("extensions", [])
        norm_extensions = tuple(normalize_extension(e) for e in raw_extensions if e)

        cat_cfg = CategoryConfig(
            name=str(cat_name),
            folder=folder_path,
            extensions=norm_extensions,
            raw_folder=folder_raw,
            is_custom_absolute=is_custom_absolute,
        )
        categories[str(cat_name)] = cat_cfg

        for ext in norm_extensions:
            extension_map[ext] = cat_cfg
            if ext.count(".") > 1:
                compound_ext_set.add(ext)

    # Sort compound extensions by length descending for greedy matching (.tar.gz before .gz)
    compound_extensions = tuple(sorted(compound_ext_set, key=lambda x: len(x), reverse=True))

    return AppConfig(
        watch_directory=watch_directory,
        recursive=recursive,
        conflict_resolution=conflict_resolution,
        stability=stability,
        ignore_hidden=ignore_hidden,
        unmatched_category=unmatched_category,
        logging=logging_cfg,
        categories=categories,
        extension_map=extension_map,
        compound_extensions=compound_extensions,
        config_source=config_source,
    )


def load_config(path: Path | str | None = None) -> AppConfig:
    """
    Load and parse configuration from path or discovery locations.
    Falls back to built-in default configuration if no file is found.
    """
    config_file = find_config_file(path)
    if not config_file:
        return parse_raw_dict(DEFAULT_CONFIG_DATA, config_source=None)

    content = config_file.read_text(encoding="utf-8")
    if config_file.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        if yaml is None:
            raise RuntimeError("PyYAML is required to parse YAML configuration files.")
        data = yaml.safe_load(content) or {}

    return parse_raw_dict(data, config_source=config_file)


def create_default_user_config(force: bool = False) -> Path:
    """
    Create a default user configuration file at ~/.config/file-organizer/config.yaml.

    Args:
        force: If True, overwrite existing file.

    Returns:
        Path to created or existing config file.
    """
    dest_path = Path.home() / ".config" / "file-organizer" / "config.yaml"
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if dest_path.exists() and not force:
        return dest_path

    # If repo default_config.yaml is available, copy it preserving comments
    pkg_default = Path(__file__).parent.parent / "config" / "default_config.yaml"
    if pkg_default.is_file():
        dest_path.write_text(pkg_default.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        # Fallback to serializing DEFAULT_CONFIG_DATA
        if yaml:
            dest_path.write_text(yaml.dump(DEFAULT_CONFIG_DATA, sort_keys=False), encoding="utf-8")
        else:
            dest_path.write_text(json.dumps(DEFAULT_CONFIG_DATA, indent=2), encoding="utf-8")

    return dest_path
