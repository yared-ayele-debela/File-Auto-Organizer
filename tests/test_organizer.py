"""
Unit tests for categorization logic, collision handling, and file movement.
"""

from pathlib import Path
import pytest

from file_organizer.config import AppConfig, CategoryConfig, parse_raw_dict
from file_organizer.organizer import (
    extract_extension,
    get_category_for_file,
    is_inside_destination,
    organize_directory,
    organize_file,
    resolve_collision,
)


@pytest.fixture
def mock_config(tmp_path: Path) -> AppConfig:
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir(parents=True, exist_ok=True)

    raw_data = {
        "watch_directory": str(watch_dir),
        "recursive": False,
        "conflict_resolution": "numeric",
        "ignore_hidden": True,
        "unmatched_category": "Other",
        "categories": {
            "PDFs": {
                "folder": str(watch_dir / "PDFs"),
                "extensions": [".pdf"],
            },
            "Documents": {
                "folder": str(watch_dir / "Documents"),
                "extensions": [".docx", ".txt", ".odt"],
            },
            "Archives": {
                "folder": str(watch_dir / "Archives"),
                "extensions": [".zip", ".tar.gz", ".tar.bz2"],
            },
            "Images": {
                "folder": str(watch_dir / "Images"),
                "extensions": [".jpg", ".png"],
            },
            "Installers": {
                "folder": str(watch_dir / "Installers"),
                "extensions": [".deb", ".appimage"],
            },
        },
    }
    return parse_raw_dict(raw_data)


def test_extract_extension():
    compounds = (".tar.gz", ".tar.bz2")
    stem, ext = extract_extension(Path("document.pdf"), compounds)
    assert stem == "document"
    assert ext == ".pdf"

    stem, ext = extract_extension(Path("backup.tar.gz"), compounds)
    assert stem == "backup"
    assert ext == ".tar.gz"

    stem, ext = extract_extension(Path("UPPERCASE.TAR.GZ"), compounds)
    assert stem == "UPPERCASE"
    assert ext == ".tar.gz"

    stem, ext = extract_extension(Path("no_extension"), compounds)
    assert stem == "no_extension"
    assert ext == ""


def test_get_category_for_file(mock_config: AppConfig):
    cat_pdf = get_category_for_file(Path("test.pdf"), mock_config)
    assert cat_pdf is not None
    assert cat_pdf.name == "PDFs"

    cat_upper = get_category_for_file(Path("TEST.PDF"), mock_config)
    assert cat_upper is not None
    assert cat_upper.name == "PDFs"

    cat_archive = get_category_for_file(Path("my_archive.tar.gz"), mock_config)
    assert cat_archive is not None
    assert cat_archive.name == "Archives"

    cat_installer = get_category_for_file(Path("app.AppImage"), mock_config)
    assert cat_installer is not None
    assert cat_installer.name == "Installers"

    cat_unknown = get_category_for_file(Path("data.xyz"), mock_config)
    assert cat_unknown is None


def test_resolve_collision_numeric(tmp_path: Path):
    dest_file = tmp_path / "sample.pdf"
    dest_file.write_text("existing content 0", encoding="utf-8")

    # First collision -> sample (1).pdf
    candidate1 = resolve_collision(dest_file, strategy="numeric")
    assert candidate1 == tmp_path / "sample (1).pdf"

    # Create candidate 1
    candidate1.write_text("existing content 1", encoding="utf-8")

    # Second collision -> sample (2).pdf
    candidate2 = resolve_collision(dest_file, strategy="numeric")
    assert candidate2 == tmp_path / "sample (2).pdf"


def test_resolve_collision_compound_extension(tmp_path: Path):
    compounds = (".tar.gz",)
    dest_file = tmp_path / "archive.tar.gz"
    dest_file.write_text("dummy archive", encoding="utf-8")

    candidate = resolve_collision(dest_file, strategy="numeric", compound_extensions=compounds)
    assert candidate == tmp_path / "archive (1).tar.gz"


def test_resolve_collision_skip(tmp_path: Path):
    dest_file = tmp_path / "sample.pdf"
    dest_file.write_text("existing", encoding="utf-8")

    candidate = resolve_collision(dest_file, strategy="skip")
    assert candidate is None


def test_resolve_collision_timestamp(tmp_path: Path):
    dest_file = tmp_path / "sample.pdf"
    dest_file.write_text("existing", encoding="utf-8")

    candidate = resolve_collision(dest_file, strategy="timestamp")
    assert candidate is not None
    assert candidate != dest_file
    assert candidate.name.startswith("sample_")
    assert candidate.name.endswith(".pdf")


def test_organize_file_success(mock_config: AppConfig):
    watch_dir = mock_config.watch_directory
    source_file = watch_dir / "invoice.pdf"
    source_file.write_text("PDF content", encoding="utf-8")

    res = organize_file(source_file, mock_config, dry_run=False)
    assert res.moved is True
    assert res.category == "PDFs"
    assert not source_file.exists()
    assert (watch_dir / "PDFs" / "invoice.pdf").exists()


def test_organize_file_collision(mock_config: AppConfig):
    watch_dir = mock_config.watch_directory
    pdf_dir = watch_dir / "PDFs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "statement.pdf").write_text("Existing statement", encoding="utf-8")

    # New incoming file with same name
    new_incoming = watch_dir / "statement.pdf"
    new_incoming.write_text("New statement", encoding="utf-8")

    res = organize_file(new_incoming, mock_config, dry_run=False)
    assert res.moved is True
    assert res.collision_resolved is True
    assert (pdf_dir / "statement (1).pdf").exists()
    assert (pdf_dir / "statement.pdf").read_text(encoding="utf-8") == "Existing statement"
    assert (pdf_dir / "statement (1).pdf").read_text(encoding="utf-8") == "New statement"


def test_organize_file_dry_run(mock_config: AppConfig):
    watch_dir = mock_config.watch_directory
    source_file = watch_dir / "photo.jpg"
    source_file.write_text("binary data", encoding="utf-8")

    res = organize_file(source_file, mock_config, dry_run=True)
    assert res.moved is True
    # Source file MUST still exist in dry-run mode
    assert source_file.exists()
    # Destination directory should NOT be created
    assert not (watch_dir / "Images").exists()


def test_organize_file_hidden_ignored(mock_config: AppConfig):
    watch_dir = mock_config.watch_directory
    hidden_file = watch_dir / ".hidden_file.txt"
    hidden_file.write_text("hidden", encoding="utf-8")

    res = organize_file(hidden_file, mock_config, dry_run=False)
    assert res.moved is False
    assert hidden_file.exists()


def test_is_inside_destination(mock_config: AppConfig):
    watch_dir = mock_config.watch_directory
    dest_dir = watch_dir / "PDFs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    nested_file = dest_dir / "inside.pdf"
    nested_file.write_text("content", encoding="utf-8")

    assert is_inside_destination(nested_file, mock_config) is True
    assert is_inside_destination(watch_dir / "top_level.pdf", mock_config) is False


def test_organize_directory(mock_config: AppConfig):
    watch_dir = mock_config.watch_directory
    (watch_dir / "file1.docx").write_text("doc", encoding="utf-8")
    (watch_dir / "file2.pdf").write_text("pdf", encoding="utf-8")
    (watch_dir / "file3.png").write_text("png", encoding="utf-8")
    (watch_dir / "unknown.xyz").write_text("xyz", encoding="utf-8")

    moved, skipped = organize_directory(watch_dir, mock_config, dry_run=False)
    # file1 (Documents), file2 (PDFs), file3 (Images), unknown (Other)
    assert moved == 4
    assert (watch_dir / "Documents" / "file1.docx").exists()
    assert (watch_dir / "PDFs" / "file2.pdf").exists()
    assert (watch_dir / "Images" / "file3.png").exists()
    assert (watch_dir / "Other" / "unknown.xyz").exists()
