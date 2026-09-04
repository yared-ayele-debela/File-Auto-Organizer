"""
Unit tests for CLI parser and commands.
"""

from pathlib import Path
import pytest

from file_organizer.cli import apply_cli_overrides, build_parser, main
from file_organizer.config import load_config


def test_build_parser_options():
    parser = build_parser()

    # Help/dry-run parse
    args = parser.parse_args(["-n", "-v", "-d", "/tmp/test", "scan"])
    assert args.dry_run is True
    assert args.verbose is True
    assert args.watch_dir == "/tmp/test"
    assert args.command == "scan"

    args_watch = parser.parse_args(["watch", "--workers", "8"])
    assert args_watch.command == "watch"
    assert args_watch.workers == 8

    args_config = parser.parse_args(["config", "--dump"])
    assert args_config.command == "config"
    assert args_config.dump is True


def test_apply_cli_overrides(tmp_path: Path):
    parser = build_parser()
    args = parser.parse_args(["-d", str(tmp_path), "scan"])
    config = load_config(None)

    updated_config = apply_cli_overrides(config, args)
    assert updated_config.watch_directory == tmp_path.resolve()


def test_cli_scan_dry_run(tmp_path: Path, capsys):
    # Create test files
    (tmp_path / "test.pdf").write_text("dummy", encoding="utf-8")
    (tmp_path / "test.jpg").write_text("dummy", encoding="utf-8")

    exit_code = main(["-d", str(tmp_path), "--dry-run", "scan"])
    assert exit_code == 0
    # Original files should not have been moved
    assert (tmp_path / "test.pdf").exists()
    assert (tmp_path / "test.jpg").exists()


def test_cli_scan_real(tmp_path: Path):
    (tmp_path / "doc.pdf").write_text("dummy", encoding="utf-8")

    exit_code = main(["-d", str(tmp_path), "scan"])
    assert exit_code == 0
    # Original file moved
    assert not (tmp_path / "doc.pdf").exists()
    assert (tmp_path / "PDFs" / "doc.pdf").exists()


def test_cli_config_dump(capsys):
    exit_code = main(["config", "--dump"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Watch Directory:" in captured.out
    assert "Categories" in captured.out
