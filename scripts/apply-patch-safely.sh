#!/usr/bin/env bash
# NemoClaw Multi-Agent Verification Gate
# apply-patch-safely.sh — apply a patch to a sandbox copy of the working
# tree, run the build gate there, and only mirror changes back to the
# real working tree if the gate passes.
#
# Usage:
#   scripts/apply-patch-safely.sh <patch-file>
#
# Exit codes:
#   0  patch applied + build gate passed + mirrored back
#   1  patch did not apply, or build gate failed (working tree untouched)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ "${#:-0}" -lt 1 ]; then
  echo "usage: $0 <patch-file>" >&2
  exit 1
fi

PATCH_PATH="$1"
if [ ! -f "${PATCH_PATH}" ]; then
  echo "[FAIL] Patch file not found: ${PATCH_PATH}" >&2
  exit 1
fi

# Resolve patch path to absolute before we leave the cwd.
PATCH_PATH="$(cd "$(dirname "${PATCH_PATH}")" && pwd)/$(basename "${PATCH_PATH}")"

SANDBOX="$(mktemp -d -t nemoclaw-sandbox.XXXXXX)"
echo "[info] sandbox: ${SANDBOX}"

cleanup() {
  rm -rf "${SANDBOX}"
}
trap cleanup EXIT

# Copy working tree into sandbox. Exclude heavy / regenerable dirs.
rsync -a \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude 'artifacts' \
  "${REPO_ROOT}/" "${SANDBOX}/"

cd "${SANDBOX}"

echo "[info] applying patch in sandbox"
if ! git init -q 2>/dev/null; then
  echo "[FAIL] could not init git in sandbox" >&2
  exit 1
fi
git add -A >/dev/null
git -c user.email=sandbox@local -c user.name=sandbox commit -q -m "sandbox baseline" || true

if ! git apply --check "${PATCH_PATH}" 2>/tmp/nemoclaw-patch-err; then
  echo "[FAIL] patch does not apply cleanly:" >&2
  cat /tmp/nemoclaw-patch-err >&2
  exit 1
fi
git apply "${PATCH_PATH}"

echo "[info] running build gate in sandbox"
mkdir -p "${SANDBOX}/artifacts"
if ! bash "${SANDBOX}/scripts/run-build-gate.sh"; then
  echo "[FAIL] build gate failed in sandbox; working tree NOT modified." >&2
  echo "       see ${SANDBOX}/artifacts/build-gate.log (sandbox is cleaned up on exit)" >&2
  cp "${SANDBOX}/artifacts/build-gate.log" "${REPO_ROOT}/artifacts/build-gate.sandbox.log" 2>/dev/null || true
  exit 1
fi

echo "[info] sandbox passed; mirroring changes back to working tree"
rsync -a --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude 'artifacts' \
  "${SANDBOX}/" "${REPO_ROOT}/"

echo "[PASS] patch applied safely."
