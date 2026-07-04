import cv2
import numpy as np
import pytest


@pytest.fixture
def gradient_img():
    """Imagen 300x200 BGR con gradiente horizontal de negro a blanco."""
    img = np.tile(np.linspace(0, 255, 300, dtype=np.uint8), (200, 1))
    return cv2.merge([img, img, img])


def to_jpeg(img):
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()
