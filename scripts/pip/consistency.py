"""Offline structural lint for requirements-fixed.txt."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lockfile import DEFAULT_INDEX, parse_pins, requirements_path


@dataclass
class ConsistencyIssue:
    line_no: int
    message: str


def run_consistency(path: str | None = None) -> list[ConsistencyIssue]:
    path = path or requirements_path()
    issues: list[ConsistencyIssue] = []
    index_url: str | None = None
    pin_lines: list[tuple[int, str, str | None]] = []

    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("--index-url"):
                parts = stripped.split(None, 1)
                if len(parts) == 2:
                    index_url = parts[1].strip()
                continue
            if stripped.startswith("--"):
                continue
            req, _, marker = stripped.partition(";")
            req = req.strip()
            if "==" not in req:
                issues.append(
                    ConsistencyIssue(
                        line_no,
                        f"expected pip-compile pin with ==, got: {req[:60]}",
                    )
                )
                continue
            m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)(?:\[[^\]]+\])?==(.+)$", req)
            if not m:
                issues.append(
                    ConsistencyIssue(line_no, f"malformed requirement: {req[:80]}")
                )
                continue
            pin_lines.append((line_no, m.group(1), marker.strip() or None))

    if index_url is None:
        issues.append(ConsistencyIssue(0, "missing --index-url header"))
    elif "nordic-pypi" not in index_url and index_url.rstrip("/") != DEFAULT_INDEX:
        issues.append(
            ConsistencyIssue(
                0,
                f"--index-url should point at Nordic PyPI, got: {index_url}",
            )
        )

    pins = parse_pins(path)
    by_name: dict[str, set[str]] = {}
    first_line: dict[str, int] = {}
    for p in pins:
        by_name.setdefault(p.name, set()).add(p.version)
        first_line.setdefault(p.name, p.line_no)
    for norm, versions in by_name.items():
        if len(versions) > 1:
            issues.append(
                ConsistencyIssue(
                    first_line[norm],
                    f"duplicate package {norm} with conflicting versions: {sorted(versions)}",
                )
            )

    return issues
