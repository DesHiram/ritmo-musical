#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p dist

BUNDLE_NAME="ritmo-musical-raspberry.tar.gz"
BUNDLE_PATH="dist/$BUNDLE_NAME"

tar \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude="venv" \
  --exclude="build" \
  --exclude="dist" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude="saved_songs.json" \
  --exclude="saved_songs.*.json" \
  -czf "$BUNDLE_PATH" \
  .

echo "Paquete creado: $BUNDLE_PATH"
echo
echo "En la Raspberry:"
echo "  mkdir -p ~/ritmo-musical"
echo "  tar -xzf $BUNDLE_NAME -C ~/ritmo-musical"
echo "  cd ~/ritmo-musical"
echo "  chmod +x scripts/*.sh"
echo "  ./scripts/setup_raspberry.sh"
echo "  ./scripts/run_raspberry.sh"
