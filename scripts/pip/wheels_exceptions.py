"""Platform-specific wheel check exceptions (see wheels-os-exceptions.yml)."""

from __future__ import annotations

import os
from pathlib import Path

from lockfile import normalize_name

DEFAULT_EXCEPTIONS = os.path.join(
    os.path.dirname(__file__), "wheels-os-exceptions.yml"
)

OsKey = str


def exceptions_path() -> str:
    return os.environ.get("WHEELS_OS_EXCEPTIONS", DEFAULT_EXCEPTIONS)


def _load_package_os_only(path: str) -> dict[str, frozenset[OsKey]]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return _load_plaintext(path)

    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    raw = data.get("package_os_only")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, frozenset[OsKey]] = {}
    for pkg, os_list in raw.items():
        if not isinstance(os_list, list):
            continue
        out[normalize_name(str(pkg))] = frozenset(str(x) for x in os_list)
    return out


def _load_plaintext(path: str) -> dict[str, frozenset[OsKey]]:
    """Minimal YAML subset when PyYAML is unavailable."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith(":") and not stripped.startswith("-"):
                current = normalize_name(stripped[:-1])
                out[current] = []
                continue
            if current and stripped.startswith("- "):
                out[current].append(stripped[2:].strip())
    return {k: frozenset(v) for k, v in out.items()}


_cache: dict[str, dict[str, frozenset[OsKey]]] | None = None


def package_os_only_map(path: str | None = None) -> dict[str, frozenset[OsKey]]:
    global _cache
    path = path or exceptions_path()
    if _cache is not None and path in _cache:
        return _cache[path]
    loaded = _load_package_os_only(path)
    if _cache is None:
        _cache = {}
    _cache[path] = loaded
    return loaded


def skip_wheel_check_for_os(package: str, os_key: OsKey, path: str | None = None) -> bool:
    """True if this package should not be wheel-checked on os_key."""
    allowed = package_os_only_map(path).get(normalize_name(package))
    if allowed is None:
        return False
    return os_key not in allowed
