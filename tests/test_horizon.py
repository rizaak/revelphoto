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


def test_conflicting_lines_return_zero():
    """Diagonales de escena en desacuerdo => no hay horizonte fiable."""
    img = np.full((400, 400, 3), 40, dtype=np.uint8)
    t = np.tan(np.radians(3.0))
    cv2.line(img, (0, int(150 + 200 * t)), (400, int(150 - 200 * t)), (220, 220, 220), 3)
    cv2.line(img, (0, int(280 - 200 * t)), (400, int(280 + 200 * t)), (220, 220, 220), 3)
    assert estimate_rotation(img) == 0.0


def test_short_line_is_not_enough_evidence():
    """Una línea corta (menos del 50% del ancho) no justifica enderezar."""
    img = np.full((400, 400, 3), 40, dtype=np.uint8)
    t = np.tan(np.radians(3.0))
    cv2.line(img, (130, int(200 + 70 * t)), (270, int(200 - 70 * t)), (220, 220, 220), 3)
    assert estimate_rotation(img) == 0.0


def _vertical_image(angle_deg: float) -> np.ndarray:
    """Imagen 400x400 con una 'columna' vertical inclinada angle_deg (misma
    rotación física que _line_image)."""
    img = np.full((400, 400, 3), 40, dtype=np.uint8)
    cv2.line(img, (200, 0), (200, 400), (220, 220, 220), 3)
    m = cv2.getRotationMatrix2D((200, 200), angle_deg, 1.0)
    return cv2.warpAffine(img, m, (400, 400), borderValue=(40, 40, 40))


def test_vertical_tilted_detected_with_same_sign_as_horizontal():
    est_v = estimate_rotation(_vertical_image(3.0))
    ref = np.full((400, 400, 3), 40, dtype=np.uint8)
    t = np.tan(np.radians(3.0))
    cv2.line(ref, (0, int(200 + 200 * t)), (400, int(200 - 200 * t)), (220, 220, 220), 3)
    est_h = estimate_rotation(ref)
    assert est_v != 0.0
    assert abs(est_v - est_h) < 0.5  # mismo ángulo y mismo signo


def test_vertical_level_near_zero():
    assert abs(estimate_rotation(_vertical_image(0.0))) < 0.3
