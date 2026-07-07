"""Presets de sesión: brief + sesgos guardados con nombre.

Se persisten en `presets.json` en la raíz del proyecto, así viajan con la
carpeta al copiarla a otro equipo. Un archivo ausente o corrupto equivale a
no tener presets.
"""
import json
from pathlib import Path

from revelado.config import SETTINGS


def _load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        presets = data.get("presets", [])
        return [p for p in presets if isinstance(p, dict) and p.get("name")]
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _dump(path: Path, presets: list[dict]) -> None:
    path.write_text(json.dumps({"presets": presets}, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def list_presets(path: Path | None = None) -> list[dict]:
    presets = _load(path or SETTINGS.presets_path)
    return sorted(presets, key=lambda p: str(p["name"]).lower())


def save_preset(name: str, prompt: str = "", exposure_bias: float = 0.0,
                temp_bias: int = 0, path: Path | None = None) -> dict:
    """Guarda (o reemplaza, por nombre) un preset y lo devuelve."""
    path = path or SETTINGS.presets_path
    name = name.strip()
    if not name:
        raise ValueError("El preset necesita un nombre")
    preset = {"name": name, "prompt": prompt.strip(),
              "exposure_bias": round(float(exposure_bias), 2),
              "temp_bias": int(temp_bias)}
    presets = [p for p in _load(path) if p["name"] != name]
    presets.append(preset)
    _dump(path, presets)
    return preset


def delete_preset(name: str, path: Path | None = None) -> bool:
    path = path or SETTINGS.presets_path
    presets = _load(path)
    remaining = [p for p in presets if p["name"] != name]
    if len(remaining) == len(presets):
        return False
    _dump(path, remaining)
    return True
