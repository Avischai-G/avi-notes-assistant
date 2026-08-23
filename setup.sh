#!/usr/bin/env bash
# Install local dependencies only. This script does not authenticate or deploy.
set -euo pipefail

python_bin="${PYTHON_BIN:-python3}"
"$python_bin" - <<'PY'
import sys

if sys.version_info < (3, 12):
    found = ".".join(str(part) for part in sys.version_info[:3])
    raise SystemExit(f"Python 3.12+ is required; {found} was selected")
PY
"$python_bin" -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-dev.txt
npm_config_cache="$PWD/.npm-cache" npm ci --ignore-scripts

echo "Local dependencies installed."
echo "Run: USE_FIRESTORE=0 TASK_STORE_MODE=fake ./.venv/bin/uvicorn server:api --host 127.0.0.1 --port 8000"
