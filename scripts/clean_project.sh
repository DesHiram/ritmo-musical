#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

rm -rf \
  .venv \
  venv \
  dist \
  build \
  __pycache__ \
  rhythm/__pycache__ \
  .pytest_cache \
  .mypy_cache

rm -f saved_songs.json saved_songs.*.json

find . -path "./.git" -prune -o -name "*.pyc" -type f -delete

echo "Proyecto limpio."
