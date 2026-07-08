import math

import cv2
import numpy as np

MAX_ANGLE = 7.0        # grados; más allá se asume intencional
MIN_DOMINANT = 0.6     # una línea dominante debe cubrir ≥ 60% de su eje...
MIN_TOTAL = 1.0        # ...o la evidencia total sumar ≥ 100% del eje
MAX_SPREAD = 0.8       # dispersión máxima (grados) entre líneas para considerarlas de acuerdo


def estimate_rotation(img_bgr: np.ndarray) -> float:
    """Ángulo de enderezado (crs:CropAngle) o 0.0 si no hay referencia fiable.

    Acepta referencias casi-horizontales (horizonte, encimeras) y
    casi-verticales (marcos, columnas, paredes) — en retratos las verticales
    son las más habituales. Una vertical inclinada se pliega sobre su
    corrección horizontal equivalente (mismo signo). Solo devolvemos un
    ángulo cuando varias líneas largas están de acuerdo entre sí; ante
    evidencia débil o contradictoria, 0.0 (no enderezar).
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    height, width = img_bgr.shape[:2]
    min_len = int(min(height, width) * 0.3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=80,
                            minLineLength=min_len, maxLineGap=10)
    if lines is None:
        return 0.0
    segments: list[tuple[float, float]] = []  # (desviación, fracción de su eje)
    # HoughLinesP devuelve (N,1,4) en OpenCV 4.x y (N,4) en 5.x; normalizamos
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        ang = float(np.degrees(np.arctan2(y1 - y2, x2 - x1)))  # y invertida (imagen)
        if ang > 90:
            ang -= 180
        elif ang <= -90:
            ang += 180
        if abs(ang) > 45:  # casi-vertical: misma corrección de nivel, mismo signo
            deviation = ang - 90 if ang > 0 else ang + 90
            axis = height
        else:
            deviation = ang
            axis = width
        if abs(deviation) <= MAX_ANGLE:
            segments.append((deviation, math.hypot(x2 - x1, y2 - y1) / axis))
    if not segments:
        return 0.0
    total_frac = sum(frac for _, frac in segments)
    longest_frac = max(frac for _, frac in segments)
    if longest_frac < MIN_DOMINANT and total_frac < MIN_TOTAL:
        return 0.0  # evidencia insuficiente: mejor no tocar
    angles = [a for a, _ in segments]
    med = float(np.median(angles))
    spread = float(np.median([abs(a - med) for a in angles]))
    if spread > MAX_SPREAD:
        return 0.0  # líneas en desacuerdo (diagonales de escena, no horizonte)
    # CropAngle en LR: valor positivo rota la imagen en sentido horario para nivelar
    return float(np.clip(-med, -MAX_ANGLE, MAX_ANGLE))
