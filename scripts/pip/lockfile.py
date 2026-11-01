"""Parse requirements-fixed.txt pins."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterator

DEFAULT_REQUIREMENTS = os.path.join(
    os.path.dirname(__file__), "..", "requirements-fixed.txt"
)
DEFAULT_INDEX = (
    "https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi/simple"
)
PYTHON_TAG = os.environ.get("CHECK_INDEX_PYTHON_TAG", "cp312")


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Pin:
    name: str
    version: str
    marker: str | None
    line_no: int
    raw: str


def requirements_path() -> str:
    return os.environ.get("REQUIREMENTS_FIXED", DEFAULT_REQUIREMENTS)


def parse_pins(path: str | None = None) -> list[Pin]:
    path = path or requirements_path()
    pins: list[Pin] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("--"):
                continue
            req, _, marker = stripped.partition(";")
            req = req.strip()
            m = re.match(
                r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)(?:\[[^\]]+\])?==(.+)$",
                req,
            )
            if not m:
                continue
            pins.append(
                Pin(
                    name=normalize_name(m.group(1)),
                    version=m.group(2).strip(),
                    marker=marker.strip() if marker.strip() else None,
                    line_no=line_no,
                    raw=stripped,
                )
            )
    return pins


def unique_pins(pins: list[Pin]) -> Iterator[Pin]:
    seen: set[tuple[str, str]] = set()
    for p in pins:
        key = (p.name, p.version)
        if key in seen:
            continue
        seen.add(key)
        yield p


def skip_marker_for_os(marker: str | None, os_key: str) -> bool:
    if not marker:
        return False
    if os_key in ("linux", "mac_arm"):
        return (
            'platform_system == "Windows"' in marker
            or 'sys_platform == "win32"' in marker
        )
    return False


def lock_version_map(pins: list[Pin]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pins:
        out[p.name] = p.version
    return out
