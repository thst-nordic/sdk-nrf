"""Check requires_dist from index JSON against lock pins (GET only)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Literal

from lockfile import lock_version_map, parse_pins, requirements_path, unique_pins

IndexKey = Literal["nordic", "pypi"]

NORDIC_JSON_BASE = os.environ.get(
    "NORDIC_PYPI_JSON_BASE",
    "https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi",
).rstrip("/")
PYPI_JSON_BASE = "https://pypi.org/pypi"

MARKER_ENV = {
    "python_version": "3.12",
    "python_full_version": "3.12.4",
    "platform_system": "Linux",
    "sys_platform": "linux",
    "os_name": "posix",
}


def _fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def fetch_release_json(name: str, ver: str, index: IndexKey) -> dict | None:
    slugs = [name, name.replace("-", "_"), name.replace("_", "-")]
    seen: set[str] = set()
    for slug in slugs:
        if slug in seen:
            continue
        seen.add(slug)
        if index == "pypi":
            url = f"{PYPI_JSON_BASE}/{slug}/{ver}/json"
        else:
            url = f"{NORDIC_JSON_BASE}/pypi/{slug}/{ver}/json"
        data = _fetch_json(url)
        if data and "info" in data:
            return data
    return None


def requires_dist_list(data: dict) -> list[str]:
    info = data.get("info") or {}
    rd = info.get("requires_dist")
    if not rd:
        return []
    if isinstance(rd, list):
        return [str(x) for x in rd if x]
    return []


def marker_applies(marker_str: str | None) -> bool:
    if not marker_str:
        return True
    try:
        from packaging.markers import Marker

        return Marker(marker_str).evaluate(MARKER_ENV)
    except Exception:
        return True


@dataclass
class ResolveIssue:
    from_package: str
    from_version: str
    requirement: str
    dependency: str
    lock_version: str | None
    message: str
    index: str


@dataclass
class ResolveMeta:
    package: str
    version: str
    index: str
    requires_dist: list[str]
    metadata_missing: bool = False


def _parse_req_name(spec: str) -> str | None:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    try:
        return canonicalize_name(Requirement(spec).name)
    except Exception:
        m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)", spec.split(";")[0].strip())
        return canonicalize_name(m.group(1)) if m else None


def _require_packaging():
    try:
        import packaging  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "resolve requires the packaging module (pip install packaging)"
        ) from e


def _version_satisfies(spec: str, lock_ver: str) -> bool:
    from packaging.requirements import Requirement

    req = Requirement(spec)
    if not req.specifier:
        return True
    return req.specifier.contains(lock_ver, prereleases=True)


def run_resolve(index: IndexKey, path: str | None = None) -> tuple[list[ResolveIssue], list[ResolveMeta]]:
    _require_packaging()
    pins = parse_pins(path or requirements_path())
    lock = lock_version_map(pins)
    issues: list[ResolveIssue] = []
    metas: list[ResolveMeta] = []

    for pin in unique_pins(pins):
        data = fetch_release_json(pin.name, pin.version, index)
        if not data:
            metas.append(
                ResolveMeta(
                    pin.name,
                    pin.version,
                    index,
                    [],
                    metadata_missing=True,
                )
            )
            continue
        rd = requires_dist_list(data)
        metas.append(ResolveMeta(pin.name, pin.version, index, rd))

        for spec in rd:
            if ";" in spec:
                req_part, _, marker = spec.partition(";")
                if not marker_applies(marker.strip()):
                    continue
                spec = req_part.strip()
            dep_name = _parse_req_name(spec)
            if not dep_name:
                continue
            norm = dep_name
            if norm not in lock:
                # Optional / test deps in metadata are not pinned in the lock.
                continue
            locked = lock[norm]
            if not _version_satisfies(spec, locked):
                issues.append(
                    ResolveIssue(
                        pin.name,
                        pin.version,
                        spec,
                        norm,
                        locked,
                        f"lock has {norm}=={locked}, need {spec}",
                        index,
                    )
                )

    return issues, metas


def resolve_to_json(
    issues: list[ResolveIssue], metas: list[ResolveMeta]
) -> str:
    return json.dumps(
        {
            "issues": [asdict(i) for i in issues],
            "metadata": [asdict(m) for m in metas],
        },
        indent=2,
    )
