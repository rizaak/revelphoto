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


def face_luma(img_bgr: np.ndarray, x: float, y: float, w: float, h: float) -> float:
    """Luminancia media (0-1) del 60% central del recuadro normalizado."""
    ih, iw = img_bgr.shape[:2]
    # Contraer al 60% central para evitar pelo/fondo
    cx, cy = x + w / 2, y + h / 2
    w, h = w * 0.6, h * 0.6
    x0 = max(0, int((cx - w / 2) * iw))
    y0 = max(0, int((cy - h / 2) * ih))
    x1 = min(iw, int((cx + w / 2) * iw))
    y1 = min(ih, int((cy + h / 2) * ih))
    if x1 <= x0 or y1 <= y0:
        return 0.5
    region = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float(region.mean() / 255.0)


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
        faces.append(Face(x=nx, y=ny, w=nw, h=nh,
                          luma=face_luma(img_bgr, nx, ny, nw, nh)))
    return faces
