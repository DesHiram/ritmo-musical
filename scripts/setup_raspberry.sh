#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f "main.py" || ! -d "rhythm" ]]; then
  echo "Error: ejecuta este script dentro del proyecto ritmo-musical."
  exit 1
fi

echo "Instalando dependencias de sistema para Raspberry Pi OS / Debian..."
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip python3-tk zenity ffmpeg \
  build-essential python3-dev pkg-config \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  libfreetype6-dev libportmidi-dev libsndfile1

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
echo "  ./scripts/run_raspberry.sh"
