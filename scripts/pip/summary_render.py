"""Merge validation artifacts into GitHub Step Summary markdown."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _artifact_file(root: Path, *candidates: str) -> Path:
    for name in candidates:
        p = root / name
        if p.is_file():
            return p
    return root / candidates[0]


def render_summary(artifact_root: Path, job_results: dict[str, str]) -> str:
    lines: list[str] = ["# requirements-fixed.txt validation", ""]
    fix: list[str] = []

    for job, result in sorted(job_results.items()):
        icon = "pass" if result == "success" else "FAIL"
        lines.append(f"- **{job}**: {icon}")
    lines.append("")

    audit_txt = _read_text(_artifact_file(artifact_root, "audit.txt", "audit/audit.txt"))
    if audit_txt:
        lines.append("## pip-audit")
        lines.append("```")
        lines.append(audit_txt[:8000])
        lines.append("```")
        lines.append("")
        if "Vulnerability" in audit_txt or "Found" in audit_txt:
            fix.append("pip-audit: review vulnerabilities (see audit.txt)")

    cons_txt = _read_text(
        _artifact_file(artifact_root, "consistency.txt", "consistency/consistency.txt")
    )
    if cons_txt:
        lines.append("## Consistency")
        lines.append("```")
        lines.append(cons_txt)
        lines.append("```")
        lines.append("")
        if job_results.get("consistency") == "failure":
            fix.extend(f"consistency: {ln}" for ln in cons_txt.splitlines() if ln.strip())

    for idx in ("nordic", "pypi"):
        data = _read_json(
            _artifact_file(
                artifact_root,
                f"resolve-{idx}.json",
                f"resolve-{idx}/resolve-{idx}.json",
            )
        )
        if not data:
            continue
        lines.append(f"## Resolve ({idx})")
        issues = data.get("issues") or []
        if not issues:
            lines.append("No dependency conflicts.")
        else:
            for iss in issues:
                msg = (
                    f"{iss.get('from_package')}=={iss.get('from_version')}: "
                    f"{iss.get('message')}"
                )
                lines.append(f"- {msg}")
                fix.append(f"resolve-{idx}: {msg}")
        lines.append("")

    drift = _metadata_drift(artifact_root)
    if drift:
        lines.append("## Metadata drift (Nordic vs PyPI requires_dist)")
        for d in drift:
            lines.append(f"- {d}")
            fix.append(f"metadata drift: {d}")
        lines.append("")

    for os_key in ("linux", "windows", "mac_arm"):
        data = _read_json(
            _artifact_file(
                artifact_root,
                f"wheels-{os_key}.json",
                f"wheels-{os_key}/wheels-{os_key}.json",
            )
        )
        if not data:
            continue
        fails = [r for r in data if r.get("status") != "ok_nordic"]
        if not fails:
            continue
        lines.append(f"## Wheels ({os_key})")
        lines.append("| Package | Status | Nordic | PyPI | Sdist | Action |")
        lines.append("|---------|--------|--------|------|-------|--------|")
        for r in fails:
            pkg = f"{r.get('package')}=={r.get('version')}"
            lines.append(
                f"| {pkg} | {r.get('status')} | {r.get('nordic_wheel')} | "
                f"{r.get('pypi_wheel')} | {r.get('sdist')} | {r.get('action')} |"
            )
            fix.append(f"wheels-{os_key}: {pkg} — {r.get('action')}")
        lines.append("")

    lines.append("## Things to fix")
    if fix:
        for item in fix[:200]:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")

    return "\n".join(lines)


def _metadata_drift(artifact_root: Path) -> list[str]:
    n = _read_json(
        _artifact_file(artifact_root, "resolve-nordic.json", "resolve-nordic/resolve-nordic.json")
    )
    p = _read_json(
        _artifact_file(artifact_root, "resolve-pypi.json", "resolve-pypi/resolve-pypi.json")
    )
    if not n or not p:
        return []
    nmap = {
        (m["package"], m["version"]): sorted(m.get("requires_dist") or [])
        for m in n.get("metadata") or []
        if not m.get("metadata_missing")
    }
    pmap = {
        (m["package"], m["version"]): sorted(m.get("requires_dist") or [])
        for m in p.get("metadata") or []
        if not m.get("metadata_missing")
    }
    out: list[str] = []
    for key in set(nmap) & set(pmap):
        if nmap[key] != pmap[key]:
            out.append(f"{key[0]}=={key[1]} requires_dist differs Nordic vs PyPI")
    return out


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    results: dict[str, str] = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            results[k] = v
    md = render_summary(root, results)
    print(md)
    failed = any(v == "failure" for v in results.values())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
