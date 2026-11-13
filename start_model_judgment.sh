#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"

if ! command -v python3 >/dev/null 2>&1; then
    echo "需要 Python 3.11 或更新版本。Debian 13 可运行：sudo apt install python3 python3-venv"
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "需要 Python 3.11 或更新版本；请使用 Debian 13 自带的 Python 3。"
    exit 1
fi

venv_dir="${MODEL_JUDGMENT_VENV:-$project_dir/.venv-judgment}"
if [[ ! -x "$venv_dir/bin/python" ]]; then
    if ! python3 -m venv "$venv_dir"; then
        echo "无法创建虚拟环境。Debian 13 请先运行：sudo apt install python3-venv，然后重试。"
        exit 1
    fi
fi
if ! cmp -s requirements-judgment.txt "$venv_dir/.model-judgment-requirements"; then
    echo "首次启动或依赖清单已更新，正在安装页面依赖，需要联网……"
    "$venv_dir/bin/python" -m pip install --disable-pip-version-check -r requirements-judgment.txt
    cp requirements-judgment.txt "$venv_dir/.model-judgment-requirements"
fi

echo "默认浏览器地址为 http://localhost:8501；若指定其他端口，请以日志URL为准。按 Ctrl+C 停止。"
export PYTHONDONTWRITEBYTECODE=1
exec "$venv_dir/bin/python" -B -m streamlit run model_judgment_app.py \
    --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false "$@"
