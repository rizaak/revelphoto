import base64
import json
from dataclasses import dataclass, replace

from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics
from revelado.config import SETTINGS


class AIUnavailable(Exception):
    """La API de Claude no está disponible o devolvió una respuesta inválida."""


@dataclass(frozen=True)
class AIDecision:
    crop: tuple[float, float, float, float] | None
    angle: float
    exposure: float
    contrast: int
    highlights: int
    shadows: int
    temp_shift: int  # desviación en Kelvin respecto al WB de cámara (+ = más cálido)
    tint_shift: int  # desviación de tinte (+ = más magenta)
    face_lifts: tuple[tuple[int, float], ...] = ()  # (índice de cara, EV local)
    rating: int = 3          # puntuación de culling 1-5 (estrellas en Lightroom)
    rating_reason: str = ""  # motivo corto en español (vacío si no hay nada que señalar)


_CROP_PROPS = {k: {"type": "number"} for k in ("left", "top", "right", "bottom")}
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "crop": {"anyOf": [
            {"type": "object", "properties": _CROP_PROPS,
             "required": list(_CROP_PROPS), "additionalProperties": False},
            {"type": "null"},
        ]},
        "angle": {"type": "number"},
        "exposure": {"type": "number"},
        "contrast": {"type": "integer"},
        "highlights": {"type": "integer"},
        "shadows": {"type": "integer"},
        "temp_shift": {"type": "integer"},
        "tint_shift": {"type": "integer"},
        "face_lifts": {"type": "array", "items": {
            "type": "object",
            "properties": {"index": {"type": "integer"}, "ev": {"type": "number"}},
            "required": ["index", "ev"], "additionalProperties": False,
        }},
        "rating": {"type": "integer"},
        "rating_reason": {"type": "string"},
    },
    "required": ["crop", "angle", "exposure", "contrast", "highlights",
                 "shadows", "temp_shift", "tint_shift", "face_lifts",
                 "rating", "rating_reason"],
    "additionalProperties": False,
}

_SYSTEM = (
    "Eres un editor fotográfico profesional de retratos. Recibes la vista previa de una "
    "foto RAW y métricas técnicas medidas localmente. Devuelve ajustes de revelado para "
    "Lightroom en JSON.\n"
    "Color: el balance de blancos de cámara ('tal como se capturó') es tu punto de "
    "partida y suele ser correcto. Devuelve temp_shift (Kelvin, positivo = más cálido) y "
    "tint_shift (positivo = más magenta) como DESVIACIÓN respecto a él: 0 y 0 si el color "
    "de cámara ya funciona; corrige con decisión solo si ves una dominante o si el estilo "
    "del fotógrafo lo pide.\n"
    "Luz: exposición global conservadora (los rostros oscuros se corrigen aparte con "
    "máscaras locales, no subas la exposición global por ellos); usa contrast, highlights "
    "y shadows para un acabado profesional: piel luminosa y natural, altas luces "
    "controladas. Con las sombras sé decidido: si el sujeto o zonas importantes de la "
    "escena quedan hundidos en sombra, rescátalos con claridad (shadows puede llegar a "
    "+70 si la escena lo pide), siempre que el resultado siga siendo natural.\n"
    "Encuadre: recorta solo si mejora claramente la composición (regla de tercios, "
    "distracciones en bordes) y nunca cortes cabezas; crop en coordenadas normalizadas "
    "0-1 de la imagen completa, o null si el encuadre ya es bueno. Si por un borde se "
    "cuela un elemento ajeno a la escena (un brazo o persona a medias, un cono, un "
    "cartel, basura, cables), recorta para dejarlo fuera siempre que el sujeto y su "
    "espacio no se resientan.\n"
    "Enderezado (angle, en grados): usa un valor distinto de 0 SOLO si ves en la imagen "
    "una referencia claramente inclinada (horizonte, línea de mar, marco de puerta, "
    "columnas, encimera). La estimación local dada es orientativa y poco fiable en "
    "retratos; una inclinación leve suele ser intencional. En caso de duda, devuelve 0.\n"
    "Rostros (face_lifts): recibes cada cara con su índice y su luminosidad medida "
    "(0-1). Si un rostro necesita corrección LOCAL de luz — contraluz, lado en sombra, "
    "notablemente más apagado que los demás o que el fondo — inclúyelo como "
    "{index, ev}: ev positivo lo aclara (típico 0.3 a 1.2), negativo leve (hasta -0.5) "
    "si está quemado. Se aplicará como máscara radial SOLO sobre esa cara, sin tocar "
    "el resto de la imagen. Si ningún rostro lo necesita, devuelve [].\n"
    "Puntuación (rating, 1-5): valora la foto como lo haría el fotógrafo al "
    "seleccionar: 5 excepcional (nítida donde importa, expresión y momento "
    "excelentes), 4 buena, 3 correcta, 2 con un problema claro (ojos cerrados, "
    "sujeto desenfocado, expresión desafortunada), 1 fallida. Cada cara trae su "
    "nitidez medida (varianza del laplaciano: compárala entre caras y con la "
    "nitidez global; un valor muy inferior sugiere sujeto desenfocado). En caso "
    "de duda, 3. rating_reason: el motivo en español en 8 palabras o menos, o "
    "cadena vacía si no hay nada que señalar."
)


def _style_text() -> str:
    """Preferencias del fotógrafo desde estilo.txt (líneas de comentario fuera)."""
    try:
        lines = SETTINGS.style_path.read_text(encoding="utf-8").splitlines()
        return "\n".join(l for l in lines if l.strip() and not l.strip().startswith("#")).strip()
    except OSError:
        return ""


def decide(client, preview_jpeg: bytes, metrics: GlobalMetrics,
           faces: list[Face], rotation: float,
           as_shot_temp: int | None = None,
           session_prompt: str = "") -> AIDecision:
    context = {
        "metricas": {
            "luma_media": round(metrics.mean_luma, 3),
            "recorte_sombras": round(metrics.clip_shadows, 4),
            "recorte_altas_luces": round(metrics.clip_highlights, 4),
            "nitidez_global": round(metrics.sharpness, 1),
            "iso": metrics.iso,
        },
        "wb_camara_kelvin": as_shot_temp,
        "rotacion_estimada_grados": round(rotation, 2),
        "caras": [{"x": round(f.x, 3), "y": round(f.y, 3), "w": round(f.w, 3),
                   "h": round(f.h, 3), "luma": round(f.luma, 3),
                   "nitidez": round(f.sharpness, 1)} for f in faces],
    }
    style = _style_text()
    system = _SYSTEM + (f"\n\nPreferencias del fotógrafo (síguelas):\n{style}" if style else "")
    if session_prompt.strip():
        system += ("\n\nIndicaciones para ESTA sesión (prioritarias sobre lo demás):\n"
                   + session_prompt.strip()[:2000])
    try:
        response = client.messages.create(
            model=SETTINGS.model,
            max_tokens=SETTINGS.api_max_tokens,
            system=system,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(preview_jpeg).decode()}},
                {"type": "text",
                 "text": "Analiza la foto y decide los ajustes. Contexto técnico:\n"
                         + json.dumps(context, ensure_ascii=False)},
            ]}],
            output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise AIUnavailable("La API rechazó la petición")
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        crop = data["crop"]
        return clamp_decision(AIDecision(
            crop=None if crop is None else (crop["left"], crop["top"],
                                            crop["right"], crop["bottom"]),
            angle=float(data["angle"]),
            exposure=float(data["exposure"]),
            contrast=int(data["contrast"]),
            highlights=int(data["highlights"]),
            shadows=int(data["shadows"]),
            temp_shift=int(data["temp_shift"]),
            tint_shift=int(data["tint_shift"]),
            face_lifts=tuple((int(f["index"]), float(f["ev"]))
                             for f in data.get("face_lifts", [])),
            rating=int(data.get("rating", 3)),
            rating_reason=str(data.get("rating_reason", "")).strip(),
        ))
    except AIUnavailable:
        raise
    except Exception as exc:  # red, parseo, formato: todo degrada a modo local
        raise AIUnavailable(str(exc)) from exc


def clamp_decision(d: AIDecision) -> AIDecision:
    crop = d.crop
    if crop is not None:
        left, top, right, bottom = (min(max(v, 0.0), 1.0) for v in crop)
        # Descartar recortes invertidos o que dejen menos del 50% por lado
        if right - left < 0.5 or bottom - top < 0.5:
            crop = None
        else:
            crop = (left, top, right, bottom)
    return replace(
        d,
        crop=crop,
        angle=float(min(max(d.angle, -SETTINGS.max_crop_angle), SETTINGS.max_crop_angle)),
        exposure=float(min(max(d.exposure, -SETTINGS.max_global_exposure),
                           SETTINGS.max_global_exposure)),
        contrast=min(max(d.contrast, -100), 100),
        highlights=min(max(d.highlights, -100), 100),
        shadows=min(max(d.shadows, -100), 100),
        temp_shift=min(max(d.temp_shift, -SETTINGS.max_temp_shift), SETTINGS.max_temp_shift),
        tint_shift=min(max(d.tint_shift, -SETTINGS.max_tint_shift), SETTINGS.max_tint_shift),
        face_lifts=tuple((i, min(max(ev, SETTINGS.min_face_ev), SETTINGS.max_face_ev))
                         for i, ev in d.face_lifts),
        rating=min(max(d.rating, 1), 5),
        rating_reason=d.rating_reason[:120],
    )
