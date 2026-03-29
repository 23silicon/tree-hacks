#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PYTHON_VENV="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON_VENV}/bin/python"
PIP_BIN="${PYTHON_VENV}/bin/pip"

cd "${ROOT_DIR}"

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

next_free_port() {
  local port="$1"
  while port_in_use "${port}"; do
    port="$((port + 1))"
  done
  printf '%s\n' "${port}"
}

cleanup() {
  local exit_code=$?

  if [[ -n "${API_PID:-}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi

  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
  exit "${exit_code}"
}

trap cleanup INT TERM EXIT

echo "==> Repo root: ${ROOT_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "==> Creating shared Python virtual environment"
  python3 -m venv "${PYTHON_VENV}"
fi

if [[ ! -f "${PYTHON_VENV}/.deps-installed" ]] || [[ requirements.shared.txt -nt "${PYTHON_VENV}/.deps-installed" ]]; then
  echo "==> Installing shared Python dependencies"
  "${PIP_BIN}" install -r requirements.shared.txt
  touch "${PYTHON_VENV}/.deps-installed"
fi

if [[ ! -d "${ROOT_DIR}/node_modules" ]]; then
  echo "==> Installing frontend dependencies"
  npm install
fi

REQUESTED_API_PORT="${API_PORT}"
REQUESTED_FRONTEND_PORT="${FRONTEND_PORT}"
API_PORT="$(next_free_port "${API_PORT}")"
FRONTEND_PORT="$(next_free_port "${FRONTEND_PORT}")"

if [[ "${API_PORT}" != "${REQUESTED_API_PORT}" ]]; then
  echo "==> Port ${REQUESTED_API_PORT} is busy, using API port ${API_PORT} instead"
fi

if [[ "${FRONTEND_PORT}" != "${REQUESTED_FRONTEND_PORT}" ]]; then
  echo "==> Port ${REQUESTED_FRONTEND_PORT} is busy, using frontend port ${FRONTEND_PORT} instead"
fi

echo "==> Starting API on http://127.0.0.1:${API_PORT}"
"${PYTHON_VENV}/bin/uvicorn" main:app --app-dir api --host 127.0.0.1 --port "${API_PORT}" --reload &
API_PID=$!

echo "==> Starting frontend on http://127.0.0.1:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/frontend"
  API_PORT="${API_PORT}" \
  VITE_API_PROXY_TARGET="http://127.0.0.1:${API_PORT}" \
  npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!

echo
echo "API:      http://127.0.0.1:${API_PORT}"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "Press Ctrl+C to stop both."
echo

wait "${API_PID}" "${FRONTEND_PID}"
