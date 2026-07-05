#!/usr/bin/env bash
# Construye Revelado.app (doble clic, sin Terminal) dentro de la carpeta del proyecto.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP="$ROOT/Revelado.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Revelado</string>
  <key>CFBundleDisplayName</key><string>Revelado</string>
  <key>CFBundleIdentifier</key><string>local.revelado.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>revelado</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/revelado" <<LAUNCH
#!/bin/bash
cd "$ROOT"
mkdir -p "\$HOME/.cache/revelado"
if /usr/sbin/lsof -ti :8420 >/dev/null 2>&1; then
  open "http://localhost:8420"   # ya está corriendo: solo abrir la página
  exit 0
fi
nohup ./.venv/bin/python run.py >> "\$HOME/.cache/revelado/app.log" 2>&1 &
LAUNCH

chmod +x "$APP/Contents/MacOS/revelado"
echo "Creada $APP — ábrela con doble clic (puedes arrastrarla al Dock)."
