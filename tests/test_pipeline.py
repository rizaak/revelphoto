from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from revelado.ai import AIDecision, AIUnavailable
from revelado.exif import ExifData, PreviewError
from revelado.pipeline import process_photo

EXIF = ExifData(iso=400, orientation=1, width=6000, height=4000)
IMG = np.full((200, 300, 3), 128, dtype=np.uint8)
AI = AIDecision(crop=None, angle=0.5, exposure=0.2, contrast=5, highlights=-10,
                shadows=15, temperature=5400, tint=4)


def _patches(**overrides):
    base = {
        "read_exif": MagicMock(return_value=EXIF),
        "extract_preview_jpeg": MagicMock(return_value=b"\xff\xd8x"),
        "decode_upright": MagicMock(return_value=IMG),
        "detect_faces": MagicMock(return_value=[]),
        "estimate_rotation": MagicMock(return_value=0.5),
        "decide": MagicMock(return_value=AI),
    }
    base.update(overrides)
    return base


def _run(tmp_path, overwrite=False, client="cliente", **overrides):
    raw = tmp_path / "IMG_1.CR3"
    raw.write_bytes(b"fake")
    mocks = _patches(**overrides)
    with patch.multiple("revelado.pipeline", **mocks):
        return process_photo(raw, overwrite=overwrite, client=client), raw


def test_happy_path_writes_xmp(tmp_path):
    result, raw = _run(tmp_path)
    assert result.status == "done"
    assert (tmp_path / "IMG_1.xmp").exists()
    assert result.settings is not None and result.settings.ai_used


def test_ai_failure_degrades_to_local(tmp_path):
    result, _ = _run(tmp_path, decide=MagicMock(side_effect=AIUnavailable("caída")))
    assert result.status == "done_local_only"
    assert (tmp_path / "IMG_1.xmp").exists()
    assert not result.settings.ai_used


def test_no_client_is_local_only(tmp_path):
    result, _ = _run(tmp_path, client=None)
    assert result.status == "done_local_only"


def test_existing_xmp_skipped(tmp_path):
    (tmp_path / "IMG_1.xmp").write_text("previo")
    result, _ = _run(tmp_path)
    assert result.status == "skipped_existing"
    assert (tmp_path / "IMG_1.xmp").read_text() == "previo"  # intacto


def test_overwrite_replaces(tmp_path):
    (tmp_path / "IMG_1.xmp").write_text("previo")
    result, _ = _run(tmp_path, overwrite=True)
    assert result.status == "done"
    assert "crs" in (tmp_path / "IMG_1.xmp").read_text()


def test_preview_error_is_error(tmp_path):
    result, _ = _run(tmp_path, extract_preview_jpeg=MagicMock(side_effect=PreviewError("sin preview")))
    assert result.status == "error" and "preview" in result.message.lower()
