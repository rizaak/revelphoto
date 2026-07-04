import logging
from dataclasses import dataclass
from pathlib import Path

from revelado.ai import AIUnavailable, decide
from revelado.analysis.faces import detect_faces
from revelado.analysis.horizon import estimate_rotation
from revelado.analysis.metrics import compute_metrics
from revelado.config import SETTINGS
from revelado.develop import DevelopSettings, compute_settings
from revelado.exif import extract_preview_jpeg, read_exif
from revelado.imageio import decode_upright, encode_jpeg
from revelado.xmp import SidecarExists, sidecar_path, write_sidecar

log = logging.getLogger(__name__)


@dataclass
class PhotoResult:
    path: str
    status: str  # done | done_local_only | skipped_existing | error
    message: str = ""
    settings: DevelopSettings | None = None


def process_photo(raw_path: Path, overwrite: bool, client) -> PhotoResult:
    try:
        if sidecar_path(raw_path).exists() and not overwrite:
            return PhotoResult(str(raw_path), "skipped_existing",
                               "Ya existe un XMP; no se sobrescribe sin confirmación")

        exif = read_exif(raw_path)
        jpeg = extract_preview_jpeg(raw_path)
        img = decode_upright(jpeg, exif.orientation, SETTINGS.preview_long_edge)
        metrics = compute_metrics(img, exif.iso)
        faces = detect_faces(img, SETTINGS.yunet_model_path)
        rotation = estimate_rotation(img)

        ai = None
        status = "done_local_only"
        if client is not None:
            try:
                ai = decide(client, encode_jpeg(img), metrics, faces, rotation)
                status = "done"
            except AIUnavailable as exc:
                log.warning("API no disponible para %s: %s", raw_path.name, exc)

        settings = compute_settings(metrics, faces, rotation, ai)
        write_sidecar(raw_path, settings, overwrite=overwrite)
        return PhotoResult(str(raw_path), status, settings=settings)

    except SidecarExists:
        return PhotoResult(str(raw_path), "skipped_existing",
                           "Ya existe un XMP; no se sobrescribe sin confirmación")
    except Exception as exc:
        log.exception("Error procesando %s", raw_path)
        return PhotoResult(str(raw_path), "error", f"{type(exc).__name__}: {exc}")
