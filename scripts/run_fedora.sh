#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "No existe .venv. Primero ejecuta:"
  echo "  ./scripts/setup_fedora.sh"
  exit 1
fi

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "No hay entorno grafico activo. Abre una terminal desde tu sesion de escritorio."
  exit 1
fi

source .venv/bin/activate
export IMAGEIO_FFMPEG_EXE="${IMAGEIO_FFMPEG_EXE:-/usr/bin/ffmpeg}"

python main.py
