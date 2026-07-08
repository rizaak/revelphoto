import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    luma: float
    sharpness: float = 0.0  # varianza del laplaciano de la zona central (bajo = desenfocada)
    frontal: bool = True    # False = perfil (los ojos separan poco); el veredicto de ojos no vale

_MIN_EYE_SEP = 0.28  # separación de ojos / ancho de cara; por debajo, perfil


def _central_gray(img_bgr: np.ndarray, x: float, y: float,
                  w: float, h: float) -> np.ndarray | None:
    """El 60% central del recuadro normalizado, en gris (evita pelo/fondo)."""
    ih, iw = img_bgr.shape[:2]
    cx, cy = x + w / 2, y + h / 2
    w, h = w * 0.6, h * 0.6
    x0 = max(0, int((cx - w / 2) * iw))
    y0 = max(0, int((cy - h / 2) * ih))
    x1 = min(iw, int((cx + w / 2) * iw))
    y1 = min(ih, int((cy + h / 2) * ih))
    if x1 <= x0 or y1 <= y0:
        return None
    return cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)


def face_luma(img_bgr: np.ndarray, x: float, y: float, w: float, h: float) -> float:
    """Luminancia media (0-1) del 60% central del recuadro normalizado."""
    region = _central_gray(img_bgr, x, y, w, h)
    if region is None:
        return 0.5
    return float(region.mean() / 255.0)


def face_sharpness(img_bgr: np.ndarray, x: float, y: float, w: float, h: float) -> float:
    region = _central_gray(img_bgr, x, y, w, h)
    if region is None or region.size < 4:
        return 0.0
    return float(cv2.Laplacian(region, cv2.CV_64F).var())


def face_crop_jpegs(img_bgr: np.ndarray, faces: list[Face],
                    limit: int = 4, min_height: int = 192) -> list[bytes]:
    """Recortes JPEG de las caras, ampliados para que la IA pueda juzgarlos.

    En la vista previa completa una cara ocupa píxeles de más; a este tamaño
    la IA distingue movida/desenfocada/ojos cerrados/tapada (verificado con
    fotos reales). Mismo orden que `faces` (los índices coinciden).
    """
    ih, iw = img_bgr.shape[:2]
    crops: list[bytes] = []
    for f in faces[:limit]:
        mx, my = f.w * 0.15, f.h * 0.15  # margen para barbilla/frente
        x0, y0 = max(0, int((f.x - mx) * iw)), max(0, int((f.y - my) * ih))
        x1 = min(iw, int((f.x + f.w + mx) * iw))
        y1 = min(ih, int((f.y + f.h + my) * ih))
        if x1 <= x0 or y1 <= y0:
            continue
        crop = img_bgr[y0:y1, x0:x1]
        if crop.shape[0] < min_height:
            scale = min_height / crop.shape[0]
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            crops.append(buf.tobytes())
    return crops


def detect_faces(img_bgr: np.ndarray, model_path: Path) -> list[Face]:
    if not model_path.exists():
        log.warning("Modelo YuNet no encontrado en %s; sin detección de caras", model_path)
        return []
    ih, iw = img_bgr.shape[:2]
    detector = cv2.FaceDetectorYN_create(str(model_path), "", (iw, ih), score_threshold=0.7)
    _, dets = detector.detect(img_bgr)
    faces: list[Face] = []
    if dets is None:
        return faces
    for d in dets:
        x, y, w, h = (float(v) for v in d[:4])
        nx, ny, nw, nh = x / iw, y / ih, w / iw, h / ih
        # landmarks YuNet: d[4:6]=ojo derecho, d[6:8]=ojo izquierdo
        frontal = w > 0 and abs(float(d[6]) - float(d[4])) / w >= _MIN_EYE_SEP
        faces.append(Face(x=nx, y=ny, w=nw, h=nh,
                          luma=face_luma(img_bgr, nx, ny, nw, nh),
                          sharpness=face_sharpness(img_bgr, nx, ny, nw, nh),
                          frontal=frontal))
    return faces
