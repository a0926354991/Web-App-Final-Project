# artifacts/

NemoClaw Multi-Agent Verification Gate writes its run logs here:

- `build-gate.log` — output of `scripts/run-build-gate.sh`
- `agent-report-check.log` — output of `scripts/verify-agent-report.py`
- `react-diff-check.log` — output of `scripts/validate-react-diff.py`

These logs are overwritten on every gate run; keep copies elsewhere if
you need a permanent audit trail.
