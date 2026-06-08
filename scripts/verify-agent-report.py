#!/usr/bin/env python3
"""NemoClaw Multi-Agent Verification Gate — verify-agent-report.py

Reads an agent report Markdown file and verifies that every PASS / success
claim is backed by the corresponding command output. Exits 1 when an
unsupported claim is found, 0 otherwise.

Usage:
    python3 scripts/verify-agent-report.py <report.md>

If no path is given, the script looks for the most recently modified
*.md file under reports/ or artifacts/.

Only Python standard library is used.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts"
LOG_FILE = ARTIFACT_DIR / "agent-report-check.log"

# Each rule: (claim regex, list of evidence regex alternatives).
# A claim only "passes" if at least one evidence pattern is also present
# anywhere in the report.
RULES = [
    # Git evidence — required if the report claims a commit / branch state.
    ("commit_status", r"\b(commit\s*成功|commit\s+ok|commit\s+pass|已\s*commit|committed)\b",
     [r"git\s+log", r"\bcommit\s+[0-9a-f]{7,40}\b"]),
    ("branch_status", r"\b(branch\s*正確|branch\s+ok|on\s+branch)\b",
     [r"git\s+branch", r"git\s+status"]),
    ("diff_claimed", r"\b(diff\s*已附|附上\s*diff|diff\s+attached)\b",
     [r"git\s+diff", r"^---\s.*\n\+\+\+", r"^diff --git "]),

    # Build / test / install evidence — required if the report claims PASS.
    ("build_pass", r"\b(build\s*pass|build\s+ok|build\s*成功|建置\s*成功)\b",
     [r"npm\s+run\s+build", r"webpack", r"vite\s+build", r"tsc\b", r"BUILD\s+BLOCKED\s+BY\s+ENVIRONMENT"]),
    ("test_pass", r"\b(test\s*pass|tests?\s+ok|測試\s*成功|all\s+tests?\s+pass)\b",
     [r"npm\s+test", r"jest\b", r"vitest\b", r"pytest\b", r"\bPASS\s+.+\.(spec|test)\.(js|ts|tsx|jsx)"]),
    ("install_done", r"\b(install\s*完成|install\s+ok|dependencies?\s+installed)\b",
     [r"npm\s+install", r"yarn\s+install", r"pnpm\s+install", r"added\s+\d+\s+packages?"]),
    ("qa_pass", r"\bQA\s*(pass|ok|成功)\b",
     [r"npm\s+run\s+build", r"npm\s+test", r"BROWSER-LEVEL\s+QA", r"CODE-LEVEL\s+CHECK", r"BUILD-LEVEL\s+QA"]),
]

# Hard requirement: any "final report" must include these sections somewhere.
FINAL_REPORT_REQUIRED = [
    ("git status",  r"git\s+status"),
    ("git branch",  r"git\s+branch"),
    ("git log",     r"git\s+log\s+--oneline"),
    ("git diff --stat", r"git\s+diff\s+--stat"),
    ("git diff",    r"git\s+diff(?!\s+--stat)"),
]

FINAL_MARKER = re.compile(r"final\s+report|最終\s*報告|## *Final", re.IGNORECASE)


def find_default_report() -> Path | None:
    candidates: list[Path] = []
    for sub in ("reports", "artifacts", "docs/agent-reports"):
        d = REPO_ROOT / sub
        if d.is_dir():
            candidates.extend(d.rglob("*.md"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def check(report_path: Path) -> int:
    text = report_path.read_text(encoding="utf-8", errors="replace")
    failures: list[str] = []
    notes: list[str] = []

    for rule_id, claim_re, evidence_res in RULES:
        if re.search(claim_re, text, re.IGNORECASE):
            if not any(re.search(ev, text, re.IGNORECASE | re.MULTILINE) for ev in evidence_res):
                failures.append(
                    f"[{rule_id}] report claims success matching /{claim_re}/ "
                    f"but no evidence pattern present "
                    f"({', '.join('/' + e + '/' for e in evidence_res)})"
                )
            else:
                notes.append(f"[{rule_id}] claim + evidence both present.")

    if FINAL_MARKER.search(text):
        for label, pat in FINAL_REPORT_REQUIRED:
            if not re.search(pat, text, re.IGNORECASE):
                failures.append(f"[final-report] missing required section: {label}")

    # Write log
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("w", encoding="utf-8") as f:
        f.write(f"verify-agent-report.py @ {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"report: {report_path}\n\n")
        if notes:
            f.write("Evidence found:\n")
            for n in notes:
                f.write(f"  - {n}\n")
        f.write("\n")
        if failures:
            f.write("FAILURES:\n")
            for fl in failures:
                f.write(f"  - {fl}\n")
        else:
            f.write("Result: PASS\n")

    if failures:
        print(f"[FAIL] {len(failures)} issue(s) in {report_path}:", file=sys.stderr)
        for fl in failures:
            print(f"  - {fl}", file=sys.stderr)
        print(f"\nLog: {LOG_FILE}", file=sys.stderr)
        return 1
    print(f"[PASS] {report_path} — all claims supported by command output.")
    print(f"Log: {LOG_FILE}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        report = Path(argv[1])
        if not report.is_absolute():
            report = (Path.cwd() / report).resolve()
    else:
        report = find_default_report()
        if report is None:
            print("[FAIL] No report path given and no *.md found under reports/ or artifacts/.",
                  file=sys.stderr)
            print("Usage: python3 scripts/verify-agent-report.py <report.md>", file=sys.stderr)
            return 1
        print(f"[info] auto-selected most recent report: {report}")
    if not report.is_file():
        print(f"[FAIL] Report file does not exist: {report}", file=sys.stderr)
        return 1
    return check(report)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
