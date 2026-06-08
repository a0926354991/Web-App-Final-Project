# NemoClaw Multi-Agent Verification Rules

These rules apply to every Agent (PM / Engineer / QA / Reviewer) that
operates on this repo. They exist to stop agents from fabricating
"success" results and to keep React-style changes from silently
introducing race conditions, infinite loops or unbuilt code.

---

## 1. No PASS without command output

An agent **must NOT** claim any of the following without attaching the
literal terminal output that proves it:

| Claim                       | Required evidence                             |
| --------------------------- | --------------------------------------------- |
| `build PASS` / `build OK`   | output of `npm run build` (or equivalent)     |
| `test PASS` / `tests OK`    | output of `npm test` (or `pytest` etc.)       |
| `QA PASS`                   | output that matches the QA tier (see §3)      |
| `commit 成功` / `committed` | output of `git log -1` showing the commit     |
| `diff attached`             | actual `git diff` body in the report          |

If the agent skipped the command, it must explicitly write `NOT RUN`
instead of `PASS`. `scripts/verify-agent-report.py` will fail any
report that violates this rule.

## 2. Build blocked by environment

If `npm install` / `npm run build` cannot run because of the local
environment (no node, network blocked, missing native lib …), the agent
must mark the build as:

```
BUILD BLOCKED BY ENVIRONMENT
```

and explain *why*. It must **not** report this as `BUILD PASS`. This
sentinel is the only acceptable "non-pass / non-fail" state.

## 3. Three QA tiers

QA in this repo has three distinct levels. Agents must label which
tier(s) they performed:

1. **BUILD-LEVEL QA** — `npm run build` + `npm test` succeed.
2. **BROWSER-LEVEL QA** — actually loaded the page, exercised the
   golden path, and (preferably) captured a screenshot.
3. **CODE-LEVEL CHECK** — read the diff and reasoned about correctness
   (no execution).

A `QA PASS` claim without naming at least one tier is rejected.

## 4. Commit hashes come from `git log`

Any commit hash cited in a report must come from `git log --oneline`
output included in the same report. Hashes pasted from memory, chat,
or fabricated are forbidden.

## 5. Final reports must include git evidence

A final report **must** include all of:

- `git status`
- `git branch`
- `git log --oneline -5`
- `git diff --stat`
- `git diff` (full body or path-scoped, but not "...")

This is what `scripts/verify-agent-report.py` enforces when it sees a
`Final Report` heading.

## 6. React-style diff hygiene

Before declaring a React/JSX change "done", the agent runs
`scripts/validate-react-diff.py` and pastes its output. The script
flags:

- `useEffect` whose dependency array contains state updated by a
  `setState` call inside the same effect (infinite loop)
- Duplicate `fetch()` of the same URL inside one component
- New props declared but never used
- `<Link>` nested inside `<Link>`
- Modifications to `package.json` (manual review required)

A non-zero exit from this script blocks the final report.

## 7. Patches go through the sandbox first

Risky multi-file patches should be applied via
`scripts/apply-patch-safely.sh`, which copies the working tree to a
sandbox, runs the build gate there, and only mirrors the changes back
on success. See that script's `--help` for usage.

## 8. The report template is mandatory

All final reports must follow `docs/agent-final-report-template.md`.
The verifier is tuned to recognise this layout — deviations are likely
to be flagged.
