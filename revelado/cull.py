"""Culling de ráfagas: entre fotos casi idénticas, destacar la mejor.

Fotos consecutivas disparadas con muy poco tiempo entre sí (ráfaga) suelen
ser repeticiones del mismo instante. La mejor del grupo conserva su
puntuación y las demás bajan un escalón respecto a ella, para que el filtro
de estrellas de Lightroom enseñe una sola candidata por ráfaga. Igual que la
armonía, solo ajusta las decisiones de la IA (muta `analysis.ai`).
"""
import statistics
from dataclasses import replace

from revelado.config import SETTINGS
from revelado.pipeline import PhotoAnalysis

_DEMOTE_REASON = "repetida en ráfaga; hay una mejor"
_BLURRY_REASON = "desenfocada o movida"


def _bursts(analyses: list[PhotoAnalysis]) -> list[list[PhotoAnalysis]]:
    usable = [a for a in analyses if a.ai is not None and a.exif is not None
              and a.exif.timestamp is not None]
    usable.sort(key=lambda a: a.exif.timestamp)
    groups: list[list[PhotoAnalysis]] = []
    for a in usable:
        if groups and a.exif.timestamp - groups[-1][-1].exif.timestamp <= SETTINGS.burst_gap:
            groups[-1].append(a)
        else:
            groups.append([a])
    return groups


def _quality(a: PhotoAnalysis) -> tuple:
    """Orden de calidad: puntuación de la IA y, de desempate, nitidez."""
    face_sharp = max((f.sharpness for f in a.faces), default=0.0)
    global_sharp = a.metrics.sharpness if a.metrics is not None else 0.0
    return (a.ai.rating, face_sharp, global_sharp)


def flag_blurry(analyses: list[PhotoAnalysis]) -> None:
    """Marca fotos desenfocadas/movidas comparándolas con SU sesión.

    La varianza del laplaciano no tiene escala absoluta (depende del
    contenido y el grano del ISO), pero dentro de una sesión el grano y las
    escenas son comparables: una foto muy por debajo de la mediana está mal.
    Se exige la caída en la nitidez global Y en la de cara (si hay caras)
    para no castigar caras pequeñas o lejanas con fondo nítido.
    """
    usable = [a for a in analyses if a.ai is not None and a.metrics is not None]
    if len(usable) < 2:
        return  # ponytail: sin sesión de referencia (1 foto) no se opina
    med_global = statistics.median(a.metrics.sharpness for a in usable)
    con_caras = [max(f.sharpness for f in a.faces) for a in usable if a.faces]
    med_face = statistics.median(con_caras) if con_caras else 0.0
    floor = SETTINGS.blur_ratio
    if med_global <= 0:
        return
    for a in usable:
        if a.metrics.sharpness >= floor * med_global:
            continue
        if a.faces and med_face > 0 and \
                max(f.sharpness for f in a.faces) >= floor * med_face:
            continue
        if a.ai.rating > 2:
            a.ai = replace(a.ai, rating=2,
                           rating_reason=a.ai.rating_reason or _BLURRY_REASON)


def rank_bursts(analyses: list[PhotoAnalysis]) -> None:
    for group in _bursts(analyses):
        if len(group) < 2:
            continue
        best = max(group, key=_quality)
        for a in group:
            if a is best:
                continue
            demoted = min(a.ai.rating, max(1, best.ai.rating - 1))
            if demoted < a.ai.rating:
                a.ai = replace(a.ai, rating=demoted,
                               rating_reason=a.ai.rating_reason or _DEMOTE_REASON)
