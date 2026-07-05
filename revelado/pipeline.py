import logging
from dataclasses import dataclass, field
from pathlib import Path

from revelado.ai import AIDecision, AIUnavailable, decide
from revelado.analysis.faces import Face, detect_faces
from revelado.analysis.horizon import estimate_rotation
from revelado.analysis.metrics import GlobalMetrics, compute_metrics
from revelado.config import SETTINGS
from revelado.develop import DevelopSettings, compute_settings
from revelado.exif import ExifData, extract_preview_jpeg, read_exif
from revelado.imageio import decode_upright, encode_jpeg
from revelado.xmp import SidecarExists, sidecar_path, write_sidecar

log = logging.getLogger(__name__)

_SKIP_MSG = "Ya existe un XMP; no se sobrescribe sin confirmación"


@dataclass
class PhotoResult:
    path: str
    status: str  # done | done_local_only | skipped_existing | error
    message: str = ""
    settings: DevelopSettings | None = None


@dataclass
class PhotoAnalysis:
    """Resultado de la fase de análisis; la armonización puede ajustar `ai`."""
    path: Path
    skipped: bool = False
    error: str = ""
    exif: ExifData | None = None
    metrics: GlobalMetrics | None = None
    faces: list[Face] = field(default_factory=list)
    rotation: float = 0.0
    ai: AIDecision | None = None


def analyze_photo(raw_path: Path, overwrite: bool, client,
                  session_prompt: str = "") -> PhotoAnalysis:
    """Fase 1: análisis local + decisión de la IA (sin escribir nada)."""
    try:
        if sidecar_path(raw_path).exists() and not overwrite:
            return PhotoAnalysis(raw_path, skipped=True)

        exif = read_exif(raw_path)
        jpeg = extract_preview_jpeg(raw_path)
        img = decode_upright(jpeg, exif.orientation, SETTINGS.preview_long_edge)
        metrics = compute_metrics(img, exif.iso)
        faces = detect_faces(img, SETTINGS.yunet_model_path)
        rotation = estimate_rotation(img)

        ai = None
        if client is not None:
            try:
                ai = decide(client, encode_jpeg(img), metrics, faces, rotation,
                            as_shot_temp=exif.color_temp,
                            session_prompt=session_prompt)
            except AIUnavailable as exc:
                log.warning("API no disponible para %s: %s", raw_path.name, exc)

        return PhotoAnalysis(raw_path, exif=exif, metrics=metrics, faces=faces,
                             rotation=rotation, ai=ai)
    except Exception as exc:
        log.exception("Error analizando %s", raw_path)
        return PhotoAnalysis(raw_path, error=f"{type(exc).__name__}: {exc}")


def finalize_photo(analysis: PhotoAnalysis, overwrite: bool,
                   exposure_bias: float = 0.0, temp_bias: int = 0) -> PhotoResult:
    """Fase 2: calcular ajustes finales y escribir el XMP."""
    raw_path = analysis.path
    if analysis.skipped:
        return PhotoResult(str(raw_path), "skipped_existing", _SKIP_MSG)
    if analysis.error:
        return PhotoResult(str(raw_path), "error", analysis.error)
    try:
        as_shot = analysis.exif.color_temp if analysis.exif else None
        settings = compute_settings(analysis.metrics, analysis.faces,
                                    analysis.rotation, analysis.ai,
                                    as_shot_temp=as_shot,
                                    exposure_bias=exposure_bias,
                                    temp_bias=temp_bias)
        write_sidecar(raw_path, settings, overwrite=overwrite)
        status = "done" if analysis.ai is not None else "done_local_only"
        return PhotoResult(str(raw_path), status, settings=settings)
    except SidecarExists:
        return PhotoResult(str(raw_path), "skipped_existing", _SKIP_MSG)
    except Exception as exc:
        log.exception("Error escribiendo ajustes de %s", raw_path)
        return PhotoResult(str(raw_path), "error", f"{type(exc).__name__}: {exc}")


def process_photo(raw_path: Path, overwrite: bool, client) -> PhotoResult:
    """Foto suelta (reprocesado individual): analizar y escribir sin armonizar."""
    return finalize_photo(analyze_photo(raw_path, overwrite, client), overwrite)
