#!/usr/bin/env python3
"""Validate committed requirements-fixed.txt (audit, consistency, resolve, wheels)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from audit_whitelist import ignore_vuln_args, whitelist_path  # noqa: E402
from consistency import run_consistency  # noqa: E402
from lockfile import requirements_path  # noqa: E402
from resolve_index import resolve_to_json, run_resolve  # noqa: E402
from wheels_index import run_wheels, wheels_to_json  # noqa: E402


def _results_dir() -> Path:
    d = Path(os.environ.get("RESULTS_DIR", "results"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_audit(args: argparse.Namespace) -> int:
    req = args.requirements_file or requirements_path()
    out = _results_dir()
    audit_log = out / "audit.txt"
    wl = getattr(args, "whitelist_file", None) or whitelist_path()
    cmd = [
        "pip-audit",
        "--strict",
        "-r",
        req,
        *ignore_vuln_args(wl),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = (proc.stdout or "") + (proc.stderr or "")
    audit_log.write_text(text, encoding="utf-8")
    print(text)
    return proc.returncode


def cmd_consistency(args: argparse.Namespace) -> int:
    path = args.requirements_file or requirements_path()
    issues = run_consistency(path)
    out = _results_dir() / "consistency.txt"
    if issues:
        lines = [f"line {i.line_no}: {i.message}" for i in issues]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for ln in lines:
            print(f"FAIL: {ln}")
        return 1
    out.write_text("SUCCESS: consistency check passed\n", encoding="utf-8")
    print("SUCCESS: consistency")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    path = args.requirements_file or requirements_path()
    index = args.index
    issues, metas = run_resolve(index, path)
    out = _results_dir()
    json_path = out / f"resolve-{index}.json"
    txt_path = out / f"resolve-{index}.txt"
    json_path.write_text(resolve_to_json(issues, metas), encoding="utf-8")
    txt_lines = []
    for iss in issues:
        txt_lines.append(
            f"FAIL: {iss.from_package}=={iss.from_version} — {iss.message} ({iss.requirement})"
        )
    if not txt_lines:
        txt_lines.append(f"SUCCESS: resolve-{index} no conflicts")
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    for ln in txt_lines:
        print(ln)
    return 1 if issues else 0


def cmd_wheels(args: argparse.Namespace) -> int:
    path = args.requirements_file or requirements_path()
    rows = run_wheels(args.os, path)
    out = _results_dir()
    json_path = out / f"wheels-{args.os}.json"
    txt_path = out / f"wheels-{args.os}.txt"
    json_path.write_text(wheels_to_json(rows), encoding="utf-8")
    fails = [r for r in rows if r.status != "ok_nordic"]
    txt_lines = []
    for r in fails:
        txt_lines.append(
            f"FAIL: {r.package}=={r.version} — missing OS: {r.os} — {r.action} "
            f"(status={r.status})"
        )
    if not txt_lines:
        txt_lines.append(f"SUCCESS: wheels-{args.os}")
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    for ln in txt_lines:
        print(ln)
    return 1 if fails else 0


def cmd_summary(args: argparse.Namespace) -> int:
    from summary_render import render_summary

    root = Path(args.artifact_dir)
    results: dict[str, str] = {}
    for spec in args.job_result or []:
        if "=" in spec:
            k, v = spec.split("=", 1)
            results[k] = v
    md = render_summary(root, results)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(md)
    else:
        print(md)
    failed = any(v == "failure" for v in results.values())
    return 1 if failed else 0


def _add_requirements_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--requirements-file",
        help="Path to lock file (default: ../requirements-fixed.txt)",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate requirements-fixed.txt")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit")
    _add_requirements_arg(p_audit)

    p_cons = sub.add_parser("consistency")
    _add_requirements_arg(p_cons)

    p_res = sub.add_parser("resolve")
    _add_requirements_arg(p_res)
    p_res.add_argument(
        "--index",
        choices=("nordic", "pypi"),
        required=True,
    )

    p_w = sub.add_parser("wheels")
    _add_requirements_arg(p_w)
    p_w.add_argument(
        "--os",
        choices=("linux", "windows", "mac_arm"),
        required=True,
    )

    p_sum = sub.add_parser("summary")
    p_sum.add_argument("artifact_dir", nargs="?", default="artifacts")
    p_sum.add_argument(
        "job_result",
        nargs="*",
        help="job=success|failure pairs",
    )

    args = parser.parse_args()
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "consistency":
        return cmd_consistency(args)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "wheels":
        return cmd_wheels(args)
    if args.command == "summary":
        return cmd_summary(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
