import math
from dataclasses import replace

from revelado.ai import AIDecision
from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics
from revelado.develop import compute_settings, face_mask_for

METRICS = GlobalMetrics(mean_luma=0.42, clip_shadows=0.0, clip_highlights=0.0,
                        wb_temp=5400, wb_tint=3, sharpness=100.0, iso=3200)
AI = AIDecision(crop=(0.1, 0.05, 0.95, 0.9), angle=-1.5, exposure=0.3,
                contrast=10, highlights=-20, shadows=25, temperature=5300, tint=6)


def test_dark_face_gets_mask_with_capped_ev():
    mask = face_mask_for(Face(0.4, 0.3, 0.1, 0.12, luma=0.20))
    assert mask is not None
    expected = math.log2(0.50 / 0.20)
    assert abs(mask.exposure_ev - expected) < 0.01
    very_dark = face_mask_for(Face(0.4, 0.3, 0.1, 0.12, luma=0.02))
    assert very_dark.exposure_ev == 1.5  # tope


def test_bright_face_no_mask():
    assert face_mask_for(Face(0.4, 0.3, 0.1, 0.12, luma=0.55)) is None


def test_mask_ellipse_expands_face_box_and_clamps():
    mask = face_mask_for(Face(0.0, 0.0, 0.2, 0.2, luma=0.1))
    assert mask.left >= 0.0 and mask.top >= 0.0
    assert mask.right - mask.left > 0.2  # expandido ~1.6x (recortado al borde)


def test_compute_with_ai_uses_ai_values():
    s = compute_settings(METRICS, [Face(0.4, 0.3, 0.1, 0.12, luma=0.2)], -1.0, AI)
    assert s.ai_used and s.has_crop
    assert (s.crop_left, s.crop_top, s.crop_right, s.crop_bottom) == AI.crop
    assert s.crop_angle == AI.angle and s.exposure == AI.exposure
    assert s.temperature is None  # sin dominante => As Shot
    assert s.luminance_smoothing > 0  # ISO 3200
    assert len(s.masks) == 1


def test_compute_with_ai_strong_cast_uses_custom_wb():
    ai_calido = replace(AI, temperature=4200)
    s = compute_settings(METRICS, [], -1.0, ai_calido)
    assert s.temperature == 4200


def test_compute_local_only():
    s = compute_settings(METRICS, [], rotation=-2.0, ai=None)
    assert not s.ai_used and s.has_crop  # rotación != 0 => enderezado activo
    assert s.crop_angle == -2.0            # usa la estimación local
    assert s.temperature is None  # sin dominante => As Shot
    assert abs(s.exposure) <= 1.0
    # exposición local: llevar luma media hacia ~0.45 de forma conservadora
    assert s.exposure > 0                  # 0.42 < 0.45 => sube un poco


def test_local_only_angle_zero_no_crop_flag():
    s = compute_settings(METRICS, [], rotation=0.0, ai=None)
    assert not s.has_crop and s.crop_angle == 0.0
