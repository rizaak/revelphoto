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
