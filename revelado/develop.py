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


def face_mask_for(face: Face) -> RadialMask | None:
    if face.luma >= SETTINGS.face_lum_threshold:
        return None
    ev = math.log2(SETTINGS.face_lum_target / max(face.luma, 0.05))
    ev = min(ev, SETTINGS.max_face_ev)
    cx, cy = face.x + face.w / 2, face.y + face.h / 2
    hw, hh = face.w * MASK_EXPANSION / 2, face.h * MASK_EXPANSION / 2
    return RadialMask(
        left=max(0.0, cx - hw), top=max(0.0, cy - hh),
        right=min(1.0, cx + hw), bottom=min(1.0, cy + hh),
        exposure_ev=round(ev, 2),
        shadows=25,
    )


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


def compute_settings(metrics: GlobalMetrics, faces: list[Face],
                     rotation: float, ai: AIDecision | None,
                     as_shot_temp: int | None = None) -> DevelopSettings:
    masks = [m for m in (face_mask_for(f) for f in faces) if m is not None]

    if ai is not None:
        has_crop = ai.crop is not None or ai.angle != 0.0
        crop = ai.crop or (0.0, 0.0, 1.0, 1.0)
        temperature, tint = _wb_from_shift(as_shot_temp, ai.temp_shift, ai.tint_shift)
        return DevelopSettings(
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
        )

    # Modo solo-local: correcciones técnicas conservadoras
    target = 0.45
    exposure = 0.0
    if metrics.mean_luma > 0.02:
        exposure = math.log2(target / metrics.mean_luma) * 0.5  # mitad del camino
        exposure = max(-SETTINGS.max_global_exposure,
                       min(SETTINGS.max_global_exposure, exposure))
    highlights = -30 if metrics.clip_highlights > 0.005 else 0
    shadows = 20 if metrics.clip_shadows > 0.005 else 0
    return DevelopSettings(
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
    )
