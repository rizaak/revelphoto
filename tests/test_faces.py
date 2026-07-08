from pathlib import Path

import numpy as np
import pytest

from revelado.analysis.faces import detect_faces, face_luma, face_sharpness
from revelado.config import SETTINGS


def test_face_luma_dark_and_bright_regions():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:50, :] = 230  # mitad superior clara
    bright = face_luma(img, x=0.1, y=0.05, w=0.3, h=0.3)
    dark = face_luma(img, x=0.1, y=0.6, w=0.3, h=0.3)
    assert bright > 0.8 and dark < 0.1


def test_face_luma_clamps_out_of_bounds():
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    assert 0.0 <= face_luma(img, x=0.9, y=0.9, w=0.5, h=0.5) <= 1.0


def test_detect_faces_missing_model_returns_empty(tmp_path):
    img = np.full((200, 200, 3), 128, dtype=np.uint8)
    assert detect_faces(img, tmp_path / "nope.onnx") == []


@pytest.mark.skipif(not SETTINGS.yunet_model_path.exists(), reason="modelo YuNet no descargado")
def test_detect_faces_runs_on_blank_image():
    img = np.full((400, 400, 3), 128, dtype=np.uint8)
    faces = detect_faces(img, SETTINGS.yunet_model_path)
    assert faces == []  # sin caras en imagen plana


def test_face_sharpness_distingue_detalle_de_liso():
    rng = np.random.default_rng(7)
    ruido = rng.integers(0, 255, (100, 100), dtype=np.uint8)
    con_detalle = np.dstack([ruido, ruido, ruido])
    liso = np.full((100, 100, 3), 120, dtype=np.uint8)
    assert face_sharpness(con_detalle, 0.2, 0.2, 0.6, 0.6) > 100
    assert face_sharpness(liso, 0.2, 0.2, 0.6, 0.6) == 0.0


def test_face_sharpness_recuadro_fuera_de_rango():
    img = np.full((50, 50, 3), 120, dtype=np.uint8)
    assert face_sharpness(img, 2.0, 2.0, 0.1, 0.1) == 0.0


def test_face_crop_jpegs_amplia_caras_pequenas():
    from revelado.analysis.faces import Face, face_crop_jpegs
    import cv2
    img = np.full((1000, 1500, 3), 128, dtype=np.uint8)
    caras = [Face(0.4, 0.3, 0.05, 0.08, luma=0.5)]  # cara de 80px de alto
    crops = face_crop_jpegs(img, caras)
    assert len(crops) == 1
    dec = cv2.imdecode(np.frombuffer(crops[0], np.uint8), cv2.IMREAD_COLOR)
    assert dec.shape[0] >= 180  # ampliada para que la IA la vea


def test_face_crop_jpegs_maximo_cuatro_y_bordes():
    from revelado.analysis.faces import Face, face_crop_jpegs
    img = np.full((500, 500, 3), 128, dtype=np.uint8)
    caras = [Face(0.95, 0.95, 0.2, 0.2, luma=0.5)] * 6  # se sale del borde
    crops = face_crop_jpegs(img, caras)
    assert len(crops) == 4
    assert all(isinstance(c, bytes) and c[:2] == b"\xff\xd8" for c in crops)


def test_face_crop_jpegs_sin_caras():
    from revelado.analysis.faces import face_crop_jpegs
    img = np.full((500, 500, 3), 128, dtype=np.uint8)
    assert face_crop_jpegs(img, []) == []


def test_face_frontal_por_defecto_y_configurable():
    from revelado.analysis.faces import Face
    assert Face(0.1, 0.1, 0.2, 0.2, luma=0.5).frontal is True
    assert Face(0.1, 0.1, 0.2, 0.2, luma=0.5, frontal=False).frontal is False
