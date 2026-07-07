import math
from dataclasses import replace

from revelado.ai import AIDecision
from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics
from revelado.develop import compute_settings, face_mask_for

METRICS = GlobalMetrics(mean_luma=0.42, clip_shadows=0.0, clip_highlights=0.0,
                        wb_temp=5400, wb_tint=3, sharpness=100.0, iso=3200)
AI = AIDecision(crop=(0.1, 0.05, 0.95, 0.9), angle=-1.5, exposure=0.3,
                contrast=10, highlights=-20, shadows=25, temp_shift=0, tint_shift=0)


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
    assert s.temperature is None  # shift 0 => As Shot
    assert s.luminance_smoothing > 0  # ISO 3200
    assert len(s.masks) == 1


def test_compute_with_ai_shift_anchored_to_camera_wb():
    ai_calido = replace(AI, temp_shift=400, tint_shift=8)
    s = compute_settings(METRICS, [], -1.0, ai_calido, as_shot_temp=5200)
    assert s.temperature == 5600 and s.tint == 8  # 5200 + 400, anclado a camara


def test_compute_with_ai_shift_without_camera_wb_stays_as_shot():
    ai_calido = replace(AI, temp_shift=400)
    s = compute_settings(METRICS, [], -1.0, ai_calido, as_shot_temp=None)
    assert s.temperature is None  # sin ancla no se toca el color


def test_compute_with_ai_tiny_shift_stays_as_shot():
    ai_leve = replace(AI, temp_shift=50, tint_shift=2)
    s = compute_settings(METRICS, [], -1.0, ai_leve, as_shot_temp=5200)
    assert s.temperature is None


def test_compute_local_only():
    s = compute_settings(METRICS, [], rotation=-2.0, ai=None)
    assert not s.ai_used and s.has_crop  # rotación != 0 => enderezado activo
    assert s.crop_angle == -2.0            # usa la estimación local
    assert s.temperature is None  # modo local nunca toca el color
    assert abs(s.exposure) <= 1.0
    # exposición local: llevar luma media hacia ~0.45 de forma conservadora
    assert s.exposure > 0                  # 0.42 < 0.45 => sube un poco


def test_local_only_angle_zero_no_crop_flag():
    s = compute_settings(METRICS, [], rotation=0.0, ai=None)
    assert not s.has_crop and s.crop_angle == 0.0


def test_exposure_bias_added_and_clamped():
    s = compute_settings(METRICS, [], 0.0, AI, as_shot_temp=5200, exposure_bias=0.4)
    assert s.exposure == 0.7  # 0.3 de la IA + 0.4 de sesgo
    s2 = compute_settings(METRICS, [], 0.0, AI, exposure_bias=5.0)
    assert s2.exposure == 1.5  # tope total


def test_temp_bias_creates_custom_from_camera_wb():
    s = compute_settings(METRICS, [], 0.0, AI, as_shot_temp=5200, temp_bias=300)
    assert s.temperature == 5500 and s.temp_shift == 300


def test_temp_bias_stacks_on_ai_shift():
    ai_calido = replace(AI, temp_shift=400)
    s = compute_settings(METRICS, [], 0.0, ai_calido, as_shot_temp=5000, temp_bias=-200)
    assert s.temperature == 5200  # (5000+400) - 200


def test_bias_applies_in_local_mode_too():
    s = compute_settings(METRICS, [], 0.0, None, as_shot_temp=5200,
                         exposure_bias=0.3, temp_bias=250)
    assert s.temperature == 5450
    assert s.exposure > 0.3  # exposición local + sesgo


def test_ai_face_lift_creates_mask_on_bright_face():
    """La IA puede pedir máscara aunque la cara no baje del umbral mecánico."""
    ai_lift = replace(AI, face_lifts=((0, 0.6),))
    s = compute_settings(METRICS, [Face(0.4, 0.3, 0.1, 0.12, luma=0.50)], 0.0,
                         ai_lift, as_shot_temp=5200)
    assert len(s.masks) == 1 and s.masks[0].exposure_ev == 0.6


def test_threshold_safety_net_when_ai_omits_dark_face():
    s = compute_settings(METRICS, [Face(0.4, 0.3, 0.1, 0.12, luma=0.20)], 0.0,
                         AI, as_shot_temp=5200)  # AI sin face_lifts
    assert len(s.masks) == 1  # regla dura del producto


def test_tiny_or_invalid_lifts_ignored():
    ai_lift = replace(AI, face_lifts=((0, 0.05), (7, 1.0)))  # ínfimo e índice inexistente
    s = compute_settings(METRICS, [Face(0.4, 0.3, 0.1, 0.12, luma=0.50)], 0.0,
                         ai_lift, as_shot_temp=5200)
    assert s.masks == []


def test_negative_lift_darkens_burnt_face():
    ai_lift = replace(AI, face_lifts=((0, -0.4),))
    s = compute_settings(METRICS, [Face(0.4, 0.3, 0.1, 0.12, luma=0.85)], 0.0,
                         ai_lift, as_shot_temp=5200)
    assert s.masks[0].exposure_ev == -0.4 and s.masks[0].shadows == 0


def test_rating_pasa_del_ai_al_resultado():
    ai = replace(AI, rating=5, rating_reason="momento excelente")
    s = compute_settings(METRICS, [], 0.0, ai)
    assert s.rating == 5 and s.rating_reason == "momento excelente"


def test_rate_false_desactiva_las_estrellas():
    ai = replace(AI, rating=5, rating_reason="x")
    s = compute_settings(METRICS, [], 0.0, ai, rate=False)
    assert s.rating is None and s.rating_reason == ""


def test_modo_local_sin_estrellas():
    s = compute_settings(METRICS, [], 0.0, ai=None)
    assert s.rating is None
