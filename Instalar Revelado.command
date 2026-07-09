#!/bin/bash
# Instalador de Revelado — doble clic en el Finder.
cd "$(dirname "$0")"
# Con doble clic el PATH no trae Homebrew ni python.org; ampliarlo aquí
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
echo "════════════════════════════════════"
echo "   Instalador de Revelado (v1)"
echo "════════════════════════════════════"

PY="$(bash scripts/find-python.sh)" || {
  echo "Se necesita Python 3.10 o superior (instálalo desde python.org)"; exit 1; }
echo "Python encontrado: $PY ($("$PY" -V))"

if ! command -v exiftool >/dev/null; then
  if command -v brew >/dev/null; then
    echo "Instalando exiftool…"; brew install exiftool
  else
    echo "❌ Falta Homebrew (necesario para exiftool)."
    echo "   Instálalo desde https://brew.sh y vuelve a ejecutar este instalador."
    read -p "Enter para cerrar…"; exit 1
  fi
fi

echo "Preparando el entorno (puede tardar unos minutos la primera vez)…"
bash scripts/setup.sh

if [ ! -f .env ]; then
  echo ""
  echo "Clave de API de Anthropic (console.anthropic.com → API Keys)."
  echo "Sin clave, la app funciona en modo solo-local (sin decisión estética de la IA)."
  read -p "Pega tu clave (o Enter para omitir): " KEY
  if [ -n "$KEY" ]; then echo "ANTHROPIC_API_KEY=$KEY" > .env; echo "Clave guardada en .env"; fi
fi

bash scripts/make-app.sh
echo ""
echo "✅ Instalación completa."
echo "   → Abre 'Revelado.app' con doble clic (arrástrala al Dock si quieres)."
echo "   → La página se abrirá sola en tu navegador."
read -p "Enter para cerrar…"
