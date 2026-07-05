"""Simulación aproximada de los ajustes de revelado sobre la vista previa.

No replica el motor RAW de Adobe: es una aproximación para que el
antes/después de la pantalla de revisión se parezca a lo que se verá en
Lightroom (balance, exposición, contraste, luces/sombras, recorte y giro).
"""
import cv2
import numpy as np


def simulate(img_bgr: np.ndarray, *, exposure: float = 0.0, contrast: int = 0,
             highlights: int = 0, shadows: int = 0, temp_shift: int = 0,
             tint: int = 0, angle: float = 0.0,
             crop: tuple[float, float, float, float] | None = None) -> np.ndarray:
    img = img_bgr.astype(np.float32) / 255.0
    h, w = img.shape[:2]

    # Geometría: girar para nivelar (CropAngle positivo = horario) y recortar
    if angle:
        m = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
        img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
    if crop is not None:
        left, top, right, bottom = crop
        y0, y1 = int(top * h), max(int(top * h) + 1, int(bottom * h))
        x0, x1 = int(left * w), max(int(left * w) + 1, int(right * w))
        img = img[y0:y1, x0:x1]

    # Exposición (EV)
    if exposure:
        img = img * (2.0 ** exposure)

    # Balance: temp_shift > 0 = más cálido (sube rojo, baja azul); tint > 0 = más magenta
    if temp_shift:
        f = temp_shift / 4000.0
        img[..., 2] *= 1 + f
        img[..., 0] *= 1 - f
    if tint:
        img[..., 1] *= 1 - tint / 300.0

    # Contraste alrededor del gris medio
    if contrast:
        img = (img - 0.5) * (1 + contrast / 150.0) + 0.5

    # Sombras y altas luces: corrección suave ponderada por luminancia
    luma = img.mean(axis=2, keepdims=True)
    if shadows:
        img = img + (shadows / 100.0) * 0.5 * np.clip(1 - luma * 2, 0, 1)
    if highlights:
        img = img + (highlights / 100.0) * 0.5 * np.clip(luma * 2 - 1, 0, 1)

    return (np.clip(img, 0.0, 1.0) * 255).astype(np.uint8)
