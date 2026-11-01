"""Nordic → PyPI → sdist wheel checks per OS."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urljoin

from lockfile import (
    PYTHON_TAG,
    unique_pins,
    parse_pins,
    requirements_path,
    skip_marker_for_os,
)
from wheels_exceptions import skip_wheel_check_for_os

OsKey = Literal["linux", "windows", "mac_arm"]

INDEX_URL = os.environ.get(
    "INDEX_URL",
    "https://files.nordicsemi.com/artifactory/api/pypi/nordic-pypi/simple",
).rstrip("/") + "/"
PYPI_SIMPLE = os.environ.get(
    "PYPI_SIMPLE_URL", "https://pypi.org/simple/"
).rstrip("/") + "/"


def compatible_python(fn: str) -> bool:
    if "py3-none-any" in fn:
        return True
    if re.search(r"py[23](?:\.py3)?-none-(manylinux|linux|win_|macosx)", fn):
        return True
    if f"-{PYTHON_TAG}-" in fn:
        return True
    if "-abi3-" in fn and ("manylinux" in fn or "win_" in fn or "macosx" in fn):
        return True
    return False


def has_linux_wheel(wheels: list[str]) -> bool:
    for fn in wheels:
        if not compatible_python(fn):
            continue
        if "py3-none-any" in fn:
            return True
        if "manylinux" in fn and "x86_64" in fn:
            return True
        if f"-{PYTHON_TAG}-" in fn and "linux_x86_64" in fn:
            return True
    return False


def has_windows_wheel(wheels: list[str]) -> bool:
    for fn in wheels:
        if not compatible_python(fn):
            continue
        if "py3-none-any" in fn:
            return True
        if "win_amd64" in fn:
            return True
    return False


def has_mac_arm_wheel(wheels: list[str]) -> bool:
    for fn in wheels:
        if not compatible_python(fn):
            continue
        if "py3-none-any" in fn:
            return True
        if "universal2" in fn and "macosx" in fn:
            return True
        if "macosx" in fn and "arm64" in fn:
            return True
    return False


OS_CHECK = {
    "linux": has_linux_wheel,
    "windows": has_windows_wheel,
    "mac_arm": has_mac_arm_wheel,
}


def http_status(url: str, method: str = "GET") -> int:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if method == "GET":
                resp.read()
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def fetch_simple(url: str) -> str:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read().decode("utf-8", "replace")


def wheels_for_version(body: str, ver: str) -> list[str]:
    href_pat = re.compile(r'href=["\']([^"\']+\.whl)(?:#[^"\']*)?["\']', re.I)
    ver_needle = f"-{ver}-"
    out: list[str] = []
    for m in href_pat.finditer(body):
        fn = m.group(1).split("/")[-1].split("#")[0]
        if ver_needle in fn:
            out.append(fn)
    return out


def sdist_on_simple(body: str, ver: str) -> bool:
    pat = re.compile(r'href=["\']([^"\']+\.tar\.gz)(?:#[^"\']*)?["\']', re.I)
    needle = f"-{ver}.tar.gz"
    for m in pat.finditer(body):
        fn = m.group(1).split("/")[-1].split("#")[0]
        if fn.endswith(needle) or needle in fn:
            return True
    return False


def pypi_has_sdist(name: str, ver: str) -> bool:
    url = f"https://pypi.org/pypi/{name}/{ver}/json"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return False
    for item in data.get("urls", []):
        if item.get("packagetype") == "sdist":
            return True
    return False


def pick_wheel_for_os(wheels: list[str], os_key: OsKey) -> str | None:
    check = OS_CHECK[os_key]
    for fn in wheels:
        if check([fn]):
            return fn
    return None


@dataclass
class WheelRow:
    package: str
    version: str
    os: str
    status: str
    nordic_wheel: bool
    pypi_wheel: bool
    sdist: str
    action: str
    wheel_file: str | None = None


def check_pin_os(name: str, ver: str, os_key: OsKey) -> WheelRow:
    simple_names = [name, name.replace("-", "_"), name.replace("_", "-")]
    nordic_wheels: list[str] = []
    nordic_body = ""
    nordic_simple_url = ""
    for slug in simple_names:
        url = INDEX_URL + slug + "/"
        try:
            nordic_body = fetch_simple(url)
            nordic_wheels = wheels_for_version(nordic_body, ver)
            if nordic_wheels:
                nordic_simple_url = url
                break
        except urllib.error.HTTPError:
            continue

    pypi_wheels: list[str] = []
    pypi_body = ""
    for slug in simple_names:
        url = PYPI_SIMPLE + slug + "/"
        try:
            pypi_body = fetch_simple(url)
            pypi_wheels = wheels_for_version(pypi_body, ver)
            if pypi_wheels:
                break
        except urllib.error.HTTPError:
            continue

    check = OS_CHECK[os_key]
    nordic_ok = check(nordic_wheels)
    pypi_ok = check(pypi_wheels)

    if nordic_ok:
        fn = pick_wheel_for_os(nordic_wheels, os_key)
        if fn and nordic_body:
            hm = re.search(
                r'href=["\']([^"\']*' + re.escape(fn) + r'(?:#[^"\']*)?)["\']',
                nordic_body,
                re.I,
            )
            if hm:
                href = hm.group(1).split("#")[0]
                base = nordic_simple_url or (INDEX_URL + name + "/")
                wheel_url = href if href.startswith("http") else urljoin(base, href)
                st = http_status(wheel_url, "HEAD")
                if st not in (200, 302, 303, 307, 308, 405):
                    return WheelRow(
                        name,
                        ver,
                        os_key,
                        "nordic_wheel_404",
                        True,
                        pypi_ok,
                        "none",
                        f"wheel HTTP {st} on Nordic ({fn})",
                        fn,
                    )
        return WheelRow(
            name,
            ver,
            os_key,
            "ok_nordic",
            True,
            pypi_ok,
            "n/a",
            "",
            fn,
        )

    if pypi_ok:
        fn = pick_wheel_for_os(pypi_wheels, os_key)
        return WheelRow(
            name,
            ver,
            os_key,
            "mirror_gap",
            False,
            True,
            "none",
            "pip_requestor: PyPI has wheel, Nordic missing",
            fn,
        )

    sdist_n = sdist_on_simple(nordic_body, ver) if nordic_body else False
    sdist_p = sdist_on_simple(pypi_body, ver) if pypi_body else False
    if not sdist_p:
        sdist_p = pypi_has_sdist(name, ver)
    if sdist_n or sdist_p:
        where = []
        if sdist_n:
            where.append("nordic")
        if sdist_p:
            where.append("pypi")
        return WheelRow(
            name,
            ver,
            os_key,
            "sdist_only",
            False,
            False,
            "+".join(where),
            "sdist only; mirror wheel or adjust pin",
            None,
        )

    return WheelRow(
        name,
        ver,
        os_key,
        "no_artifact",
        False,
        False,
        "none",
        "no wheel or sdist on Nordic or PyPI",
        None,
    )


def run_wheels(os_key: OsKey, path: str | None = None) -> list[WheelRow]:
    pins = parse_pins(path or requirements_path())
    rows: list[WheelRow] = []
    for pin in unique_pins(pins):
        if skip_marker_for_os(pin.marker, os_key):
            continue
        if skip_wheel_check_for_os(pin.name, os_key):
            continue
        rows.append(check_pin_os(pin.name, pin.version, os_key))
    return rows


def wheels_to_json(rows: list[WheelRow]) -> str:
    return json.dumps([asdict(r) for r in rows], indent=2)
