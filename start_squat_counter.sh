#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
    echo "需要Python 3.11+。Debian 13可安装：sudo apt install python3 python3-venv"
    exit 1
fi
venv_dir="${SQUAT_COUNTER_VENV:-$project_dir/.venv-squat}"
if [[ ! -x "$venv_dir/bin/python" ]]; then
    python3 -m venv "$venv_dir" || { echo "请先安装python3-venv后重试。"; exit 1; }
fi
if ! cmp -s requirements-squat.txt "$venv_dir/.squat-requirements"; then
    "$venv_dir/bin/python" -m pip install --disable-pip-version-check -r requirements-squat.txt
    cp requirements-squat.txt "$venv_dir/.squat-requirements"
fi
"$venv_dir/bin/python" scripts/download_squat_assets.py
export PYTHONDONTWRITEBYTECODE=1
exec "$venv_dir/bin/python" -B -m streamlit run squat_counter_app.py \
    --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false "$@"
