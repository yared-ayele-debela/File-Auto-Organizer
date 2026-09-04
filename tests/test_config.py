"""
Unit tests for configuration loading and validation.
"""

from pathlib import Path
import tempfile
import pytest

from file_organizer.config import (
    AppConfig,
    load_config,
    normalize_extension,
    parse_raw_dict,
    resolve_path,
    create_default_user_config,
)


def test_normalize_extension():
    assert normalize_extension("pdf") == ".pdf"
    assert normalize_extension(".PDF") == ".pdf"
    assert normalize_extension("  .tar.gz  ") == ".tar.gz"
    assert normalize_extension(".Deb") == ".deb"


def test_resolve_path():
    base = Path("/home/user/test_base")
    # Relative path should resolve against base
    resolved_rel = resolve_path("subfolder/file.txt", base_dir=base)
    assert resolved_rel == (base / "subfolder/file.txt").resolve()

    # Absolute path remains absolute
    resolved_abs = resolve_path("/var/log", base_dir=base)
    assert resolved_abs == Path("/var/log")


def test_parse_raw_dict_defaults():
    raw = {
        "watch_directory": "~/Downloads",
        "conflict_resolution": "numeric",
        "categories": {
            "PDFs": {
                "folder": "PDFs",
                "extensions": [".pdf"],
            },
            "Archives": {
                "folder": "Archives",
                "extensions": [".zip", ".tar.gz"],
            },
        },
    }
    config = parse_raw_dict(raw)
    assert isinstance(config, AppConfig)
    assert config.conflict_resolution == "numeric"
    assert ".pdf" in config.extension_map
    assert config.extension_map[".pdf"].name == "PDFs"
    assert ".tar.gz" in config.compound_extensions
    assert config.extension_map[".tar.gz"].name == "Archives"


def test_load_config_default_fallback():
    # Calling load_config with None should return valid AppConfig without crashing
    config = load_config(None)
    assert isinstance(config, AppConfig)
    assert "PDFs" in config.categories
    assert "Documents" in config.categories
    assert "Images" in config.categories
    assert ".pdf" in config.extension_map


def test_custom_yaml_loading(tmp_path):
    custom_yaml = tmp_path / "custom_config.yaml"
    custom_yaml.write_text("""
watch_directory: "~/CustomWatch"
conflict_resolution: "timestamp"
categories:
  CustomCat:
    folder: "CustomFolder"
    extensions:
      - ".custom"
      - ".special.dat"
""", encoding="utf-8")

    config = load_config(custom_yaml)
    assert config.conflict_resolution == "timestamp"
    assert ".custom" in config.extension_map
    assert config.extension_map[".custom"].name == "CustomCat"
    assert ".special.dat" in config.compound_extensions
