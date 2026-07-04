#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

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
