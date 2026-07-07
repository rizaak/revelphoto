"""Culling de ráfagas: entre fotos casi idénticas, destacar la mejor.

Fotos consecutivas disparadas con muy poco tiempo entre sí (ráfaga) suelen
ser repeticiones del mismo instante. La mejor del grupo conserva su
puntuación y las demás bajan un escalón respecto a ella, para que el filtro
de estrellas de Lightroom enseñe una sola candidata por ráfaga. Igual que la
armonía, solo ajusta las decisiones de la IA (muta `analysis.ai`).
"""
from dataclasses import replace

from revelado.config import SETTINGS
from revelado.pipeline import PhotoAnalysis

_DEMOTE_REASON = "repetida en ráfaga; hay una mejor"


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
