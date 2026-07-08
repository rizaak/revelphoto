from pathlib import Path
from dataclasses import replace

from revelado.ai import AIDecision
from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics
from revelado.cull import rank_bursts
from revelado.exif import ExifData
from revelado.pipeline import PhotoAnalysis


def _metrics(sharpness=300.0):
    return GlobalMetrics(mean_luma=0.4, clip_shadows=0.0, clip_highlights=0.0,
                         wb_temp=5200, wb_tint=0, sharpness=sharpness, iso=200)


def _ai(rating=3, reason=""):
    return AIDecision(crop=None, angle=0.0, exposure=0.0, contrast=0,
                      highlights=0, shadows=0, temp_shift=0, tint_shift=0,
                      rating=rating, rating_reason=reason)


def _photo(name, ts, rating=3, face_sharp=100.0, reason=""):
    return PhotoAnalysis(
        Path(f"/s/{name}.CR3"),
        exif=ExifData(200, 1, 0, 0, color_temp=5200, timestamp=ts),
        metrics=_metrics(),
        faces=[Face(0.4, 0.3, 0.1, 0.1, luma=0.5, sharpness=face_sharp)],
        ai=_ai(rating, reason),
    )


def test_la_mejor_de_la_rafaga_conserva_su_puntuacion():
    a = _photo("A", 100.0, rating=4)
    b = _photo("B", 101.0, rating=4, face_sharp=50.0)  # misma nota, menos nítida
    c = _photo("C", 102.0, rating=2)
    rank_bursts([a, b, c])
    assert a.ai.rating == 4                     # la mejor, intacta
    assert b.ai.rating == 3                     # baja un escalón respecto a la mejor
    assert b.ai.rating_reason == "repetida en ráfaga; hay una mejor"
    assert c.ai.rating == 2                     # ya estaba por debajo: no cambia


def test_fotos_espaciadas_no_son_rafaga():
    a = _photo("A", 100.0, rating=4)
    b = _photo("B", 110.0, rating=4)  # 10 s después: otra toma, no ráfaga
    rank_bursts([a, b])
    assert a.ai.rating == 4 and b.ai.rating == 4


def test_rafagas_independientes():
    a1 = _photo("A1", 100.0, rating=5)
    a2 = _photo("A2", 101.0, rating=5, face_sharp=10.0)
    b1 = _photo("B1", 200.0, rating=3)
    b2 = _photo("B2", 201.0, rating=3, face_sharp=10.0)
    rank_bursts([a1, a2, b1, b2])
    assert (a1.ai.rating, a2.ai.rating) == (5, 4)
    assert (b1.ai.rating, b2.ai.rating) == (3, 2)


def test_motivo_existente_no_se_pisa():
    a = _photo("A", 100.0, rating=4)
    b = _photo("B", 101.0, rating=2, reason="ojos cerrados")
    rank_bursts([a, b])
    assert b.ai.rating == 2
    assert b.ai.rating_reason == "ojos cerrados"


def test_ignora_fotos_sin_ia_o_sin_hora():
    con_ia = _photo("A", 100.0, rating=4)
    sin_hora = _photo("B", 100.5, rating=4)
    sin_hora.exif = ExifData(200, 1, 0, 0, timestamp=None)
    sin_ia = _photo("C", 101.0)
    sin_ia.ai = None
    rank_bursts([con_ia, sin_hora, sin_ia])  # no debe fallar ni tocar nada
    assert con_ia.ai.rating == 4 and sin_hora.ai.rating == 4 and sin_ia.ai is None


def test_suelo_de_una_estrella():
    a = _photo("A", 100.0, rating=1)
    b = _photo("B", 101.0, rating=1, face_sharp=50.0)
    rank_bursts([a, b])
    assert b.ai.rating == 1  # nunca por debajo de 1


def _sesion(*sharps, global_sharp=None):
    fotos = []
    for i, fs in enumerate(sharps):
        p = _photo(f"S{i}", 100.0 + i * 60, rating=4, face_sharp=fs)
        if global_sharp is not None:
            p.metrics = _metrics(global_sharp[i])
        fotos.append(p)
    return fotos

def test_desenfocada_respecto_a_la_sesion_baja_a_2():
    from revelado.cull import flag_blurry
    fotos = _sesion(100.0, 110.0, 95.0, 5.0, global_sharp=[300, 310, 290, 8])
    flag_blurry(fotos)
    assert [f.ai.rating for f in fotos] == [4, 4, 4, 2]
    assert fotos[3].ai.rating_reason == "desenfocada o movida"

def test_nitidas_no_se_tocan_aunque_varien():
    from revelado.cull import flag_blurry
    fotos = _sesion(60.0, 120.0, 90.0)  # variación normal de una sesión
    flag_blurry(fotos)
    assert all(f.ai.rating == 4 for f in fotos)

def test_borrosa_pero_fondo_nitido_no_se_marca():
    """Solo cara baja (p.ej. cara pequeña y lejana): sin caída global, no se toca."""
    from revelado.cull import flag_blurry
    fotos = _sesion(100.0, 110.0, 12.0, global_sharp=[300, 310, 295])
    flag_blurry(fotos)
    assert fotos[2].ai.rating == 4

def test_motivo_existente_no_se_pisa_al_marcar_borrosa():
    from revelado.cull import flag_blurry
    fotos = _sesion(100.0, 110.0, 95.0, 5.0, global_sharp=[300, 310, 290, 8])
    fotos[3].ai = replace(fotos[3].ai, rating_reason="ojos cerrados")
    flag_blurry(fotos)
    assert fotos[3].ai.rating == 2
    assert fotos[3].ai.rating_reason == "ojos cerrados"

def test_sesion_de_una_foto_no_hace_nada():
    from revelado.cull import flag_blurry
    fotos = _sesion(5.0)
    flag_blurry(fotos)
    assert fotos[0].ai.rating == 4

def test_fotos_sin_ia_se_ignoran_al_marcar_borrosas():
    from revelado.cull import flag_blurry
    fotos = _sesion(100.0, 110.0, 5.0, global_sharp=[300, 310, 8])
    fotos[0].ai = None
    flag_blurry(fotos)  # no debe fallar
    assert fotos[2].ai.rating == 2
