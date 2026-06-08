# Agent Final Report — &lt;short title&gt;

> Fill every section. Sections that don't apply must say `N/A` with a
> one-line reason. PASS without command output will be rejected by
> `scripts/verify-agent-report.py`.

## 1. Summary

- Goal:
- Outcome (one of): `PASS` / `FAIL` / `BUILD BLOCKED BY ENVIRONMENT`
- QA tier(s) performed (one or more):
  - [ ] BUILD-LEVEL QA
  - [ ] BROWSER-LEVEL QA
  - [ ] CODE-LEVEL CHECK

## 2. Files changed

List each file with a one-line reason.

- `path/to/file` — reason

## 3. Git evidence

### git status
```
<paste output of `git status`>
```

### git branch
```
<paste output of `git branch --show-current` and `git branch`>
```

### git log --oneline -5
```
<paste output>
```

### git diff --stat
```
<paste output>
```

### git diff
```diff
<paste full diff or, for very large diffs, paste per-file diffs that
together cover every changed file>
```

## 4. Build / test evidence

### npm install
```
<paste output, or write "NOT RUN — node_modules already present">
```

### npm run build
```
<paste output, or write "BUILD BLOCKED BY ENVIRONMENT — <reason>">
```

### npm test
```
<paste output, or write "NOT RUN — no test script in package.json">
```

## 5. React diff hygiene

```
<paste full output of `python3 scripts/validate-react-diff.py`>
```

## 6. Browser-level QA (if performed)

- URL(s) opened:
- Steps performed (golden path + at least one edge case):
- Observations:
- Screenshot(s) (path under `artifacts/` or attached):

## 7. Risks / follow-ups

- Known limitations:
- Anything an agent in the next turn should double-check:

## 8. Sign-off

- Agent name / role:
- Commit hash (must appear in §3 `git log`):
- Date (ISO 8601):
