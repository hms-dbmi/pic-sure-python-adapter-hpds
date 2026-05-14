#!/usr/bin/env bash
# Container entrypoint:
#   1. Sync project dependencies into /opt/venv on first run, or when
#      pyproject.toml / uv.lock changed since the last sync.
#   2. Exec the requested command (bash for `dev`, jupyter for `notebook`).

set -euo pipefail

VENV_DIR="${UV_PROJECT_ENVIRONMENT:-/opt/venv}"
STAMP="${VENV_DIR}/.sync-stamp"
LOCK="/workspace/uv.lock"
PROJECT="/workspace/pyproject.toml"

needs_sync() {
    [ ! -f "${VENV_DIR}/pyvenv.cfg" ] && return 0
    [ ! -f "${STAMP}" ] && return 0
    [ "${PROJECT}" -nt "${STAMP}" ] && return 0
    [ -f "${LOCK}" ] && [ "${LOCK}" -nt "${STAMP}" ] && return 0
    return 1
}

if needs_sync; then
    echo "==> uv sync (installing project + dev/docs/notebook groups)"
    cd /workspace
    uv sync --all-extras --group dev --group docs --group notebook
    touch "${STAMP}"
fi

exec "$@"
