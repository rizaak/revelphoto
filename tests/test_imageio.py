import numpy as np

from revelado.imageio import decode_upright, encode_jpeg
from tests.conftest import to_jpeg


def test_decode_no_rotation(gradient_img):
    out = decode_upright(to_jpeg(gradient_img), orientation=1, max_edge=1500)
    assert out.shape[:2] == (200, 300)


def test_decode_orientation_6_rotates_90cw(gradient_img):
    out = decode_upright(to_jpeg(gradient_img), orientation=6, max_edge=1500)
    assert out.shape[:2] == (300, 200)  # landscape -> portrait


def test_decode_resizes_long_edge(gradient_img):
    out = decode_upright(to_jpeg(gradient_img), orientation=1, max_edge=150)
    assert max(out.shape[:2]) == 150


def test_encode_roundtrip(gradient_img):
    data = encode_jpeg(gradient_img)
    assert data.startswith(b"\xff\xd8")
    out = decode_upright(data, orientation=1, max_edge=1500)
    assert out.shape == gradient_img.shape
