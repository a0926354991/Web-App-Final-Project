#!/usr/bin/env bash
# NemoClaw Multi-Agent Verification Gate
# run-build-gate.sh — unified npm install / build / test runner.
#
# Exit codes:
#   0  build gate passed (or N/A: no package.json found)
#   1  build gate failed (install / build / test error)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARTIFACT_DIR="${REPO_ROOT}/artifacts"
LOG_FILE="${ARTIFACT_DIR}/build-gate.log"

mkdir -p "${ARTIFACT_DIR}"
: > "${LOG_FILE}"

log() {
  printf '%s\n' "$*" | tee -a "${LOG_FILE}"
}

run_step() {
  local label="$1"; shift
  log ""
  log "=== ${label} ==="
  log "\$ $*"
  if ! "$@" >>"${LOG_FILE}" 2>&1; then
    log ""
    log "[FAIL] ${label} failed. See ${LOG_FILE}"
    exit 1
  fi
  log "[OK] ${label}"
}

log "NemoClaw Build Gate"
log "Repo: ${REPO_ROOT}"
log "Date: $(date '+%Y-%m-%d %H:%M:%S')"

# Find a directory that has a package.json (root or frontend/)
PKG_DIR=""
for candidate in "${REPO_ROOT}" "${REPO_ROOT}/frontend"; do
  if [ -f "${candidate}/package.json" ]; then
    PKG_DIR="${candidate}"
    break
  fi
done

if [ -z "${PKG_DIR}" ]; then
  log ""
  log "[SKIP] No package.json found in repo root or frontend/."
  log "       This project has no JS build pipeline."
  log "       Build gate marked: BUILD BLOCKED BY ENVIRONMENT (no JS project)."
  exit 0
fi

log "Using package.json in: ${PKG_DIR}"

# Tooling versions
log ""
log "=== Tooling ==="
if ! command -v node >/dev/null 2>&1; then
  log "[FAIL] node not installed. Build gate cannot run."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  log "[FAIL] npm not installed. Build gate cannot run."
  exit 1
fi
log "node: $(node -v)"
log "npm:  $(npm -v)"

cd "${PKG_DIR}"

# Install dependencies if missing
if [ ! -d "node_modules" ]; then
  run_step "npm install" npm install
else
  log ""
  log "[SKIP] node_modules exists; skipping npm install."
fi

# Build (only if a build script is declared)
if node -e "process.exit(require('./package.json').scripts && require('./package.json').scripts.build ? 0 : 1)" 2>/dev/null; then
  run_step "npm run build" npm run build
else
  log ""
  log "[SKIP] No 'build' script in package.json."
  log "       Build gate marked: BUILD BLOCKED BY ENVIRONMENT (no JS build target)."
fi

# Test (only if a test script is declared)
if node -e "process.exit(require('./package.json').scripts && require('./package.json').scripts.test ? 0 : 1)" 2>/dev/null; then
  run_step "npm test" npm test -- --watchAll=false
else
  log ""
  log "[SKIP] No 'test' script in package.json; skipping npm test."
fi

log ""
log "[PASS] Build gate completed successfully."
exit 0
