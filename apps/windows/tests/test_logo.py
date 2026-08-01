"""Tests for custom logo discovery."""

from __future__ import annotations

import sys

from windows_rectangle.ui import logo


def test_find_logo_file_prefers_env_configured_directory(tmp_path, monkeypatch):
    env_dir = tmp_path / "env-logo"
    repo_dir = tmp_path / "repo"
    env_dir.mkdir()
    (env_dir / "logo.png").write_bytes(b"not a real image")
    (repo_dir / "logo").mkdir(parents=True)
    (repo_dir / "logo" / "windows.ico").write_bytes(b"repo icon")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(env_dir))
    monkeypatch.setattr(logo, "_repo_root", lambda: repo_dir)

    assert logo.find_logo_file() == env_dir / "logo.png"


def test_find_logo_file_prefers_windows_ico_inside_same_directory(tmp_path, monkeypatch):
    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    (logo_dir / "logo.png").write_bytes(b"png")
    (logo_dir / "windows.ico").write_bytes(b"ico")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(logo_dir))
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path / "repo")

    assert logo.find_logo_file() == logo_dir / "windows.ico"


def test_find_logo_file_supports_webp_files(tmp_path, monkeypatch):
    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    (logo_dir / "logo.webp").write_bytes(b"webp")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(logo_dir))
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path / "repo")

    assert logo.find_logo_file() == logo_dir / "logo.webp"


def test_find_logo_file_keeps_png_priority_over_webp(tmp_path, monkeypatch):
    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    (logo_dir / "logo.webp").write_bytes(b"webp")
    (logo_dir / "logo.png").write_bytes(b"png")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(logo_dir))
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path / "repo")

    assert logo.find_logo_file() == logo_dir / "logo.png"


def test_find_tray_logo_file_uses_tray_specific_asset(tmp_path, monkeypatch):
    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    (logo_dir / "logo.png").write_bytes(b"app logo")
    (logo_dir / "tray_logo.png").write_bytes(b"tray logo")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(logo_dir))
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path / "repo")

    assert logo.find_tray_logo_file() == logo_dir / "tray_logo.png"


def test_find_tray_logo_file_ignores_regular_logo(tmp_path, monkeypatch):
    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    (logo_dir / "logo.png").write_bytes(b"app logo")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(logo_dir))
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path / "repo")

    assert logo.find_tray_logo_file() is None


def test_find_logo_file_checks_pyinstaller_resource_directory(tmp_path, monkeypatch):
    bundled_logo = tmp_path / "bundle" / "logo"
    bundled_logo.mkdir(parents=True)
    (bundled_logo / "app.png").write_bytes(b"png")
    monkeypatch.delenv("WINDOWS_RECTANGLE_LOGO_DIR", raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path / "repo")

    assert logo.find_logo_file() == bundled_logo / "app.png"


def test_find_logo_file_returns_none_when_no_supported_logo_exists(tmp_path, monkeypatch):
    (tmp_path / "logo").mkdir()
    (tmp_path / "logo" / "README.md").write_text("docs only", encoding="utf-8")
    monkeypatch.delenv("WINDOWS_RECTANGLE_LOGO_DIR", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(logo, "_repo_root", lambda: tmp_path)

    assert logo.find_logo_file() is None
