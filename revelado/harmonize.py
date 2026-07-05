"""Armonía de sesión: mismo look dentro de cada escena.

Agrupa las fotos por situación de luz (hora de captura y WB de cámara) y,
dentro de cada grupo, unifica color y tono (mediana de las decisiones de la
IA) mientras la exposición se calcula por foto para igualar el brillo final
aunque el diafragma/obturador variara entre tomas. Recorte y enderezado
siguen siendo individuales.
"""
import math
from dataclasses import replace
from statistics import median

from revelado.config import SETTINGS
from revelado.pipeline import PhotoAnalysis


def _same_scene(prev: PhotoAnalysis, cur: PhotoAnalysis) -> bool:
    tp, tc = prev.exif.timestamp, cur.exif.timestamp
    if tp is not None and tc is not None and abs(tc - tp) > SETTINGS.harmony_time_gap:
        return False
    wp, wc = prev.exif.color_temp, cur.exif.color_temp
    if wp is not None and wc is not None and abs(wc - wp) > SETTINGS.harmony_wb_delta:
        return False
    return True


def _groups(analyses: list[PhotoAnalysis]) -> list[list[PhotoAnalysis]]:
    usable = [a for a in analyses if a.ai is not None and a.metrics is not None
              and a.exif is not None]
    usable.sort(key=lambda a: (a.exif.timestamp is None, a.exif.timestamp or 0.0))
    groups: list[list[PhotoAnalysis]] = []
    for a in usable:
        if groups and _same_scene(groups[-1][-1], a):
            groups[-1].append(a)
        else:
            groups.append([a])
    return groups


def harmonize(analyses: list[PhotoAnalysis]) -> None:
    """Muta las decisiones de la IA para unificar el look por escena."""
    for group in _groups(analyses):
        if len(group) < 2:
            continue
        # Color: Kelvin ABSOLUTO único por escena (con WB automático cada foto
        # trae una base distinta; igualar solo el desplazamiento no basta)
        median_shift = int(median(a.ai.temp_shift for a in group))
        bases = [a.exif.color_temp for a in group if a.exif.color_temp]
        group_kelvin = int(median(bases)) + median_shift if bases else None
        tint_shift = int(median(a.ai.tint_shift for a in group))
        contrast = int(median(a.ai.contrast for a in group))
        highlights = int(median(a.ai.highlights for a in group))
        shadows = int(median(a.ai.shadows for a in group))
        # Brillo final objetivo: el que la IA pretendía de mediana en la escena
        target = median(a.metrics.mean_luma * 2 ** a.ai.exposure for a in group)
        limit = SETTINGS.max_global_exposure
        for a in group:
            if group_kelvin is not None and a.exif.color_temp:
                temp_shift = group_kelvin - a.exif.color_temp
            else:
                temp_shift = median_shift
            exposure = math.log2(max(target, 0.02) / max(a.metrics.mean_luma, 0.02))
            a.ai = replace(
                a.ai,
                temp_shift=temp_shift, tint_shift=tint_shift,
                contrast=contrast, highlights=highlights, shadows=shadows,
                exposure=round(max(-limit, min(limit, exposure)), 2),
            )
