import math

import cv2
import numpy as np

MAX_ANGLE = 7.0        # grados; más allá se asume intencional
MIN_DOMINANT = 0.6     # una línea dominante debe cubrir ≥ 60% del ancho...
MIN_TOTAL = 1.0        # ...o la evidencia total sumar ≥ 100% del ancho
MAX_SPREAD = 0.8       # dispersión máxima (grados) entre líneas para considerarlas de acuerdo


def estimate_rotation(img_bgr: np.ndarray) -> float:
    """Ángulo de enderezado (crs:CropAngle) o 0.0 si no hay referencia fiable.

    En retratos rara vez hay horizonte real: solo devolvemos un ángulo cuando
    varias líneas casi-horizontales largas están de acuerdo entre sí. Ante
    evidencia débil o contradictoria, 0.0 (no enderezar).
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    min_len = int(min(img_bgr.shape[:2]) * 0.3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=80,
                            minLineLength=min_len, maxLineGap=10)
    if lines is None:
        return 0.0
    segments: list[tuple[float, float]] = []  # (ángulo, longitud)
    # HoughLinesP devuelve (N,1,4) en OpenCV 4.x y (N,4) en 5.x; normalizamos
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        if x2 == x1:
            continue
        ang = np.degrees(np.arctan2(y1 - y2, x2 - x1))  # y invertida (imagen)
        if abs(ang) <= MAX_ANGLE:  # solo casi-horizontales
            segments.append((float(ang), math.hypot(x2 - x1, y2 - y1)))
    if not segments:
        return 0.0
    width = img_bgr.shape[1]
    total_length = sum(length for _, length in segments)
    longest = max(length for _, length in segments)
    if longest < MIN_DOMINANT * width and total_length < MIN_TOTAL * width:
        return 0.0  # evidencia insuficiente: mejor no tocar
    angles = [a for a, _ in segments]
    med = float(np.median(angles))
    spread = float(np.median([abs(a - med) for a in angles]))
    if spread > MAX_SPREAD:
        return 0.0  # líneas en desacuerdo (diagonales de escena, no horizonte)
    # CropAngle en LR: valor positivo rota la imagen en sentido horario para nivelar
    return float(np.clip(-med, -MAX_ANGLE, MAX_ANGLE))
