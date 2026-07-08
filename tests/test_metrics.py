import cv2
import numpy as np

from revelado.analysis.metrics import (GlobalMetrics, color_noise_for,
                                       compute_metrics, noise_reduction_for,
                                       sharpening_for)


def _flat(value, shape=(100, 100, 3)):
    return np.full(shape, value, dtype=np.uint8)


def test_mean_luma_midgray():
    m = compute_metrics(_flat(128), iso=100)
    assert 0.45 < m.mean_luma < 0.55


def test_clipping_detected():
    img = _flat(0)
    img[:, 50:] = 255
    m = compute_metrics(img, iso=100)
    assert m.clip_shadows > 0.4 and m.clip_highlights > 0.4


def test_wb_neutral_gray_is_daylight():
    m = compute_metrics(_flat(128), iso=100)
    assert 4500 <= m.wb_temp <= 6500
    assert -20 <= m.wb_tint <= 20


def test_wb_blue_cast_lowers_temp():
    img = _flat(128).astype(np.int16)
    img[:, :, 0] += 60  # canal azul dominante (BGR)
    m = compute_metrics(np.clip(img, 0, 255).astype(np.uint8), iso=100)
    neutral = compute_metrics(_flat(128), iso=100)
    assert m.wb_temp > neutral.wb_temp  # corregir azul => subir temperatura


def test_sharpness_blur_ranks_lower(gradient_img):
    noise = np.random.default_rng(0).integers(0, 255, gradient_img.shape, dtype=np.uint8)
    sharp = compute_metrics(noise, iso=100).sharpness
    blurred = compute_metrics(cv2.GaussianBlur(noise, (15, 15), 5), iso=100).sharpness
    assert sharp > blurred


def test_sharpening_and_nr_ranges():
    assert 25 <= sharpening_for(5.0) <= 60
    assert sharpening_for(5.0) >= sharpening_for(500.0)
    assert noise_reduction_for(100) == 0
    assert noise_reduction_for(3200) > 0
    assert noise_reduction_for(25600) <= 40


def test_color_noise_por_iso():
    assert color_noise_for(100) == 25   # el valor por defecto de Lightroom
    assert color_noise_for(3200) == 35
    assert color_noise_for(12800) == 50
