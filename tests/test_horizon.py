import cv2
import numpy as np

from revelado.analysis.horizon import estimate_rotation


def _line_image(angle_deg: float) -> np.ndarray:
    """Imagen 400x400 con una línea 'horizonte' inclinada angle_deg."""
    img = np.full((400, 400, 3), 40, dtype=np.uint8)
    t = np.tan(np.radians(angle_deg))
    p1 = (0, int(200 + 200 * t))
    p2 = (400, int(200 - 200 * t))
    cv2.line(img, p1, p2, (220, 220, 220), 3)
    return img


def test_level_horizon_near_zero():
    assert abs(estimate_rotation(_line_image(0.0))) < 0.3


def test_tilted_horizon_detected_within_half_degree():
    est = estimate_rotation(_line_image(3.0))
    assert abs(abs(est) - 3.0) < 0.5 and est != 0.0


def test_no_lines_returns_zero():
    img = np.full((400, 400, 3), 128, dtype=np.uint8)
    assert estimate_rotation(img) == 0.0


def test_clamped_to_seven_degrees():
    assert abs(estimate_rotation(_line_image(6.5))) <= 7.0
