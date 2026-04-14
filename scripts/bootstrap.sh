#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR/backend"
python3 -m venv .venv
source .venv/bin/activate
pip install -i https://pypi.org/simple -r requirements.txt -r requirements-dev.txt

cd "$ROOT_DIR/frontend"
npm install

echo "Bootstrap complete."
