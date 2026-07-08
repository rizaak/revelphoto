from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class GlobalMetrics:
    mean_luma: float
    clip_shadows: float
    clip_highlights: float
    wb_temp: int
    wb_tint: int
    sharpness: float
    iso: int


def compute_metrics(img_bgr: np.ndarray, iso: int) -> GlobalMetrics:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    luma = gray.astype(np.float64) / 255.0
    b, g, r = (img_bgr[:, :, i].mean() for i in range(3))

    # Gris-mundo: desviación de R/B respecto a G, mapeada alrededor de 5500K.
    # +600K por cada 10% de dominancia azul (cast frío => subir temperatura).
    eps = 1e-6
    blue_bias = (b - r) / (g + eps)          # >0: cast azul, <0: cast cálido
    green_bias = (g - (r + b) / 2) / (g + eps)  # >0: cast verde => tint magenta
    wb_temp = int(np.clip(5500 + blue_bias * 6000, 3000, 9000))
    wb_tint = int(np.clip(green_bias * 150, -50, 50))

    return GlobalMetrics(
        mean_luma=float(luma.mean()),
        clip_shadows=float((gray <= 2).mean()),
        clip_highlights=float((gray >= 253).mean()),
        wb_temp=wb_temp,
        wb_tint=wb_tint,
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        iso=iso,
    )


def sharpening_for(sharpness: float) -> int:
    # Imagen blanda (varianza baja) => más enfoque; nítida => enfoque base.
    if sharpness < 50:
        return 60
    if sharpness < 200:
        return 45
    return 30


def noise_reduction_for(iso: int) -> int:
    if iso <= 400:
        return 0
    if iso <= 1600:
        return 15
    if iso <= 6400:
        return 25
    return 40


def color_noise_for(iso: int) -> int:
    # Ruido de color (puntos verdes/magenta) en ISO alto; 25 es el defecto de LR.
    if iso <= 1600:
        return 25
    if iso <= 6400:
        return 35
    return 50
