import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from revelado.exif import ExifData, PreviewError, extract_preview_jpeg, read_exif


def _completed(stdout: bytes, code: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=b"")


def test_read_exif_parses_json():
    payload = json.dumps([{"ISO": 800, "Orientation": 6, "ImageWidth": 6000, "ImageHeight": 4000}]).encode()
    with patch("revelado.exif.subprocess.run", return_value=_completed(payload)) as run:
        data = read_exif(Path("/x/IMG_0001.CR3"))
    assert data == ExifData(iso=800, orientation=6, width=6000, height=4000)
    assert "-j" in run.call_args[0][0] and "-n" in run.call_args[0][0]


def test_read_exif_defaults_when_missing():
    payload = json.dumps([{}]).encode()
    with patch("revelado.exif.subprocess.run", return_value=_completed(payload)):
        data = read_exif(Path("/x/a.cr2"))
    assert data == ExifData(iso=100, orientation=1, width=0, height=0)


def test_extract_preview_prefers_jpgfromraw():
    with patch("revelado.exif.subprocess.run", return_value=_completed(b"\xff\xd8JPEGDATA")) as run:
        out = extract_preview_jpeg(Path("/x/a.cr3"))
    assert out.startswith(b"\xff\xd8")
    assert "-JpgFromRaw" in run.call_args[0][0]


def test_extract_preview_falls_back_then_raises():
    with patch("revelado.exif.subprocess.run", return_value=_completed(b"")):
        with pytest.raises(PreviewError):
            extract_preview_jpeg(Path("/x/a.cr3"))


def test_read_exif_color_temperature():
    payload = json.dumps([{"ISO": 200, "Orientation": 1, "ImageWidth": 6000,
                           "ImageHeight": 4000, "ColorTemperature": 5200}]).encode()
    with patch("revelado.exif.subprocess.run", return_value=_completed(payload)):
        data = read_exif(Path("/x/a.cr3"))
    assert data.color_temp == 5200


def test_read_exif_color_temperature_missing_is_none():
    payload = json.dumps([{"ISO": 200}]).encode()
    with patch("revelado.exif.subprocess.run", return_value=_completed(payload)):
        assert read_exif(Path("/x/a.cr3")).color_temp is None
