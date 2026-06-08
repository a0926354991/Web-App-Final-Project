#!/usr/bin/env python3
"""NemoClaw Multi-Agent Verification Gate — validate-react-diff.py

Scans the current git diff for high-risk React patterns and other risky
changes. Exits 1 if any high-risk issue is found, 0 otherwise.

Checks:
  1. useEffect dependency array referencing a state setter's own state
     (likely infinite loop).
  2. Multiple fetch() of the same URL inside the same component file.
  3. New props declared in a component but never referenced.
  4. Nested <Link> ... <Link> ... </Link> </Link>.
  5. Modifications to package.json.

Only Python standard library is used.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts"
LOG_FILE = ARTIFACT_DIR / "react-diff-check.log"

JSX_EXTS = (".jsx", ".tsx", ".js", ".ts")


def run_git(args: list[str]) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout


def changed_files() -> list[str]:
    """Return list of files changed vs HEAD (staged + unstaged + untracked)."""
    out = run_git(["status", "--porcelain"])
    files: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # rename "old -> new"
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def full_diff() -> str:
    # combined staged + unstaged + new files
    parts = [run_git(["diff", "HEAD"])]
    # include untracked file content as added lines
    for f in changed_files():
        full = REPO_ROOT / f
        if (REPO_ROOT / f).is_file():
            try:
                content = (REPO_ROOT / f).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if f.endswith(JSX_EXTS) or f.endswith(".json"):
                parts.append(f"\n+++ untracked-or-current {f}\n")
                for ln in content.splitlines():
                    parts.append("+" + ln + "\n")
    return "".join(parts)


def file_added_lines(diff: str) -> dict[str, list[str]]:
    """Map file path -> list of added lines (lines starting with '+')."""
    by_file: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    for line in diff.splitlines():
        m = re.match(r"^\+\+\+ (?:b/)?(.+)$", line)
        if m:
            current = m.group(1).strip()
            continue
        m = re.match(r"^\+\+\+ untracked-or-current (.+)$", line)
        if m:
            current = m.group(1).strip()
            continue
        if current and line.startswith("+") and not line.startswith("+++"):
            by_file[current].append(line[1:])
    return by_file


# ---------- individual checks ------------------------------------------------

def check_useeffect_deps(file: str, lines: list[str]) -> list[str]:
    """Flag useEffect blocks whose dep array contains a state updated by a
    setState call inside the same block."""
    if not file.endswith(JSX_EXTS):
        return []
    blob = "\n".join(lines)
    findings: list[str] = []
    for m in re.finditer(
        r"useEffect\s*\(\s*\(\s*\)\s*=>\s*\{(?P<body>.*?)\}\s*,\s*\[(?P<deps>[^\]]*)\]\s*\)",
        blob,
        re.DOTALL,
    ):
        body = m.group("body")
        deps = [d.strip() for d in m.group("deps").split(",") if d.strip()]
        setters = re.findall(r"\bset([A-Z][A-Za-z0-9_]*)\s*\(", body)
        for setter in setters:
            state = setter[0].lower() + setter[1:]
            if state in deps:
                findings.append(
                    f"{file}: useEffect deps include `{state}` while body calls "
                    f"`set{setter}(...)` — likely infinite loop"
                )
    return findings


def check_duplicate_fetch(file: str, lines: list[str]) -> list[str]:
    if not file.endswith(JSX_EXTS):
        return []
    urls: dict[str, int] = defaultdict(int)
    for ln in lines:
        for m in re.finditer(r"""fetch\s*\(\s*['"`]([^'"`]+)['"`]""", ln):
            urls[m.group(1)] += 1
    findings = []
    for url, count in urls.items():
        if count > 1:
            findings.append(f"{file}: fetch('{url}') appears {count} times in added lines")
    return findings


def check_unused_props(file: str, lines: list[str]) -> list[str]:
    if not file.endswith(JSX_EXTS):
        return []
    blob = "\n".join(lines)
    findings: list[str] = []
    # destructured props: function Foo({ a, b, c }) { ... }
    for m in re.finditer(
        r"function\s+([A-Z][A-Za-z0-9_]*)\s*\(\s*\{\s*([^}]+)\}\s*\)\s*\{",
        blob,
    ):
        comp = m.group(1)
        props = [p.strip().split(":")[0].split("=")[0].strip()
                 for p in m.group(2).split(",") if p.strip()]
        # naive scope: look in the rest of blob
        rest = blob[m.end():]
        for p in props:
            if not p or p.startswith("..."):
                continue
            if not re.search(r"\b" + re.escape(p) + r"\b", rest):
                findings.append(f"{file}: component <{comp}/> declares prop `{p}` but never uses it")
    return findings


def check_nested_link(file: str, lines: list[str]) -> list[str]:
    if not file.endswith(JSX_EXTS):
        return []
    blob = "\n".join(lines)
    findings: list[str] = []
    # crude: a <Link ...> ... <Link ...> ... </Link> ... </Link> pattern
    if re.search(r"<Link\b[^>]*>[^<]*<Link\b", blob, re.DOTALL):
        findings.append(f"{file}: nested <Link> inside <Link> detected (invalid DOM)")
    return findings


def _clean(path: str) -> str:
    # strip the synthetic prefix our diff builder uses for untracked files
    return path.replace("untracked-or-current ", "")


def check_package_json(by_file: dict[str, list[str]]) -> list[str]:
    findings = []
    for path in by_file:
        clean = _clean(path)
        if clean.endswith("package.json") or clean.endswith("package-lock.json"):
            findings.append(f"{clean}: modified — review whether a new dependency was added")
    return findings


# ---------- driver -----------------------------------------------------------

def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        diff = full_diff()
    except RuntimeError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    by_file = file_added_lines(diff)
    all_findings: list[str] = []

    for path, lines in by_file.items():
        clean = _clean(path)
        all_findings += check_useeffect_deps(clean, lines)
        all_findings += check_duplicate_fetch(clean, lines)
        all_findings += check_unused_props(clean, lines)
        all_findings += check_nested_link(clean, lines)
    all_findings += check_package_json(by_file)

    with LOG_FILE.open("w", encoding="utf-8") as f:
        f.write(f"validate-react-diff.py @ {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"files scanned: {len(by_file)}\n\n")
        if all_findings:
            f.write("HIGH-RISK FINDINGS:\n")
            for fl in all_findings:
                f.write(f"  - {fl}\n")
        else:
            f.write("Result: PASS — no high-risk patterns detected.\n")

    if all_findings:
        print(f"[FAIL] {len(all_findings)} high-risk finding(s):", file=sys.stderr)
        for fl in all_findings:
            print(f"  - {fl}", file=sys.stderr)
        print(f"\nLog: {LOG_FILE}", file=sys.stderr)
        return 1

    if not by_file:
        print("[PASS] No changed files detected; nothing to scan.")
    else:
        print(f"[PASS] Scanned {len(by_file)} file(s); no high-risk patterns found.")
    print(f"Log: {LOG_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
