#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f "main.py" || ! -d "rhythm" ]]; then
  echo "Error: ejecuta este script dentro del proyecto ritmo-musical."
  exit 1
fi

echo "Instalando dependencias de sistema para Fedora..."
sudo dnf install -y \
  python3 python3-pip python3-tkinter ffmpeg \
  gcc gcc-c++ make pkgconf-pkg-config python3-devel \
  SDL2-devel SDL2_image-devel SDL2_mixer-devel SDL2_ttf-devel \
  freetype-devel portmidi-devel libsndfile-devel

echo "Creando entorno virtual..."
python3 -m venv .venv
source .venv/bin/activate

echo "Instalando dependencias de Python..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo "Verificando archivos del proyecto..."
python -m py_compile \
  main.py \
  rhythm/__init__.py \
  rhythm/app.py \
  rhythm/audio.py \
  rhythm/constants.py \
  rhythm/library.py \
  rhythm/models.py \
  rhythm/rendering.py

echo
echo "Listo. Para correr el juego:"
echo "  ./scripts/run_fedora.sh"
