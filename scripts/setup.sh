#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Se necesita Python 3.10 o superior"; exit 1
fi

if ! command -v exiftool >/dev/null; then
  echo "Instalando exiftool con Homebrew..."
  brew install exiftool
fi

if [ ! -d .venv ]; then python3 -m venv .venv; fi
./.venv/bin/pip install -q -r requirements.txt

mkdir -p models
MODEL=models/face_detection_yunet_2023mar.onnx
if [ ! -f "$MODEL" ]; then
  echo "Descargando modelo de detección de caras (YuNet)..."
  curl -fsSL -o "$MODEL" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi

echo "Listo. Ejecuta: ./.venv/bin/python run.py"
