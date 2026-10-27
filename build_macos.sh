#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${RECORTA_PYTHON:-python3}"
if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python tools/make_icon.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/gui_smoke.py
.venv/bin/python tests/organizer_smoke.py
PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache" .venv/bin/python -m PyInstaller \
  --noconfirm --clean --windowed --name Recorta \
  --icon assets/Recorta.icns --osx-bundle-identifier local.recorta.desktop \
  --collect-all pillow_heif app.py
echo "Aplicación creada en: $PWD/dist/Recorta.app"

