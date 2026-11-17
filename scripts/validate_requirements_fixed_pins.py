#!/usr/bin/env python3
"""HTTP-only validation of requirements-fixed.txt pins (no pip compile/install).

Checks bdist_wheel availability for cp312 on marker-aware OS targets (linux,
windows, mac_arm). Nordic index: simple page + optional HEAD. PyPI: release JSON.
matter-idl is checked on Nordic only (not public PyPI).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

NORDIC_SIMPLE_DEFAULT = (
    "https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi/simple/"
)
PYPI_JSON_TEMPLATE = "https://pypi.org/pypi/{name}/{version}/json"

# Not on public PyPI; validated on Nordic mirror only.
PYPI_SKIP_NAMES = frozenset({"matter-idl", "py-utlx"})

OS_ALL = ("linux", "windows", "mac_arm")


@dataclass(frozen=True)
class Pin:
    name: str
    version: str
    os_required: frozenset[str]
    line_no: int


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def required_oses(marker: str) -> frozenset[str]:
    if not marker.strip():
        return frozenset(OS_ALL)
    m = marker.strip()
    if 'sys_platform == "win32"' in m or 'platform_system == "Windows"' in m:
        return frozenset({"windows"})
    if "platform_system != " in m and '"Linux"' in m:
        return frozenset({"windows", "mac_arm"})
    return frozenset(OS_ALL)


def parse_lockfile(path: str) -> tuple[list[Pin], list[str]]:
    pins: list[Pin] = []
    parse_errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    spec_re = re.compile(
        r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)(?:\[[^\]]+\])?==(.+)$"
    )
    with open(path, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("--"):
                continue
            req, _, marker = line.partition(";")
            req = req.strip()
            m = spec_re.match(req)
            if not m:
                parse_errors.append(f"line {line_no}: unparsed {raw.strip()!r}")
                continue
            name = normalize_name(m.group(1))
            version = m.group(2).strip()
            key = (name, version)
            if key in seen:
                continue
            seen.add(key)
            pins.append(
                Pin(
                    name=name,
                    version=version,
                    os_required=required_oses(marker),
                    line_no=line_no,
                )
            )
    return pins, parse_errors


def compatible_python(fn: str, python_tag: str) -> bool:
    if "py3-none-any" in fn or "py2.py3-none-any" in fn:
        return True
    if re.search(r"py[23](?:\.py3)?-none-(manylinux|linux|win_|macosx)", fn):
        return True
    if f"-{python_tag}-" in fn:
        return True
    if "-abi3-" in fn and ("manylinux" in fn or "win_" in fn or "macosx" in fn):
        return True
    return False


def is_universal_wheel(fn: str) -> bool:
    return "py3-none-any" in fn or "py2.py3-none-any" in fn


def os_for_wheel_filename(fn: str) -> str | None:
    if is_universal_wheel(fn):
        return None
    if "manylinux" in fn and "x86_64" in fn:
        return "linux"
    if re.search(r"cp\d+-cp\d+-linux_x86_64", fn):
        return "linux"
    if "win_amd64" in fn:
        return "windows"
    if "macosx" in fn and ("arm64" in fn or "universal2" in fn):
        return "mac_arm"
    return None


def has_linux_wheel(wheels: Iterable[str], python_tag: str) -> bool:
    for fn in wheels:
        if not compatible_python(fn, python_tag):
            continue
        if is_universal_wheel(fn):
            return True
        if "manylinux" in fn and "x86_64" in fn:
            return True
        if re.search(r"cp\d+-cp\d+-linux_x86_64", fn):
            return True
    return False


def has_windows_wheel(wheels: Iterable[str], python_tag: str) -> bool:
    for fn in wheels:
        if not compatible_python(fn, python_tag):
            continue
        if is_universal_wheel(fn):
            return True
        if "win_amd64" in fn:
            return True
    return False


def has_mac_arm_wheel(wheels: Iterable[str], python_tag: str) -> bool:
    for fn in wheels:
        if not compatible_python(fn, python_tag):
            continue
        if is_universal_wheel(fn):
            return True
        if "universal2" in fn and "macosx" in fn:
            return True
        if "macosx" in fn and "arm64" in fn:
            return True
    return False


OS_WHEEL_FN = {
    "linux": has_linux_wheel,
    "windows": has_windows_wheel,
    "mac_arm": has_mac_arm_wheel,
}


def http_status(url: str, method: str = "GET", timeout: int = 120) -> int:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if method == "GET":
                resp.read()
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def wheel_filename(href: str) -> str:
    return href.split("/")[-1].split("#")[0]


def wheels_for_version_from_simple(body: str, ver: str) -> list[str]:
    href_pat = re.compile(r'href=["\']([^"\']+\.whl)(?:#[^"\']*)?["\']', re.I)
    ver_needle = f"-{ver}-"
    out: list[str] = []
    for m in href_pat.finditer(body):
        fn = wheel_filename(m.group(1))
        if ver_needle in fn:
            out.append(fn)
    return out


def wheels_for_version_from_pypi_json(data: dict) -> list[str]:
    out: list[str] = []
    for entry in data.get("urls") or []:
        if entry.get("packagetype") != "bdist_wheel":
            continue
        fn = entry.get("filename")
        if fn and fn.endswith(".whl"):
            out.append(fn)
    return out


def absent_os_for_pin(
    wheels: list[str], os_required: frozenset[str], python_tag: str
) -> list[str]:
    absent = []
    for os_key in OS_ALL:
        if os_key not in os_required:
            continue
        if not OS_WHEEL_FN[os_key](wheels, python_tag):
            absent.append(os_key)
    return absent


def check_nordic_pin(
    pin: Pin, index_url: str, python_tag: str
) -> list[str]:
    failures: list[str] = []
    simple_url = urljoin(index_url, pin.name + "/")
    st = http_status(simple_url, "GET")
    if st != 200:
        failures.append(f"{pin.name}=={pin.version} (simple index HTTP {st})")
        return failures
    with urllib.request.urlopen(simple_url, timeout=120) as resp:
        body = resp.read().decode("utf-8", "replace")
    wheels = wheels_for_version_from_simple(body, pin.version)
    if not wheels:
        failures.append(f"{pin.name}=={pin.version} (no wheels on simple index)")
        return failures
    absent = absent_os_for_pin(wheels, pin.os_required, python_tag)
    if absent:
        failures.append(
            f"{pin.name}=={pin.version} — missing OS: {', '.join(absent)} ({python_tag})"
        )
        return failures
    checked_os: set[str] = set()
    for fn in wheels:
        if not compatible_python(fn, python_tag):
            continue
        os_key = os_for_wheel_filename(fn)
        if not os_key or os_key in checked_os or os_key not in pin.os_required:
            continue
        if not OS_WHEEL_FN[os_key]([fn], python_tag):
            continue
        checked_os.add(os_key)
        hm = re.search(
            r'href=["\']([^"\']*' + re.escape(fn) + r'(?:#[^"\']*)?)["\']',
            body,
            re.I,
        )
        if not hm:
            failures.append(
                f"{pin.name}=={pin.version} — wheel link not found ({os_key}: {fn})"
            )
            continue
        href = hm.group(1)
        wheel_url = href if href.startswith("http") else urljoin(simple_url, href)
        wstatus = http_status(wheel_url, "HEAD")
        if wstatus not in (200, 302, 303, 307, 308, 405):
            failures.append(
                f"{pin.name}=={pin.version} — wheel HTTP {wstatus} on {os_key} ({fn})"
            )
    return failures


def check_pypi_pin(pin: Pin, python_tag: str) -> list[str]:
    failures: list[str] = []
    url = PYPI_JSON_TEMPLATE.format(name=pin.name, version=pin.version)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        failures.append(f"{pin.name}=={pin.version} (PyPI HTTP {e.code})")
        return failures
    except OSError as e:
        failures.append(f"{pin.name}=={pin.version} ({e})")
        return failures
    wheels = wheels_for_version_from_pypi_json(data)
    if not wheels:
        failures.append(f"{pin.name}=={pin.version} (sdist only / no wheels on PyPI)")
        return failures
    absent = absent_os_for_pin(wheels, pin.os_required, python_tag)
    if absent:
        failures.append(
            f"{pin.name}=={pin.version} — missing OS: {', '.join(absent)} ({python_tag})"
        )
    return failures


def shard_pins(pins: list[Pin], shard_count: int, shard_id: int) -> list[Pin]:
    if shard_count <= 1:
        return pins
    ordered = sorted(pins, key=lambda p: (p.name, p.version))
    return [p for i, p in enumerate(ordered) if i % shard_count == shard_id]


def check_pin(
    pin: Pin, index: str, index_url: str, python_tag: str
) -> list[str]:
    if index == "pypi" and pin.name in PYPI_SKIP_NAMES:
        return []
    if index == "nordic":
        return check_nordic_pin(pin, index_url, python_tag)
    if index == "pypi":
        return check_pypi_pin(pin, python_tag)
    raise ValueError(f"unknown index {index!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        default="scripts/requirements-fixed.txt",
        help="Path to requirements-fixed.txt",
    )
    parser.add_argument(
        "--index",
        choices=("pypi", "nordic"),
        required=True,
    )
    parser.add_argument(
        "--index-url",
        default=NORDIC_SIMPLE_DEFAULT,
        help="Nordic simple index base (nordic index only)",
    )
    parser.add_argument("--python-tag", default="cp312")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-id", type=int, default=0)
    args = parser.parse_args()

    if args.shard_count < 1 or not 0 <= args.shard_id < args.shard_count:
        print("invalid shard-count / shard-id", file=sys.stderr)
        return 2

    index_url = args.index_url.rstrip("/") + "/"
    pins, parse_errors = parse_lockfile(args.requirements)
    failures: list[str] = list(parse_errors) if args.shard_id == 0 else []
    pins = shard_pins(pins, args.shard_count, args.shard_id)

    if parse_errors and args.shard_id != 0:
        return 0
    if parse_errors:
        for item in failures:
            print(f"FAIL: {item}")
        print(f"FAIL: parse errors in lockfile", file=sys.stderr)
        return 1

    checked = 0
    workers = max(1, args.workers)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(check_pin, pin, args.index, index_url, args.python_tag): pin
            for pin in pins
            if not (args.index == "pypi" and pin.name in PYPI_SKIP_NAMES)
        }
        for fut in as_completed(futures):
            pin = futures[fut]
            try:
                pin_failures = fut.result()
            except Exception as e:
                pin_failures = [f"{pin.name}=={pin.version} ({e})"]
            checked += 1
            for item in pin_failures:
                failures.append(item)

    for item in failures:
        print(f"FAIL: {item}")
    if failures:
        print(
            f"FAIL: {args.index} {len(failures)} issue(s), {checked} pin(s) in shard",
            file=sys.stderr,
        )
        return 1
    skip_note = ""
    if args.index == "pypi":
        skip_note = f" (skipped on PyPI: {', '.join(sorted(PYPI_SKIP_NAMES))})"
    print(
        f"SUCCESS: {args.index} {checked} pin(s) "
        f"(shard {args.shard_id + 1}/{args.shard_count}){skip_note}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())