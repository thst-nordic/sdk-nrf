#!/usr/bin/env python3
"""Verify every pin in requirements-fixed.txt is downloadable from Nordic PyPI."""

from __future__ import annotations

import argparse
import html.parser
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from pip._internal.models.target_python import TargetPython
from pip._vendor.packaging.utils import InvalidWheelFilename, parse_wheel_filename

DEFAULT_INDEX = "https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi/simple"
PYTHON_VERSION = (3, 12)

PLATFORMS = (
    "manylinux2014_x86_64",
    "win_amd64",
    "macosx_11_0_arm64",
)

PLATFORM_HINTS: dict[str, tuple[str, ...]] = {
    "manylinux2014_x86_64": (
        "manylinux2014_x86_64",
        "manylinux_2_17_x86_64",
        "manylinux_2_26_x86_64",
        "manylinux_2_27_x86_64",
        "manylinux_2_28_x86_64",
        "manylinux_2_5_x86_64",
        "linux_x86_64",
    ),
    "win_amd64": ("win_amd64", "win32"),
    "macosx_11_0_arm64": (
        "macosx_11_0_arm64",
        "macosx_10_9_universal2",
        "macosx_11_0_universal2",
    ),
}

PURE_PYTHON_TAGS = ("py3-none-any", "py2.py3-none-any")

REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.\-]*(?:\[[^\]]+\])?)==([^\s;]+)(?:\s*;\s*(.+))?$"
)
CPython_TAG_RE = re.compile(r"-cp(\d{2,3})-")

_target_python_cache: dict[str, set] = {}


def log(message: str) -> None:
    print(f"[validate-requirements-fixed] {message}", flush=True)


def platforms_for_marker(marker: str | None) -> tuple[str, ...]:
    if not marker:
        return PLATFORMS

    if 'platform_system == "Windows"' in marker or 'sys_platform == "win32"' in marker:
        return ("win_amd64",)

    return PLATFORMS


def parse_requirements(path: Path) -> list[tuple[str, str, str | None]]:
    entries: list[tuple[str, str, str | None]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--"):
            continue

        match = REQUIREMENT_RE.match(stripped)
        if not match:
            log(f"warning: skipping unparsable line: {stripped}")
            continue

        package = match.group(1)
        version = match.group(2)
        marker = match.group(3)
        entries.append((package, version, marker))

    return entries


def normalize_name(name: str) -> str:
    base = re.split(r"\[", name, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", base).lower()


def supported_tags(platform: str) -> set:
    if platform not in _target_python_cache:
        target = TargetPython(platforms=[platform], py_version_info=PYTHON_VERSION)
        _target_python_cache[platform] = set(target.get_unsorted_tags())
    return _target_python_cache[platform]


class _SimpleIndexParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.links.append(value)


def fetch_simple_index(index_url: str, package: str, cache: dict[str, list[str]]) -> list[str]:
    key = normalize_name(package)
    if key in cache:
        return cache[key]

    page_url = f"{index_url.rstrip('/')}/{key}/"
    request = Request(page_url, headers={"Accept": "application/vnd.pypi.simple.v1+html"})
    with urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8", errors="replace")

    parser = _SimpleIndexParser()
    parser.feed(body)
    cache[key] = parser.links
    return parser.links


def link_filename(href: str) -> str:
    path = urlparse(href.split("#", 1)[0]).path
    return path.rsplit("/", 1)[-1]


def absolute_link(index_page_url: str, href: str) -> str:
    return urljoin(index_page_url, href.split("#", 1)[0])


def wheel_matches(platform: str, filename: str) -> bool | None:
    """Return True/False when parsed; None if filename cannot be parsed."""
    try:
        _, _, _, wheel_tags = parse_wheel_filename(filename)
    except InvalidWheelFilename:
        return None

    tags = supported_tags(platform)
    return any(tag in tags for tag in wheel_tags)


def wheel_matches_fallback(platform: str, package: str, version: str, filename: str) -> bool:
    if not filename.endswith(".whl"):
        return False

    version_token = f"-{version}-"
    if version_token not in filename and not filename.endswith(f"-{version}.whl"):
        return False

    if not python_tag_compatible(filename):
        return False

    lowered = filename.lower()
    if any(tag in lowered for tag in PURE_PYTHON_TAGS):
        return True

    return any(hint in lowered for hint in PLATFORM_HINTS[platform])


def python_tag_compatible(filename: str) -> bool:
    lowered = filename.lower()
    if "abi3" in lowered or any(tag in lowered for tag in PURE_PYTHON_TAGS):
        return True

    match = CPython_TAG_RE.search(filename)
    if not match:
        return True

    expected = PYTHON_VERSION[0] * 100 + PYTHON_VERSION[1]
    return int(match.group(1)) == expected


def find_wheel_url(
    index_url: str,
    package: str,
    version: str,
    platform: str,
    cache: dict[str, list[str]],
) -> str | None:
    page_url = f"{index_url.rstrip('/')}/{normalize_name(package)}/"
    for href in fetch_simple_index(index_url, package, cache):
        filename = link_filename(href)
        if not filename.endswith(".whl"):
            continue

        parsed = wheel_matches(platform, filename)
        if parsed is True:
            _, wheel_version, _, _ = parse_wheel_filename(filename)
            if str(wheel_version) != version:
                continue
        elif not wheel_matches_fallback(platform, package, version, filename):
            continue

        return absolute_link(page_url, href)

    return None


def find_sdist_url(
    index_url: str,
    package: str,
    version: str,
    cache: dict[str, list[str]],
) -> str | None:
    page_url = f"{index_url.rstrip('/')}/{normalize_name(package)}/"
    version_marker = f"-{version}."
    sdist_suffixes = (".tar.gz", ".zip")
    for href in fetch_simple_index(index_url, package, cache):
        filename = link_filename(href)
        if not filename.endswith(sdist_suffixes):
            continue
        if version_marker not in filename:
            continue
        return absolute_link(page_url, href)

    return None


def head_check(url: str) -> tuple[bool, str]:
    request = Request(url, method="HEAD")
    try:
        with urlopen(request, timeout=60) as response:
            if 200 <= response.status < 300:
                return True, ""
            return False, f"HEAD {url} returned HTTP {response.status}"
    except HTTPError as exc:
        return False, f"HEAD {url} returned HTTP {exc.code}"
    except URLError as exc:
        return False, f"HEAD {url} failed: {exc.reason}"


def validate_spec_fast(
    package: str,
    version: str,
    platform: str,
    index_url: str,
    cache: dict[str, list[str]],
) -> str | None:
    wheel_url = find_wheel_url(index_url, package, version, platform, cache)
    if wheel_url:
        ok, detail = head_check(wheel_url)
        if ok:
            return None
        return detail or f"wheel not available: {wheel_url}"

    sdist_url = find_sdist_url(index_url, package, version, cache)
    if sdist_url:
        ok, detail = head_check(sdist_url)
        if ok:
            return None
        return detail or f"sdist not available: {sdist_url}"

    return (
        f"no wheel or sdist for {package}=={version} on {platform} "
        f"in {index_url}/{normalize_name(package)}/"
    )


def pip_download(
    spec: str,
    platform: str,
    index_url: str,
    dest: str,
    *,
    wheels_only: bool,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--no-deps",
        "--no-cache-dir",
        "--index-url",
        index_url,
        "--platform",
        platform,
        "--python-version",
        f"{PYTHON_VERSION[0]}.{PYTHON_VERSION[1]}",
        "--implementation",
        "cp",
        "-d",
        dest,
        spec,
    ]
    if wheels_only:
        command[4:4] = ["--only-binary=:all:"]

    env = os.environ.copy()
    env["PIP_CONFIG_FILE"] = "/dev/null"
    return subprocess.run(command, capture_output=True, text=True, env=env)


def validate_spec_full(
    spec: str,
    platform: str,
    index_url: str,
    dest: str,
) -> str | None:
    wheel_result = pip_download(spec, platform, index_url, dest, wheels_only=True)
    if wheel_result.returncode == 0:
        return None

    sdist_result = pip_download(spec, platform, index_url, dest, wheels_only=False)
    if sdist_result.returncode == 0:
        return None

    detail = (sdist_result.stderr or sdist_result.stdout or wheel_result.stderr).strip()
    return detail or "pip download failed"


def run_validation(
    entries: list[tuple[str, str, str | None]],
    index_url: str,
    *,
    fast: bool,
    report_all: bool,
) -> int:
    failures: list[tuple[str, str, str]] = []
    checks = 0
    total_checks = sum(len(platforms_for_marker(marker)) for _, _, marker in entries)
    mode = "fast (index+HEAD)" if fast else "full (pip download)"

    log(
        f"Validating {len(entries)} pins ({total_checks} platform checks, {mode}) "
        f"from {index_url}"
    )

    index_cache: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory(prefix="req-fixed-validate-") as dest:
        for package, version, marker in entries:
            spec = f"{package}=={version}"
            for platform in platforms_for_marker(marker):
                checks += 1
                if checks == 1 or checks % 25 == 0 or checks == total_checks:
                    log(f"progress: {checks}/{total_checks} checks")

                if fast:
                    error = validate_spec_fast(
                        package, version, platform, index_url, index_cache
                    )
                else:
                    error = validate_spec_full(spec, platform, index_url, dest)

                if error:
                    failures.append((platform, spec, error))
                    if not report_all:
                        log(f"FAILED: {spec} @ {platform}")
                        print(f"\n--- {spec} @ {platform} ---", file=sys.stderr)
                        print(error, file=sys.stderr)
                        return 1

    if failures:
        log(f"FAILED: {len(failures)} of {checks} platform checks did not pass")
        for platform, spec, error in failures:
            print(f"\n--- {spec} @ {platform} ---", file=sys.stderr)
            print(error, file=sys.stderr)
        return 1

    log(f"OK: all {checks} platform checks passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify requirements-fixed.txt pins are installable from Nordic PyPI."
    )
    parser.add_argument("requirements_file", type=Path)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="check simple index + HEAD only (no full wheel download)",
    )
    parser.add_argument(
        "--report-all",
        action="store_true",
        help="continue after failures and report all errors",
    )
    args = parser.parse_args()

    if not args.requirements_file.is_file():
        print(f"error: file not found: {args.requirements_file}", file=sys.stderr)
        return 2

    index_url = os.environ.get("NORDIC_PYPI_INDEX", DEFAULT_INDEX)
    entries = parse_requirements(args.requirements_file)
    if not entries:
        print("error: no package pins found to validate", file=sys.stderr)
        return 2

    return run_validation(entries, index_url, fast=args.fast, report_all=args.report_all)


if __name__ == "__main__":
    sys.exit(main())
