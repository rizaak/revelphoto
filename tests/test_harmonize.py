import math
from pathlib import Path

from revelado.ai import AIDecision
from revelado.analysis.metrics import GlobalMetrics
from revelado.exif import ExifData
from revelado.harmonize import harmonize
from revelado.pipeline import PhotoAnalysis


def _metrics(luma):
    return GlobalMetrics(mean_luma=luma, clip_shadows=0.0, clip_highlights=0.0,
                         wb_temp=5500, wb_tint=0, sharpness=200.0, iso=400)


def _ai(exposure=0.0, temp_shift=0, contrast=0):
    return AIDecision(crop=None, angle=0.0, exposure=exposure, contrast=contrast,
                      highlights=0, shadows=0, temp_shift=temp_shift, tint_shift=0)


def _photo(name, ts, wb=4200, luma=0.4, **ai_kwargs):
    return PhotoAnalysis(
        Path(f"/x/{name}.CR3"),
        exif=ExifData(iso=400, orientation=1, width=0, height=0,
                      color_temp=wb, timestamp=ts),
        metrics=_metrics(luma), ai=_ai(**ai_kwargs))


def test_group_gets_median_color_and_tone():
    photos = [_photo("a", 100, temp_shift=0, contrast=5),
              _photo("b", 130, temp_shift=200, contrast=10),
              _photo("c", 160, temp_shift=400, contrast=30)]
    harmonize(photos)
    assert all(p.ai.temp_shift == 200 for p in photos)
    assert all(p.ai.contrast == 10 for p in photos)


def test_exposure_equalizes_final_brightness():
    # Misma escena, una foto salió más oscura (obturador distinto)
    photos = [_photo("a", 100, luma=0.40, exposure=0.0),
              _photo("b", 120, luma=0.20, exposure=0.0),
              _photo("c", 140, luma=0.40, exposure=0.0)]
    harmonize(photos)
    rendered = [p.metrics.mean_luma * 2 ** p.ai.exposure for p in photos]
    assert max(rendered) - min(rendered) < 0.02  # brillo final igualado
    assert photos[1].ai.exposure > 0.5           # la oscura sube


def test_time_gap_splits_scenes():
    photos = [_photo("a", 100, temp_shift=0),
              _photo("b", 130, temp_shift=0),
              _photo("c", 5000, temp_shift=400),   # 80 min después: otra escena
              _photo("d", 5030, temp_shift=400)]
    harmonize(photos)
    assert photos[0].ai.temp_shift == 0 and photos[2].ai.temp_shift == 400


def test_camera_wb_change_splits_scenes():
    photos = [_photo("a", 100, wb=4200, temp_shift=0),
              _photo("b", 120, wb=4200, temp_shift=0),
              _photo("c", 140, wb=5600, temp_shift=300),  # cambió la luz
              _photo("d", 160, wb=5600, temp_shift=300)]
    harmonize(photos)
    assert photos[0].ai.temp_shift == 0 and photos[2].ai.temp_shift == 300


def test_single_photo_and_failed_analyses_untouched():
    solo = _photo("a", 100, exposure=0.3)
    failed = PhotoAnalysis(Path("/x/err.CR3"), error="boom")
    skipped = PhotoAnalysis(Path("/x/skip.CR3"), skipped=True)
    harmonize([solo, failed, skipped])
    assert solo.ai.exposure == 0.3 and failed.ai is None
