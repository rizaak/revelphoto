import cv2
import numpy as np

MAX_ANGLE = 7.0  # grados; más allá se asume intencional


def estimate_rotation(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    min_len = int(min(img_bgr.shape[:2]) * 0.3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=80,
                            minLineLength=min_len, maxLineGap=10)
    if lines is None:
        return 0.0
    angles = []
    # HoughLinesP devuelve (N,1,4) en OpenCV 4.x y (N,4) en 5.x; normalizamos
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        if x2 == x1:
            continue
        ang = np.degrees(np.arctan2(y1 - y2, x2 - x1))  # y invertida (imagen)
        if abs(ang) <= MAX_ANGLE:  # solo casi-horizontales
            angles.append(ang)
    if not angles:
        return 0.0
    med = float(np.median(angles))
    # CropAngle en LR: valor positivo rota la imagen en sentido horario para nivelar
    return float(np.clip(-med, -MAX_ANGLE, MAX_ANGLE))
