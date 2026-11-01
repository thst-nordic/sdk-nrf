"""Load pip-audit-whitelist.yml for Jenkins parity."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_WHITELIST = os.path.join(
    os.path.dirname(__file__), "..", "pip-audit-whitelist.yml"
)


def whitelist_path() -> str:
    return os.environ.get("PIP_AUDIT_WHITELIST", DEFAULT_WHITELIST)


def ignore_vuln_args(path: str | None = None) -> list[str]:
    path = path or whitelist_path()
    args: list[str] = []
    if not Path(path).is_file():
        return args
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return _ignore_vuln_args_plaintext(path)

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return args
    for _key, ids in data.items():
        if not isinstance(ids, list):
            continue
        for vid in ids:
            if vid:
                args.extend(["--ignore-vuln", str(vid)])
    return args


def _ignore_vuln_args_plaintext(path: str) -> list[str]:
    """Minimal parser when PyYAML is unavailable."""
    args: list[str] = []
    in_list = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.endswith(":") and not stripped.startswith("-"):
                in_list = True
                continue
            if in_list and stripped.startswith("- "):
                vid = stripped[2:].strip()
                if vid:
                    args.extend(["--ignore-vuln", vid])
    return args
