#!/usr/bin/env bash
# Encuentra un Python >= 3.10 aunque el PATH no lo traiga (los .command de
# doble clic corren sin el perfil del usuario, así que python.org y Homebrew
# quedan fuera del PATH). Imprime la ruta del intérprete; sale con 1 si no hay.
set -u

_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; }

CANDIDATOS=(
  "${REVELADO_PYTHON:-}"
  "$(command -v python3 2>/dev/null || true)"
  "${HOME}/.pyenv/shims/python3"
)
# Instalaciones de python.org (la más nueva primero) y Homebrew
while IFS= read -r p; do CANDIDATOS+=("$p"); done < <(
  ls -1 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 2>/dev/null | sort -rV
)
CANDIDATOS+=(/opt/homebrew/bin/python3 /usr/local/bin/python3)

VISTOS=""
for py in "${CANDIDATOS[@]}"; do
  [ -n "$py" ] && [ -x "$py" ] || continue
  if _ok "$py"; then echo "$py"; exit 0; fi
  VISTOS="$VISTOS
   - $py => $("$py" -V 2>&1 | head -1)"
done

echo "No se encontró Python 3.10 o superior. Intérpretes revisados:$VISTOS" >&2
exit 1
