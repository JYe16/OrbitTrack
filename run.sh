#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${CALDAV_ENV_NAME:-caldav-gtk}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v conda >/dev/null 2>&1; then
  echo "Error: conda command not found in PATH." >&2
  exit 1
fi

if ! conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  echo "Error: conda environment '$ENV_NAME' not found." >&2
  echo "Create it first, or set CALDAV_ENV_NAME to an existing env." >&2
  exit 1
fi

cd "$PROJECT_DIR"
exec conda run -n "$ENV_NAME" python -m orbittrack.main "$@"
