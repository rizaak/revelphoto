import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class PreviewError(Exception):
    """No se pudo extraer la vista previa JPEG del RAW."""


@dataclass(frozen=True)
class ExifData:
    iso: int
    orientation: int
    width: int
    height: int


def _run(args: list[str]) -> bytes:
    result = subprocess.run(args, capture_output=True, timeout=30)
    return result.stdout


def _int_tag(tags: dict, key: str, default: int) -> int:
    value = tags.get(key)
    return default if value is None else int(value)


def read_exif(raw_path: Path) -> ExifData:
    out = _run(["exiftool", "-j", "-n", "-ISO", "-Orientation",
                "-ImageWidth", "-ImageHeight", str(raw_path)])
    try:
        tags = json.loads(out.decode() or "[{}]")[0]
    except (json.JSONDecodeError, IndexError):
        tags = {}
    return ExifData(
        iso=_int_tag(tags, "ISO", 100),
        orientation=_int_tag(tags, "Orientation", 1),
        width=_int_tag(tags, "ImageWidth", 0),
        height=_int_tag(tags, "ImageHeight", 0),
    )


def extract_preview_jpeg(raw_path: Path) -> bytes:
    for tag in ("-JpgFromRaw", "-PreviewImage"):
        data = _run(["exiftool", "-b", tag, str(raw_path)])
        if data.startswith(b"\xff\xd8"):
            return data
    raise PreviewError(f"Sin vista previa embebida: {raw_path.name}")
