import math
from dataclasses import dataclass, field

from revelado.ai import AIDecision
from revelado.analysis.faces import Face
from revelado.analysis.metrics import (GlobalMetrics, noise_reduction_for,
                                       sharpening_for)
from revelado.config import SETTINGS

MASK_EXPANSION = 1.6  # la elipse cubre 1.6x el recuadro de la cara


@dataclass(frozen=True)
class RadialMask:
    left: float
    top: float
    right: float
    bottom: float
    exposure_ev: float
    shadows: int


@dataclass
class DevelopSettings:
    temperature: int | None  # None => "As Shot" (sin dominante de color claro)
    tint: int
    exposure: float
    contrast: int
    highlights: int
    shadows: int
    whites: int
    blacks: int
    sharpness: int
    luminance_smoothing: int
    has_crop: bool
    crop_left: float
    crop_top: float
    crop_right: float
    crop_bottom: float
    crop_angle: float
    masks: list[RadialMask] = field(default_factory=list)
    ai_used: bool = False
    temp_shift: int = 0  # desviación aplicada respecto al WB de cámara (para la simulación)


def face_mask_for(face: Face, ev: float | None = None) -> RadialMask | None:
    """Máscara radial para una cara.

    Con `ev` explícito (decisión de la IA) se usa ese valor; sin él aplica la
    regla dura del producto: caras bajo el umbral se levantan hacia el objetivo.
    """
    if ev is None:
        if face.luma >= SETTINGS.face_lum_threshold:
            return None
        ev = math.log2(SETTINGS.face_lum_target / max(face.luma, 0.05))
        ev = min(ev, SETTINGS.max_face_ev)
    elif abs(ev) < SETTINGS.min_face_lift_apply:
        return None
    cx, cy = face.x + face.w / 2, face.y + face.h / 2
    hw, hh = face.w * MASK_EXPANSION / 2, face.h * MASK_EXPANSION / 2
    return RadialMask(
        left=max(0.0, cx - hw), top=max(0.0, cy - hh),
        right=min(1.0, cx + hw), bottom=min(1.0, cy + hh),
        exposure_ev=round(ev, 2),
        shadows=25 if ev > 0 else 0,
    )


def _masks_from_ai(faces: list[Face], ai: AIDecision) -> list[RadialMask]:
    """Máscaras según la IA, con la regla del umbral como red de seguridad."""
    lifts = {i: ev for i, ev in ai.face_lifts if 0 <= i < len(faces)}
    masks = []
    for idx, face in enumerate(faces):
        mask = (face_mask_for(face, ev=lifts[idx]) if idx in lifts
                else face_mask_for(face))
        if mask is not None:
            masks.append(mask)
    return masks


def _wb_from_shift(as_shot_temp: int | None, temp_shift: int,
                   tint_shift: int) -> tuple[int | None, int]:
    """WB absoluto anclado al de cámara; None => se queda en "As Shot".

    Solo se escribe WB Custom si la IA pidió una desviación significativa Y
    conocemos el Kelvin de cámara para anclarla (si no, mejor no tocar el color).
    """
    significant = (abs(temp_shift) >= SETTINGS.min_temp_shift_apply
                   or abs(tint_shift) >= SETTINGS.min_tint_shift_apply)
    if as_shot_temp is None or not significant:
        return None, 0
    temperature = min(max(as_shot_temp + temp_shift, 2000), 50000)
    return temperature, tint_shift


def _apply_session_bias(s: DevelopSettings, as_shot_temp: int | None,
                        exposure_bias: float, temp_bias: int) -> DevelopSettings:
    """Sesgo de sesión del fotógrafo: se suma al resultado de IA/armonía."""
    if exposure_bias:
        limit = SETTINGS.max_total_exposure
        s.exposure = round(min(max(s.exposure + exposure_bias, -limit), limit), 2)
    if temp_bias:
        if s.temperature is not None:
            s.temperature = min(max(s.temperature + temp_bias, 2000), 50000)
        elif as_shot_temp is not None:
            s.temperature = min(max(as_shot_temp + temp_bias, 2000), 50000)
        s.temp_shift += temp_bias
    return s


def compute_settings(metrics: GlobalMetrics, faces: list[Face],
                     rotation: float, ai: AIDecision | None,
                     as_shot_temp: int | None = None,
                     exposure_bias: float = 0.0,
                     temp_bias: int = 0) -> DevelopSettings:
    if ai is not None:
        masks = _masks_from_ai(faces, ai)
        has_crop = ai.crop is not None or ai.angle != 0.0
        crop = ai.crop or (0.0, 0.0, 1.0, 1.0)
        temperature, tint = _wb_from_shift(as_shot_temp, ai.temp_shift, ai.tint_shift)
        return _apply_session_bias(DevelopSettings(
            temp_shift=ai.temp_shift if temperature is not None else 0,
            temperature=temperature, tint=tint,
            exposure=ai.exposure, contrast=ai.contrast,
            highlights=ai.highlights, shadows=ai.shadows,
            whites=0, blacks=0,
            sharpness=sharpening_for(metrics.sharpness),
            luminance_smoothing=noise_reduction_for(metrics.iso),
            has_crop=has_crop,
            crop_left=crop[0], crop_top=crop[1],
            crop_right=crop[2], crop_bottom=crop[3],
            crop_angle=ai.angle,
            masks=masks, ai_used=True,
        ), as_shot_temp, exposure_bias, temp_bias)

    # Modo solo-local: correcciones técnicas conservadoras
    masks = [m for m in (face_mask_for(f) for f in faces) if m is not None]
    target = 0.45
    exposure = 0.0
    if metrics.mean_luma > 0.02:
        exposure = math.log2(target / metrics.mean_luma) * 0.5  # mitad del camino
        exposure = max(-SETTINGS.max_global_exposure,
                       min(SETTINGS.max_global_exposure, exposure))
    highlights = -30 if metrics.clip_highlights > 0.005 else 0
    shadows = 20 if metrics.clip_shadows > 0.005 else 0
    return _apply_session_bias(DevelopSettings(
        # El color solo lo decide la IA: en modo local el WB se queda "As Shot"
        temperature=None, tint=0,
        exposure=round(exposure, 2), contrast=0,
        highlights=highlights, shadows=shadows, whites=0, blacks=0,
        sharpness=sharpening_for(metrics.sharpness),
        luminance_smoothing=noise_reduction_for(metrics.iso),
        has_crop=rotation != 0.0,
        crop_left=0.0, crop_top=0.0, crop_right=1.0, crop_bottom=1.0,
        crop_angle=rotation,
        masks=masks, ai_used=False,
    ), as_shot_temp, exposure_bias, temp_bias)
