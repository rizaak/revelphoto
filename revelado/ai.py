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
    temperature: int
    tint: int


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
        "temperature": {"type": "integer"},
        "tint": {"type": "integer"},
    },
    "required": ["crop", "angle", "exposure", "contrast", "highlights",
                 "shadows", "temperature", "tint"],
    "additionalProperties": False,
}

_SYSTEM = (
    "Eres un editor fotográfico profesional de retratos. Recibes la vista previa de una "
    "foto RAW y métricas técnicas medidas localmente. Devuelve ajustes de revelado para "
    "Lightroom en JSON. Reglas: exposición global conservadora (los rostros oscuros se "
    "corrigen aparte con máscaras locales, no subas la exposición global por ellos); "
    "recorta solo si mejora claramente la composición (regla de tercios, distracciones "
    "en bordes) y nunca cortes cabezas; crop en coordenadas normalizadas 0-1 de la imagen "
    "completa, o null si el encuadre ya es bueno; angle es el ajuste fino de enderezado "
    "en grados (parte de la estimación local dada); temperature/tint parten de la "
    "estimación local, corrígelos solo si ves un dominante de color."
)


def decide(client, preview_jpeg: bytes, metrics: GlobalMetrics,
           faces: list[Face], rotation: float) -> AIDecision:
    context = {
        "metricas": {
            "luma_media": round(metrics.mean_luma, 3),
            "recorte_sombras": round(metrics.clip_shadows, 4),
            "recorte_altas_luces": round(metrics.clip_highlights, 4),
            "wb_temp_estimada": metrics.wb_temp,
            "wb_tint_estimado": metrics.wb_tint,
            "iso": metrics.iso,
        },
        "rotacion_estimada_grados": round(rotation, 2),
        "caras": [{"x": round(f.x, 3), "y": round(f.y, 3), "w": round(f.w, 3),
                   "h": round(f.h, 3), "luma": round(f.luma, 3)} for f in faces],
    }
    try:
        response = client.messages.create(
            model=SETTINGS.model,
            max_tokens=SETTINGS.api_max_tokens,
            system=_SYSTEM,
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
            temperature=int(data["temperature"]),
            tint=int(data["tint"]),
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
        temperature=min(max(d.temperature, 2500), 10000),
        tint=min(max(d.tint, -100), 100),
    )
