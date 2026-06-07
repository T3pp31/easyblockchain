#!/usr/bin/env python3
"""プロジェクト内のバージョン文字列を一括更新する。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def read_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "(\d+\.\d+\.\d+)"', pyproject, re.MULTILINE)
    if not match:
        raise SystemExit("version not found in pyproject.toml")
    return match.group(1)


def bump_version(current: str, bump: str) -> str:
    matched = VERSION_PATTERN.fullmatch(current)
    if not matched:
        raise SystemExit(f"invalid version format: {current!r}")
    major, minor, patch = (int(part) for part in matched.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version(new_version: str) -> None:
    replacements: list[tuple[Path, tuple[str, str]]] = [
        (
            ROOT / "pyproject.toml",
            (
                r'^version = "\d+\.\d+\.\d+"',
                f'version = "{new_version}"',
            ),
        ),
        (
            ROOT / "useful_blockchain" / "__init__.py",
            (
                r'__version__ = "\d+\.\d+\.\d+"',
                f'__version__ = "{new_version}"',
            ),
        ),
        (
            ROOT / "setup.py",
            (
                r"VERSION = '\d+\.\d+\.\d+'",
                f"VERSION = '{new_version}'",
            ),
        ),
    ]
    for path, (pattern, replacement) in replacements:
        text = path.read_text(encoding="utf-8")
        updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"failed to update version in {path}")
        path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump package version")
    parser.add_argument(
        "bump",
        choices=["patch", "minor", "major"],
        help="Semantic version bump type",
    )
    args = parser.parse_args()
    new_version = bump_version(read_version(), args.bump)
    write_version(new_version)
    sys.stdout.write(f"{new_version}\n")


if __name__ == "__main__":
    main()
