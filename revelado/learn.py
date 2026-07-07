"""Aprender el estilo del fotógrafo desde XMP que él ya editó.

Lee los sidecars de sesiones editadas a mano (en Lightroom: Metadatos →
Guardar metadatos en archivos), junta las tendencias de los ajustes y la IA
las convierte en frases de estilo que se guardan en un bloque marcado de
estilo.txt. Los XMP generados por Revelado se ignoran: se aprende de las
ediciones del fotógrafo, no de las nuestras.
"""
import json
import re
from pathlib import Path
from statistics import median, quantiles

from revelado.ai import AIUnavailable
from revelado.config import SETTINGS

_OWN_MARK = 'x:xmptk="revelado"'
_NUMERIC_KEYS = ("Exposure2012", "Contrast2012", "Highlights2012", "Shadows2012",
                 "Whites2012", "Blacks2012", "Clarity2012", "Texture",
                 "Vibrance", "Saturation", "Temperature", "Tint")
_ATTR_RE = re.compile(r'crs:(\w+)="([^"]*)"')
_ELEM_RE = re.compile(r"<crs:(\w+)>([^<]*)</crs:\1>")

_MARK_START = "# === Estilo aprendido de tus ediciones (generado automáticamente; edítalo o bórralo) ==="
_MARK_END = "# === Fin del estilo aprendido ==="

_SUMMARY_SYSTEM = (
    "Eres el asistente de un fotógrafo de retratos. Recibes estadísticas de los "
    "ajustes de revelado que él aplicó a mano en Lightroom (medianas y cuartiles "
    "por ajuste, en unidades de Lightroom). Convierte esas tendencias en sus "
    "preferencias de estilo: de 3 a 6 líneas en español, una preferencia por "
    "línea, en lenguaje natural e imperativo (como instrucciones para un editor), "
    "sin números salvo que una tendencia sea muy marcada. Ignora ajustes con "
    "valores cercanos a cero o sin tendencia clara. Responde SOLO con las líneas, "
    "sin títulos ni viñetas."
)


def read_xmp_settings(path: Path) -> dict | None:
    """Ajustes crs de un XMP editado; None si no es utilizable (o es nuestro)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if _OWN_MARK in text or "crs:" not in text:
        return None
    values: dict[str, float | str] = {}
    for key, raw in _ATTR_RE.findall(text) + _ELEM_RE.findall(text):
        if key in _NUMERIC_KEYS:
            try:
                values[key] = float(raw)
            except ValueError:
                pass
        elif key == "WhiteBalance":
            values[key] = raw
    return values or None


def collect_stats(folder: Path) -> dict:
    """Tendencias de todos los XMP editados bajo la carpeta (recursivo)."""
    parsed = [v for v in (read_xmp_settings(p) for p in sorted(folder.rglob("*.xmp")))
              if v]
    sliders: dict[str, dict] = {}
    for key in _NUMERIC_KEYS:
        data = [v[key] for v in parsed if key in v]
        if not data:
            continue
        p25, p75 = (quantiles(data, n=4)[0], quantiles(data, n=4)[2]) \
            if len(data) > 1 else (data[0], data[0])
        sliders[key] = {"mediana": round(median(data), 2),
                        "p25": round(p25, 2), "p75": round(p75, 2),
                        "fotos": len(data)}
    wb: dict[str, int] = {}
    for v in parsed:
        name = str(v.get("WhiteBalance", "As Shot"))
        wb[name] = wb.get(name, 0) + 1
    return {"count": len(parsed), "sliders": sliders, "balance_blancos": wb}


def summarize_style(client, stats: dict) -> str:
    """La IA convierte las estadísticas en frases de estilo (texto plano)."""
    try:
        response = client.messages.create(
            model=SETTINGS.model,
            max_tokens=500,
            system=_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content":
                       "Estadísticas de mis ediciones:\n"
                       + json.dumps(stats, ensure_ascii=False)}],
        )
        if response.stop_reason == "refusal":
            raise AIUnavailable("La API rechazó la petición")
        text = next(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise AIUnavailable("Respuesta vacía")
        return text
    except AIUnavailable:
        raise
    except Exception as exc:
        raise AIUnavailable(str(exc)) from exc


def apply_learned_style(text: str, path: Path | None = None) -> Path:
    """Escribe (o reemplaza) el bloque aprendido en estilo.txt, sin tocar el resto."""
    path = path or SETTINGS.style_path
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    start = current.find(_MARK_START)
    end = current.find(_MARK_END)
    if start != -1 and end != -1:
        current = current[:start] + current[end + len(_MARK_END):].lstrip("\n")
    current = current.rstrip("\n")
    block = f"{_MARK_START}\n{text.strip()}\n{_MARK_END}\n"
    path.write_text((current + "\n\n" + block) if current else block,
                    encoding="utf-8")
    return path
