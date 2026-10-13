"""bump_version スクリプトのユニットテスト。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "test_bump_version_module", SCRIPTS_DIR / "bump_version.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_bump_version_module"] = module
    spec.loader.exec_module(module)
    return module


def _setup_files(root: Path) -> None:
    (root / "pyproject.toml").write_bytes(
        b'[project]\nname = "x"\nversion = "1.2.3"\n'
    )
    (root / "useful_blockchain").mkdir()
    (root / "useful_blockchain" / "__init__.py").write_bytes(
        b'__version__ = "1.2.3"\n'
    )
    (root / "setup.py").write_bytes(b"VERSION = '1.2.3'\n")


def test_write_version_updates_files_preserving_lf_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    _setup_files(tmp_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    module.write_version("1.2.4")

    assert b'version = "1.2.4"' in (tmp_path / "pyproject.toml").read_bytes()
    assert b'__version__ = "1.2.4"' in (
        tmp_path / "useful_blockchain" / "__init__.py"
    ).read_bytes()
    assert b"VERSION = '1.2.4'" in (tmp_path / "setup.py").read_bytes()
    # 行末が CRLF に変換されないこと
    assert b"\r" not in (tmp_path / "pyproject.toml").read_bytes()
    assert (
        b"\r" not in (tmp_path / "useful_blockchain" / "__init__.py").read_bytes()
    )
    assert b"\r" not in (tmp_path / "setup.py").read_bytes()


def test_write_version_preserves_existing_crlf_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    (tmp_path / "pyproject.toml").write_bytes(
        b'[project]\r\nname = "x"\r\nversion = "1.2.3"\r\n'
    )
    (tmp_path / "useful_blockchain").mkdir()
    (tmp_path / "useful_blockchain" / "__init__.py").write_bytes(
        b'__version__ = "1.2.3"\r\n'
    )
    (tmp_path / "setup.py").write_bytes(b"VERSION = '1.2.3'\r\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    module.write_version("1.2.4")

    assert (
        tmp_path / "pyproject.toml"
    ).read_bytes() == b'[project]\r\nname = "x"\r\nversion = "1.2.4"\r\n'
    assert (
        tmp_path / "useful_blockchain" / "__init__.py"
    ).read_bytes() == b'__version__ = "1.2.4"\r\n'
    assert (tmp_path / "setup.py").read_bytes() == b"VERSION = '1.2.4'\r\n"
