# Revelado Automático para Lightroom Classic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local web app (Python/FastAPI at `localhost:8420`) that analyzes Canon RAW files (CR2/CR3) with local CV + the Claude API and writes Lightroom Classic XMP sidecars (exposure/color, crop/straighten, sharpening/NR, per-face radial masks), with live progress and macOS notification.

**Architecture:** FastAPI backend serving a vanilla HTML/JS frontend. Per-photo pipeline: exiftool extracts the embedded JPEG preview → local analysis (OpenCV YuNet faces, histogram, gray-world WB, Laplacian sharpness, Hough horizon) → one Claude API call (vision + structured JSON) for aesthetic crop/fine-tune → XMP sidecar written next to the RAW. Jobs run concurrently with SSE progress events.

**Tech Stack:** Python 3.11+, FastAPI + Uvicorn, `anthropic` SDK (model `claude-haiku-4-5`, base64 image blocks, `output_config.format` json_schema), OpenCV (YuNet ONNX), NumPy, exiftool (subprocess), pytest + httpx TestClient. Frontend: plain HTML/CSS/JS with `EventSource` (SSE).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-04-revelado-automatico-lightroom-design.md`. Read it before starting.
- **Never modify RAW files or any Lightroom catalog.** Only `.xmp` sidecars are written.
- **Never overwrite an existing `.xmp` unless `overwrite=True`** (user-confirmed). Default behavior raises/skips.
- Face rule: faces with mean luma < **0.35** get a **local radial mask** raising exposure toward **0.50**, capped at **+1.5 EV**; global exposure stays conservative (|exposure| ≤ **1.0 EV**).
- API failure ⇒ **local-only mode** (photo still processed, status `done_local_only`), never a batch failure.
- Model ID is exactly `claude-haiku-4-5` (no date suffix). Only a ~1500px preview is ever sent to the API.
- Port **8420**. All numeric defaults live in `revelado/config.py` — no magic numbers elsewhere.
- Python 3.11+. Tests run with `python -m pytest`. Commit after every task.
- All user-facing strings (frontend, notifications, API error messages) in **Spanish**.

## File Structure

```
revelado/
  __init__.py
  config.py            # Settings dataclass (thresholds, model, port, paths)
  exif.py              # exiftool wrapper: EXIF read + embedded preview extraction
  imageio.py           # JPEG decode + EXIF-orientation upright + resize
  analysis/
    __init__.py
    metrics.py         # histogram/luma stats, WB estimate, sharpness, ISO→NR
    faces.py           # YuNet detection + per-face luminance
    horizon.py         # Hough-based rotation estimate
  ai.py                # Claude API call (vision + structured JSON) + clamping
  develop.py           # DevelopSettings/RadialMask + compute_settings()
  xmp.py               # XMP sidecar render/write/delete
  pipeline.py          # process_photo() orchestration
  jobs.py              # JobManager: async queue, per-photo status, SSE bus
  notify.py            # macOS notification via osascript
  server.py            # FastAPI app + routes
  static/
    index.html
    app.js
    style.css
models/                # face_detection_yunet_2023mar.onnx (downloaded by setup.sh)
scripts/setup.sh       # exiftool + venv + pip + YuNet model download
run.py                 # uvicorn entry point
requirements.txt
tests/
  test_config.py test_exif.py test_imageio.py test_metrics.py test_faces.py
  test_horizon.py test_ai.py test_develop.py test_xmp.py test_pipeline.py
  test_jobs.py test_server.py
  conftest.py          # shared fixtures (synthetic images, tmp raws)
samples/               # (gitignored) user drops real CR2/CR3 here for integration tests
```

---

### Task 1: Scaffolding + config

**Files:**
- Create: `requirements.txt`, `revelado/__init__.py`, `revelado/config.py`, `revelado/analysis/__init__.py`, `scripts/setup.sh`, `.gitignore`, `tests/test_config.py`

**Interfaces:**
- Produces: `revelado.config.SETTINGS` — frozen dataclass instance with fields listed below; every later task imports from here.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path

from revelado.config import SETTINGS


def test_defaults():
    assert SETTINGS.port == 8420
    assert SETTINGS.model == "claude-haiku-4-5"
    assert SETTINGS.preview_long_edge == 1500
    assert SETTINGS.face_lum_threshold == 0.35
    assert SETTINGS.face_lum_target == 0.50
    assert SETTINGS.max_face_ev == 1.5
    assert SETTINGS.max_global_exposure == 1.0
    assert SETTINGS.raw_extensions == (".cr2", ".cr3")
    assert isinstance(SETTINGS.yunet_model_path, Path)
    assert SETTINGS.yunet_model_path.name == "face_detection_yunet_2023mar.onnx"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'revelado'`

- [ ] **Step 3: Write the implementation**

```python
# revelado/__init__.py
```
(empty file; also create empty `revelado/analysis/__init__.py`)

```python
# revelado/config.py
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    port: int = 8420
    model: str = "claude-haiku-4-5"
    preview_long_edge: int = 1500
    thumb_long_edge: int = 400
    face_lum_threshold: float = 0.35
    face_lum_target: float = 0.50
    max_face_ev: float = 1.5
    max_global_exposure: float = 1.0
    max_crop_angle: float = 10.0
    api_concurrency: int = 4
    worker_concurrency: int = 4
    api_max_tokens: int = 1024
    raw_extensions: tuple[str, ...] = (".cr2", ".cr3")
    yunet_model_path: Path = _ROOT / "models" / "face_detection_yunet_2023mar.onnx"
    cache_dir: Path = Path.home() / ".cache" / "revelado"


SETTINGS = Settings()
```

```
# requirements.txt
fastapi>=0.110
uvicorn>=0.29
anthropic>=0.92
opencv-python-headless>=4.9
numpy>=1.26
pytest>=8.0
httpx>=0.27
```

```bash
# scripts/setup.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v exiftool >/dev/null; then
  echo "Instalando exiftool con Homebrew..."
  brew install exiftool
fi

if [ ! -d .venv ]; then python3 -m venv .venv; fi
./.venv/bin/pip install -q -r requirements.txt

mkdir -p models
MODEL=models/face_detection_yunet_2023mar.onnx
if [ ! -f "$MODEL" ]; then
  echo "Descargando modelo de detección de caras (YuNet)..."
  curl -fsSL -o "$MODEL" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi

echo "Listo. Ejecuta: ./.venv/bin/python run.py"
```

```
# .gitignore
.venv/
__pycache__/
models/*.onnx
samples/
.pytest_cache/
```

- [ ] **Step 4: Set up environment and run test**

Run: `bash scripts/setup.sh && ./.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (1 passed). From here on, always use `./.venv/bin/python -m pytest`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: scaffolding, config y setup"
```

---

### Task 2: exiftool wrapper (`exif.py`)

**Files:**
- Create: `revelado/exif.py`, `tests/test_exif.py`

**Interfaces:**
- Consumes: `SETTINGS` (nothing else).
- Produces:
  - `ExifData` dataclass: `iso: int`, `orientation: int` (EXIF 1–8), `width: int`, `height: int`
  - `read_exif(raw_path: Path) -> ExifData` — runs `exiftool -j -n -ISO -Orientation -ImageWidth -ImageHeight <file>`
  - `extract_preview_jpeg(raw_path: Path) -> bytes` — tries `exiftool -b -JpgFromRaw`, falls back to `-b -PreviewImage`; raises `PreviewError` if both empty
  - `PreviewError(Exception)`

- [ ] **Step 1: Write the failing tests** (mock `subprocess.run` — no real RAW needed)

```python
# tests/test_exif.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_exif.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# revelado/exif.py
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


def read_exif(raw_path: Path) -> ExifData:
    out = _run(["exiftool", "-j", "-n", "-ISO", "-Orientation",
                "-ImageWidth", "-ImageHeight", str(raw_path)])
    try:
        tags = json.loads(out.decode() or "[{}]")[0]
    except (json.JSONDecodeError, IndexError):
        tags = {}
    return ExifData(
        iso=int(tags.get("ISO") or 100),
        orientation=int(tags.get("Orientation") or 1),
        width=int(tags.get("ImageWidth") or 0),
        height=int(tags.get("ImageHeight") or 0),
    )


def extract_preview_jpeg(raw_path: Path) -> bytes:
    for tag in ("-JpgFromRaw", "-PreviewImage"):
        data = _run(["exiftool", "-b", tag, str(raw_path)])
        if data.startswith(b"\xff\xd8"):
            return data
    raise PreviewError(f"Sin vista previa embebida: {raw_path.name}")
```

Note: `subprocess.run` is referenced as `revelado.exif.subprocess.run` so the mocks in the tests patch it; keep the `import subprocess` module-level.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_exif.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/exif.py tests/test_exif.py && git commit -m "feat: wrapper de exiftool (EXIF + preview embebida)"
```

---

### Task 3: image decode + orientation (`imageio.py`)

**Files:**
- Create: `revelado/imageio.py`, `tests/test_imageio.py`, `tests/conftest.py`

**Interfaces:**
- Produces:
  - `decode_upright(jpeg: bytes, orientation: int, max_edge: int) -> np.ndarray` — BGR uint8, EXIF orientation applied (upright), long edge ≤ `max_edge`
  - `encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes`
- Consumed by: `pipeline.py` (previews for analysis/AI) and `server.py` (thumbnails).

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
import cv2
import numpy as np
import pytest


@pytest.fixture
def gradient_img():
    """Imagen 300x200 BGR con gradiente horizontal de negro a blanco."""
    img = np.tile(np.linspace(0, 255, 300, dtype=np.uint8), (200, 1))
    return cv2.merge([img, img, img])


def to_jpeg(img):
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()
```

```python
# tests/test_imageio.py
import numpy as np

from revelado.imageio import decode_upright, encode_jpeg
from tests.conftest import to_jpeg


def test_decode_no_rotation(gradient_img):
    out = decode_upright(to_jpeg(gradient_img), orientation=1, max_edge=1500)
    assert out.shape[:2] == (200, 300)


def test_decode_orientation_6_rotates_90cw(gradient_img):
    out = decode_upright(to_jpeg(gradient_img), orientation=6, max_edge=1500)
    assert out.shape[:2] == (300, 200)  # landscape -> portrait


def test_decode_resizes_long_edge(gradient_img):
    out = decode_upright(to_jpeg(gradient_img), orientation=1, max_edge=150)
    assert max(out.shape[:2]) == 150


def test_encode_roundtrip(gradient_img):
    data = encode_jpeg(gradient_img)
    assert data.startswith(b"\xff\xd8")
    out = decode_upright(data, orientation=1, max_edge=1500)
    assert out.shape == gradient_img.shape
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_imageio.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/imageio.py
import cv2
import numpy as np

# Rotaciones por valor EXIF Orientation (solo las de cámara: 1,3,6,8)
_ROTATIONS = {
    3: cv2.ROTATE_180,
    6: cv2.ROTATE_90_CLOCKWISE,
    8: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def decode_upright(jpeg: bytes, orientation: int, max_edge: int) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("JPEG ilegible")
    rot = _ROTATIONS.get(orientation)
    if rot is not None:
        img = cv2.rotate(img, rot)
    h, w = img.shape[:2]
    long_edge = max(h, w)
    if long_edge > max_edge:
        scale = max_edge / long_edge
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("No se pudo codificar JPEG")
    return buf.tobytes()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_imageio.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/imageio.py tests/ && git commit -m "feat: decodificación de previews con orientación EXIF"
```

---

### Task 4: global metrics (`analysis/metrics.py`)

**Files:**
- Create: `revelado/analysis/metrics.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `GlobalMetrics` dataclass: `mean_luma: float` (0–1), `clip_shadows: float`, `clip_highlights: float`, `wb_temp: int` (Kelvin), `wb_tint: int`, `sharpness: float`, `iso: int`
  - `compute_metrics(img_bgr, iso: int) -> GlobalMetrics`
  - `sharpening_for(sharpness: float) -> int` — crs Sharpness 25–60 (soft image ⇒ more)
  - `noise_reduction_for(iso: int) -> int` — crs LuminanceSmoothing 0–40

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metrics.py
import cv2
import numpy as np

from revelado.analysis.metrics import (GlobalMetrics, compute_metrics,
                                       noise_reduction_for, sharpening_for)


def _flat(value, shape=(100, 100, 3)):
    return np.full(shape, value, dtype=np.uint8)


def test_mean_luma_midgray():
    m = compute_metrics(_flat(128), iso=100)
    assert 0.45 < m.mean_luma < 0.55


def test_clipping_detected():
    img = _flat(0)
    img[:, 50:] = 255
    m = compute_metrics(img, iso=100)
    assert m.clip_shadows > 0.4 and m.clip_highlights > 0.4


def test_wb_neutral_gray_is_daylight():
    m = compute_metrics(_flat(128), iso=100)
    assert 4500 <= m.wb_temp <= 6500
    assert -20 <= m.wb_tint <= 20


def test_wb_blue_cast_lowers_temp():
    img = _flat(128).astype(np.int16)
    img[:, :, 0] += 60  # canal azul dominante (BGR)
    m = compute_metrics(np.clip(img, 0, 255).astype(np.uint8), iso=100)
    neutral = compute_metrics(_flat(128), iso=100)
    assert m.wb_temp > neutral.wb_temp  # corregir azul => subir temperatura


def test_sharpness_blur_ranks_lower(gradient_img):
    noise = np.random.default_rng(0).integers(0, 255, gradient_img.shape, dtype=np.uint8)
    sharp = compute_metrics(noise, iso=100).sharpness
    blurred = compute_metrics(cv2.GaussianBlur(noise, (15, 15), 5), iso=100).sharpness
    assert sharp > blurred


def test_sharpening_and_nr_ranges():
    assert 25 <= sharpening_for(5.0) <= 60
    assert sharpening_for(5.0) >= sharpening_for(500.0)
    assert noise_reduction_for(100) == 0
    assert noise_reduction_for(3200) > 0
    assert noise_reduction_for(25600) <= 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_metrics.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/analysis/metrics.py
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class GlobalMetrics:
    mean_luma: float
    clip_shadows: float
    clip_highlights: float
    wb_temp: int
    wb_tint: int
    sharpness: float
    iso: int


def compute_metrics(img_bgr: np.ndarray, iso: int) -> GlobalMetrics:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    luma = gray.astype(np.float64) / 255.0
    b, g, r = (img_bgr[:, :, i].mean() for i in range(3))

    # Gris-mundo: desviación de R/B respecto a G, mapeada alrededor de 5500K.
    # +600K por cada 10% de dominancia azul (cast frío => subir temperatura).
    eps = 1e-6
    blue_bias = (b - r) / (g + eps)          # >0: cast azul, <0: cast cálido
    green_bias = (g - (r + b) / 2) / (g + eps)  # >0: cast verde => tint magenta
    wb_temp = int(np.clip(5500 + blue_bias * 6000, 3000, 9000))
    wb_tint = int(np.clip(green_bias * 150, -50, 50))

    return GlobalMetrics(
        mean_luma=float(luma.mean()),
        clip_shadows=float((gray <= 2).mean()),
        clip_highlights=float((gray >= 253).mean()),
        wb_temp=wb_temp,
        wb_tint=wb_tint,
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        iso=iso,
    )


def sharpening_for(sharpness: float) -> int:
    # Imagen blanda (varianza baja) => más enfoque; nítida => enfoque base.
    if sharpness < 50:
        return 60
    if sharpness < 200:
        return 45
    return 30


def noise_reduction_for(iso: int) -> int:
    if iso <= 400:
        return 0
    if iso <= 1600:
        return 15
    if iso <= 6400:
        return 25
    return 40
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_metrics.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/analysis/metrics.py tests/test_metrics.py && git commit -m "feat: métricas globales (luma, WB, nitidez, ruido)"
```

---

### Task 5: face detection (`analysis/faces.py`)

**Files:**
- Create: `revelado/analysis/faces.py`, `tests/test_faces.py`

**Interfaces:**
- Produces:
  - `Face` dataclass: `x, y, w, h: float` (normalized 0–1 in the upright image), `luma: float` (0–1 mean over the central 60% of the box)
  - `detect_faces(img_bgr, model_path: Path) -> list[Face]` — YuNet via `cv2.FaceDetectorYN_create`; returns `[]` if model file missing (logged warning, never crashes)
  - `face_luma(img_bgr, x, y, w, h) -> float` (pure helper, unit-testable without the model)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_faces.py
from pathlib import Path

import numpy as np
import pytest

from revelado.analysis.faces import detect_faces, face_luma
from revelado.config import SETTINGS


def test_face_luma_dark_and_bright_regions():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:50, :] = 230  # mitad superior clara
    bright = face_luma(img, x=0.1, y=0.05, w=0.3, h=0.3)
    dark = face_luma(img, x=0.1, y=0.6, w=0.3, h=0.3)
    assert bright > 0.8 and dark < 0.1


def test_face_luma_clamps_out_of_bounds():
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    assert 0.0 <= face_luma(img, x=0.9, y=0.9, w=0.5, h=0.5) <= 1.0


def test_detect_faces_missing_model_returns_empty(tmp_path):
    img = np.full((200, 200, 3), 128, dtype=np.uint8)
    assert detect_faces(img, tmp_path / "nope.onnx") == []


@pytest.mark.skipif(not SETTINGS.yunet_model_path.exists(), reason="modelo YuNet no descargado")
def test_detect_faces_runs_on_blank_image():
    img = np.full((400, 400, 3), 128, dtype=np.uint8)
    faces = detect_faces(img, SETTINGS.yunet_model_path)
    assert faces == []  # sin caras en imagen plana
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_faces.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/analysis/faces.py
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    luma: float


def face_luma(img_bgr: np.ndarray, x: float, y: float, w: float, h: float) -> float:
    """Luminancia media (0-1) del 60% central del recuadro normalizado."""
    ih, iw = img_bgr.shape[:2]
    # Contraer al 60% central para evitar pelo/fondo
    cx, cy = x + w / 2, y + h / 2
    w, h = w * 0.6, h * 0.6
    x0 = max(0, int((cx - w / 2) * iw))
    y0 = max(0, int((cy - h / 2) * ih))
    x1 = min(iw, int((cx + w / 2) * iw))
    y1 = min(ih, int((cy + h / 2) * ih))
    if x1 <= x0 or y1 <= y0:
        return 0.5
    region = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float(region.mean() / 255.0)


def detect_faces(img_bgr: np.ndarray, model_path: Path) -> list[Face]:
    if not model_path.exists():
        log.warning("Modelo YuNet no encontrado en %s; sin detección de caras", model_path)
        return []
    ih, iw = img_bgr.shape[:2]
    detector = cv2.FaceDetectorYN_create(str(model_path), "", (iw, ih), score_threshold=0.7)
    _, dets = detector.detect(img_bgr)
    faces: list[Face] = []
    if dets is None:
        return faces
    for d in dets:
        x, y, w, h = (float(v) for v in d[:4])
        nx, ny, nw, nh = x / iw, y / ih, w / iw, h / ih
        faces.append(Face(x=nx, y=ny, w=nw, h=nh,
                          luma=face_luma(img_bgr, nx, ny, nw, nh)))
    return faces
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_faces.py -v`
Expected: PASS (4 passed, or 3 passed + 1 skipped if the model isn't downloaded)

- [ ] **Step 5: Commit**

```bash
git add revelado/analysis/faces.py tests/test_faces.py && git commit -m "feat: detección de caras YuNet con luminancia por rostro"
```

---

### Task 6: horizon/rotation (`analysis/horizon.py`)

**Files:**
- Create: `revelado/analysis/horizon.py`, `tests/test_horizon.py`

**Interfaces:**
- Produces: `estimate_rotation(img_bgr) -> float` — degrees to rotate to level (positive = rotate counterclockwise in LR terms, i.e. `crs:CropAngle` sign convention: the value we return is written directly as CropAngle). Returns `0.0` when no confident near-horizontal lines. Clamped to ±7°.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_horizon.py
import cv2
import numpy as np

from revelado.analysis.horizon import estimate_rotation


def _line_image(angle_deg: float) -> np.ndarray:
    """Imagen 400x400 con una línea 'horizonte' inclinada angle_deg."""
    img = np.full((400, 400, 3), 40, dtype=np.uint8)
    t = np.tan(np.radians(angle_deg))
    p1 = (0, int(200 + 200 * t))
    p2 = (400, int(200 - 200 * t))
    cv2.line(img, p1, p2, (220, 220, 220), 3)
    return img


def test_level_horizon_near_zero():
    assert abs(estimate_rotation(_line_image(0.0))) < 0.3


def test_tilted_horizon_detected_within_half_degree():
    est = estimate_rotation(_line_image(3.0))
    assert abs(abs(est) - 3.0) < 0.5 and est != 0.0


def test_no_lines_returns_zero():
    img = np.full((400, 400, 3), 128, dtype=np.uint8)
    assert estimate_rotation(img) == 0.0


def test_clamped_to_seven_degrees():
    assert abs(estimate_rotation(_line_image(6.5))) <= 7.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_horizon.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/analysis/horizon.py
import cv2
import numpy as np

MAX_ANGLE = 7.0  # grados; más allá se asume intencional


def estimate_rotation(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    min_len = int(min(img_bgr.shape[:2]) * 0.3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=80,
                            minLineLength=min_len, maxLineGap=10)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        if x2 == x1:
            continue
        ang = np.degrees(np.arctan2(y1 - y2, x2 - x1))  # y invertida (imagen)
        if abs(ang) <= MAX_ANGLE:  # solo casi-horizontales
            angles.append(ang)
    if not angles:
        return 0.0
    med = float(np.median(angles))
    # CropAngle en LR: valor positivo rota la imagen en sentido horario para nivelar
    return float(np.clip(-med, -MAX_ANGLE, MAX_ANGLE))
```

Note: the returned sign convention is validated visually in the acceptance task (Task 13); if a tilted photo comes out doubled instead of leveled in Lightroom, flip the sign in this one function — the tests only assert magnitude.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_horizon.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/analysis/horizon.py tests/test_horizon.py && git commit -m "feat: estimación de horizonte con Hough"
```

---

### Task 7: Claude API decision (`ai.py`)

**Files:**
- Create: `revelado/ai.py`, `tests/test_ai.py`

**Interfaces:**
- Consumes: `GlobalMetrics`, `Face` (from Tasks 4–5), `SETTINGS`.
- Produces:
  - `AIDecision` dataclass: `crop: tuple[float, float, float, float] | None` (left, top, right, bottom, normalized, `None` = no crop), `angle: float`, `exposure: float`, `contrast: int`, `highlights: int`, `shadows: int`, `temperature: int`, `tint: int`
  - `AIUnavailable(Exception)` — raised on any API/parse failure; caller switches to local-only
  - `decide(client, preview_jpeg: bytes, metrics: GlobalMetrics, faces: list[Face], rotation: float) -> AIDecision`
  - `clamp_decision(d: AIDecision) -> AIDecision` — safety limits (exposure ±`max_global_exposure`, angle ±`max_crop_angle`, contrast/highlights/shadows ±100, temp 2500–10000, tint ±100, crop ordered and within 0–1 with min size 0.5)
- API call uses `client.messages.create` with model `SETTINGS.model`, `max_tokens=SETTINGS.api_max_tokens`, a base64 `image` content block plus a text block, and `output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}}`. Numeric range enforcement is client-side (`clamp_decision`), since json_schema numeric min/max aren't supported.

- [ ] **Step 1: Write the failing tests** (mock the Anthropic client — no network)

```python
# tests/test_ai.py
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from revelado.ai import AIDecision, AIUnavailable, clamp_decision, decide
from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics

METRICS = GlobalMetrics(mean_luma=0.4, clip_shadows=0.01, clip_highlights=0.0,
                        wb_temp=5200, wb_tint=5, sharpness=300.0, iso=400)
VALID = {"crop": {"left": 0.05, "top": 0.02, "right": 0.98, "bottom": 0.95},
         "angle": -1.2, "exposure": 0.4, "contrast": 12, "highlights": -25,
         "shadows": 30, "temperature": 5300, "tint": 8}


def _client_returning(payload: str, stop_reason: str = "end_turn"):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=payload)],
    )
    return client


def test_decide_parses_valid_json():
    d = decide(_client_returning(json.dumps(VALID)), b"\xff\xd8", METRICS,
               [Face(0.4, 0.3, 0.1, 0.15, luma=0.28)], rotation=-1.0)
    assert d.crop == (0.05, 0.02, 0.98, 0.95)
    assert d.exposure == 0.4 and d.temperature == 5300


def test_decide_null_crop():
    payload = dict(VALID, crop=None)
    d = decide(_client_returning(json.dumps(payload)), b"", METRICS, [], 0.0)
    assert d.crop is None


def test_decide_sends_image_and_schema():
    client = _client_returning(json.dumps(VALID))
    decide(client, b"\xff\xd8abc", METRICS, [], 0.0)
    kwargs = client.messages.create.call_args.kwargs
    blocks = kwargs["messages"][0]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["type"] == "base64"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["model"] == "claude-haiku-4-5"


def test_decide_raises_on_garbage():
    with pytest.raises(AIUnavailable):
        decide(_client_returning("no es json"), b"", METRICS, [], 0.0)


def test_decide_raises_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("red caída")
    with pytest.raises(AIUnavailable):
        decide(client, b"", METRICS, [], 0.0)


def test_clamp_limits():
    wild = AIDecision(crop=(0.9, -0.2, 0.1, 2.0), angle=45.0, exposure=3.0,
                      contrast=500, highlights=-500, shadows=200,
                      temperature=100, tint=999)
    c = clamp_decision(wild)
    assert c.crop is None or (0 <= c.crop[0] < c.crop[2] <= 1 and 0 <= c.crop[1] < c.crop[3] <= 1)
    assert abs(c.exposure) <= 1.0 and abs(c.angle) <= 10.0
    assert -100 <= c.contrast <= 100 and -100 <= c.shadows <= 100
    assert 2500 <= c.temperature <= 10000 and -100 <= c.tint <= 100


def test_clamp_rejects_tiny_crop():
    d = AIDecision(crop=(0.4, 0.4, 0.5, 0.5), angle=0, exposure=0, contrast=0,
                   highlights=0, shadows=0, temperature=5500, tint=0)
    assert clamp_decision(d).crop is None  # recorte < 50% del lado => descartar
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_ai.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/ai.py
import base64
import json
from dataclasses import dataclass, replace

from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics
from revelado.config import SETTINGS


class AIUnavailable(Exception):
    """La API de Claude no está disponible o devolvió una respuesta inválida."""


@dataclass(frozen=True)
class AIDecision:
    crop: tuple[float, float, float, float] | None
    angle: float
    exposure: float
    contrast: int
    highlights: int
    shadows: int
    temperature: int
    tint: int


_CROP_PROPS = {k: {"type": "number"} for k in ("left", "top", "right", "bottom")}
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "crop": {"anyOf": [
            {"type": "object", "properties": _CROP_PROPS,
             "required": list(_CROP_PROPS), "additionalProperties": False},
            {"type": "null"},
        ]},
        "angle": {"type": "number"},
        "exposure": {"type": "number"},
        "contrast": {"type": "integer"},
        "highlights": {"type": "integer"},
        "shadows": {"type": "integer"},
        "temperature": {"type": "integer"},
        "tint": {"type": "integer"},
    },
    "required": ["crop", "angle", "exposure", "contrast", "highlights",
                 "shadows", "temperature", "tint"],
    "additionalProperties": False,
}

_SYSTEM = (
    "Eres un editor fotográfico profesional de retratos. Recibes la vista previa de una "
    "foto RAW y métricas técnicas medidas localmente. Devuelve ajustes de revelado para "
    "Lightroom en JSON. Reglas: exposición global conservadora (los rostros oscuros se "
    "corrigen aparte con máscaras locales, no subas la exposición global por ellos); "
    "recorta solo si mejora claramente la composición (regla de tercios, distracciones "
    "en bordes) y nunca cortes cabezas; crop en coordenadas normalizadas 0-1 de la imagen "
    "completa, o null si el encuadre ya es bueno; angle es el ajuste fino de enderezado "
    "en grados (parte de la estimación local dada); temperature/tint parten de la "
    "estimación local, corrígelos solo si ves un dominante de color."
)


def decide(client, preview_jpeg: bytes, metrics: GlobalMetrics,
           faces: list[Face], rotation: float) -> AIDecision:
    context = {
        "metricas": {
            "luma_media": round(metrics.mean_luma, 3),
            "recorte_sombras": round(metrics.clip_shadows, 4),
            "recorte_altas_luces": round(metrics.clip_highlights, 4),
            "wb_temp_estimada": metrics.wb_temp,
            "wb_tint_estimado": metrics.wb_tint,
            "iso": metrics.iso,
        },
        "rotacion_estimada_grados": round(rotation, 2),
        "caras": [{"x": round(f.x, 3), "y": round(f.y, 3), "w": round(f.w, 3),
                   "h": round(f.h, 3), "luma": round(f.luma, 3)} for f in faces],
    }
    try:
        response = client.messages.create(
            model=SETTINGS.model,
            max_tokens=SETTINGS.api_max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(preview_jpeg).decode()}},
                {"type": "text",
                 "text": "Analiza la foto y decide los ajustes. Contexto técnico:\n"
                         + json.dumps(context, ensure_ascii=False)},
            ]}],
            output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            raise AIUnavailable("La API rechazó la petición")
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        crop = data["crop"]
        return clamp_decision(AIDecision(
            crop=None if crop is None else (crop["left"], crop["top"],
                                            crop["right"], crop["bottom"]),
            angle=float(data["angle"]),
            exposure=float(data["exposure"]),
            contrast=int(data["contrast"]),
            highlights=int(data["highlights"]),
            shadows=int(data["shadows"]),
            temperature=int(data["temperature"]),
            tint=int(data["tint"]),
        ))
    except AIUnavailable:
        raise
    except Exception as exc:  # red, parseo, formato: todo degrada a modo local
        raise AIUnavailable(str(exc)) from exc


def clamp_decision(d: AIDecision) -> AIDecision:
    crop = d.crop
    if crop is not None:
        left, top, right, bottom = (min(max(v, 0.0), 1.0) for v in crop)
        # Descartar recortes invertidos o que dejen menos del 50% por lado
        if right - left < 0.5 or bottom - top < 0.5:
            crop = None
        else:
            crop = (left, top, right, bottom)
    return replace(
        d,
        crop=crop,
        angle=float(min(max(d.angle, -SETTINGS.max_crop_angle), SETTINGS.max_crop_angle)),
        exposure=float(min(max(d.exposure, -SETTINGS.max_global_exposure),
                           SETTINGS.max_global_exposure)),
        contrast=min(max(d.contrast, -100), 100),
        highlights=min(max(d.highlights, -100), 100),
        shadows=min(max(d.shadows, -100), 100),
        temperature=min(max(d.temperature, 2500), 10000),
        tint=min(max(d.tint, -100), 100),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_ai.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/ai.py tests/test_ai.py && git commit -m "feat: decisión estética vía API de Claude con salida estructurada"
```

---

### Task 8: develop settings + face masks (`develop.py`)

**Files:**
- Create: `revelado/develop.py`, `tests/test_develop.py`

**Interfaces:**
- Consumes: `GlobalMetrics`, `Face`, `AIDecision`, helpers `sharpening_for` / `noise_reduction_for`.
- Produces:
  - `RadialMask` dataclass: `left, top, right, bottom: float` (normalized ellipse bounding box in **full-image** coordinates — LR masks are always in full-image space, independent of crop), `exposure_ev: float`, `shadows: int`
  - `DevelopSettings` dataclass: `temperature, tint: int`, `exposure: float`, `contrast, highlights, shadows, whites, blacks: int`, `sharpness: int`, `luminance_smoothing: int`, `has_crop: bool`, `crop_left, crop_top, crop_right, crop_bottom: float`, `crop_angle: float`, `masks: list[RadialMask]`, `ai_used: bool`
  - `compute_settings(metrics, faces, rotation, ai: AIDecision | None) -> DevelopSettings` — `ai=None` means local-only mode
  - `face_mask_for(face: Face) -> RadialMask | None` — `None` when face is bright enough

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_develop.py
import math

from revelado.ai import AIDecision
from revelado.analysis.faces import Face
from revelado.analysis.metrics import GlobalMetrics
from revelado.develop import compute_settings, face_mask_for

METRICS = GlobalMetrics(mean_luma=0.42, clip_shadows=0.0, clip_highlights=0.0,
                        wb_temp=5400, wb_tint=3, sharpness=100.0, iso=3200)
AI = AIDecision(crop=(0.1, 0.05, 0.95, 0.9), angle=-1.5, exposure=0.3,
                contrast=10, highlights=-20, shadows=25, temperature=5300, tint=6)


def test_dark_face_gets_mask_with_capped_ev():
    mask = face_mask_for(Face(0.4, 0.3, 0.1, 0.12, luma=0.20))
    assert mask is not None
    expected = math.log2(0.50 / 0.20)
    assert abs(mask.exposure_ev - expected) < 0.01
    very_dark = face_mask_for(Face(0.4, 0.3, 0.1, 0.12, luma=0.02))
    assert very_dark.exposure_ev == 1.5  # tope


def test_bright_face_no_mask():
    assert face_mask_for(Face(0.4, 0.3, 0.1, 0.12, luma=0.55)) is None


def test_mask_ellipse_expands_face_box_and_clamps():
    mask = face_mask_for(Face(0.0, 0.0, 0.2, 0.2, luma=0.1))
    assert mask.left >= 0.0 and mask.top >= 0.0
    assert mask.right - mask.left > 0.2  # expandido ~1.6x (recortado al borde)


def test_compute_with_ai_uses_ai_values():
    s = compute_settings(METRICS, [Face(0.4, 0.3, 0.1, 0.12, luma=0.2)], -1.0, AI)
    assert s.ai_used and s.has_crop
    assert (s.crop_left, s.crop_top, s.crop_right, s.crop_bottom) == AI.crop
    assert s.crop_angle == AI.angle and s.exposure == AI.exposure
    assert s.temperature == AI.temperature
    assert s.luminance_smoothing > 0  # ISO 3200
    assert len(s.masks) == 1


def test_compute_local_only():
    s = compute_settings(METRICS, [], rotation=-2.0, ai=None)
    assert not s.ai_used and not s.has_crop
    assert s.crop_angle == -2.0            # usa la estimación local
    assert s.temperature == METRICS.wb_temp
    assert abs(s.exposure) <= 1.0
    # exposición local: llevar luma media hacia ~0.45 de forma conservadora
    assert s.exposure > 0                  # 0.42 < 0.45 => sube un poco


def test_local_only_angle_zero_no_crop_flag():
    s = compute_settings(METRICS, [], rotation=0.0, ai=None)
    assert not s.has_crop and s.crop_angle == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_develop.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/develop.py
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
    temperature: int
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


def compute_settings(metrics: GlobalMetrics, faces: list[Face],
                     rotation: float, ai: AIDecision | None) -> DevelopSettings:
    masks = [m for m in (face_mask_for(f) for f in faces) if m is not None]

    if ai is not None:
        has_crop = ai.crop is not None or ai.angle != 0.0
        crop = ai.crop or (0.0, 0.0, 1.0, 1.0)
        return DevelopSettings(
            temperature=ai.temperature, tint=ai.tint,
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
        temperature=metrics.wb_temp, tint=metrics.wb_tint,
        exposure=round(exposure, 2), contrast=0,
        highlights=highlights, shadows=shadows, whites=0, blacks=0,
        sharpness=sharpening_for(metrics.sharpness),
        luminance_smoothing=noise_reduction_for(metrics.iso),
        has_crop=rotation != 0.0,
        crop_left=0.0, crop_top=0.0, crop_right=1.0, crop_bottom=1.0,
        crop_angle=rotation,
        masks=masks, ai_used=False,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_develop.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/develop.py tests/test_develop.py && git commit -m "feat: cálculo de ajustes de revelado y máscaras por rostro"
```

---

### Task 9: XMP sidecar (`xmp.py`)

**Files:**
- Create: `revelado/xmp.py`, `tests/test_xmp.py`

**Interfaces:**
- Consumes: `DevelopSettings`, `RadialMask`.
- Produces:
  - `SidecarExists(Exception)`
  - `sidecar_path(raw_path: Path) -> Path` — `IMG_0001.CR3` → `IMG_0001.xmp` (same directory, lowercase `.xmp`)
  - `render_xmp(s: DevelopSettings) -> str` — full XMP document, `crs` namespace, ProcessVersion 11.0 (PV2012); radial masks as `crs:CircularGradientBasedCorrections` (local values normalized: exposure stored as EV/4, shadows as value/100)
  - `write_sidecar(raw_path: Path, s: DevelopSettings, overwrite: bool = False) -> Path` — raises `SidecarExists` if the file exists and `overwrite` is False
  - `delete_sidecar(raw_path: Path) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_xmp.py
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from revelado.develop import DevelopSettings, RadialMask
from revelado.xmp import (SidecarExists, delete_sidecar, render_xmp,
                          sidecar_path, write_sidecar)

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"


def _settings(masks=()):
    return DevelopSettings(
        temperature=5300, tint=8, exposure=0.35, contrast=12, highlights=-25,
        shadows=30, whites=0, blacks=-5, sharpness=45, luminance_smoothing=15,
        has_crop=True, crop_left=0.05, crop_top=0.02, crop_right=0.98,
        crop_bottom=0.95, crop_angle=-1.2, masks=list(masks), ai_used=True)


def test_sidecar_path():
    assert sidecar_path(Path("/a/IMG_1.CR3")) == Path("/a/IMG_1.xmp")


def test_render_is_valid_xml_with_crs_values():
    root = ET.fromstring(render_xmp(_settings()))
    desc = root.find(f".//{{{'http://www.w3.org/1999/02/22-rdf-syntax-ns#'}}}Description")
    assert desc.get(f"{{{CRS}}}Temperature") == "5300"
    assert desc.get(f"{{{CRS}}}Exposure2012") == "+0.35"
    assert desc.get(f"{{{CRS}}}Highlights2012") == "-25"
    assert desc.get(f"{{{CRS}}}HasCrop") == "True"
    assert desc.get(f"{{{CRS}}}CropAngle") == "-1.200000"
    assert desc.get(f"{{{CRS}}}CropLeft") == "0.050000"
    assert desc.get(f"{{{CRS}}}Sharpness") == "45"
    assert desc.get(f"{{{CRS}}}LuminanceSmoothing") == "15"
    assert desc.get(f"{{{CRS}}}HasSettings") == "True"


def test_render_mask_normalization():
    mask = RadialMask(left=0.3, top=0.2, right=0.6, bottom=0.5,
                      exposure_ev=1.0, shadows=25)
    text = render_xmp(_settings([mask]))
    assert "CircularGradientBasedCorrections" in text
    assert 'crs:LocalExposure2012="0.250000"' in text  # 1.0 EV / 4
    assert 'crs:LocalShadows2012="0.250000"' in text   # 25 / 100
    assert "<crs:Top>0.200000</crs:Top>" in text
    ET.fromstring(text)  # sigue siendo XML válido


def test_render_without_crop_or_masks():
    s = _settings()
    s.has_crop = False
    s.masks = []
    text = render_xmp(s)
    assert 'crs:HasCrop="False"' in text
    assert "CircularGradientBasedCorrections" not in text


def test_write_respects_existing(tmp_path):
    raw = tmp_path / "IMG_2.CR2"
    raw.write_bytes(b"fake")
    out = write_sidecar(raw, _settings())
    assert out.exists() and out.suffix == ".xmp"
    with pytest.raises(SidecarExists):
        write_sidecar(raw, _settings())
    write_sidecar(raw, _settings(), overwrite=True)  # no lanza


def test_delete(tmp_path):
    raw = tmp_path / "IMG_3.CR2"
    raw.write_bytes(b"fake")
    write_sidecar(raw, _settings())
    assert delete_sidecar(raw) is True
    assert delete_sidecar(raw) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_xmp.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/xmp.py
from pathlib import Path

from revelado.develop import DevelopSettings, RadialMask


class SidecarExists(Exception):
    """Ya existe un XMP para esta foto; se necesita confirmación para sobrescribir."""


def sidecar_path(raw_path: Path) -> Path:
    return raw_path.with_suffix(".xmp")


def _fmt_signed_float(v: float) -> str:
    return f"{v:+.2f}" if v != 0 else "0.00"


def _fmt_signed_int(v: int) -> str:
    return f"{v:+d}" if v != 0 else "0"


def _mask_xml(m: RadialMask) -> str:
    return f"""    <rdf:li>
     <rdf:Description
      crs:What="Correction"
      crs:CorrectionAmount="1.000000"
      crs:CorrectionActive="true"
      crs:LocalExposure2012="{m.exposure_ev / 4:.6f}"
      crs:LocalShadows2012="{m.shadows / 100:.6f}"
      crs:LocalContrast2012="0.000000"
      crs:LocalHighlights2012="0.000000">
      <crs:CorrectionMasks>
       <rdf:Seq>
        <rdf:li rdf:parseType="Resource">
         <crs:What>Mask/CircularGradient</crs:What>
         <crs:MaskValue>1.000000</crs:MaskValue>
         <crs:Top>{m.top:.6f}</crs:Top>
         <crs:Left>{m.left:.6f}</crs:Left>
         <crs:Bottom>{m.bottom:.6f}</crs:Bottom>
         <crs:Right>{m.right:.6f}</crs:Right>
         <crs:Angle>0</crs:Angle>
         <crs:Midpoint>50</crs:Midpoint>
         <crs:Roundness>0</crs:Roundness>
         <crs:Feather>75</crs:Feather>
         <crs:Flipped>true</crs:Flipped>
         <crs:Version>2</crs:Version>
        </rdf:li>
       </rdf:Seq>
      </crs:CorrectionMasks>
     </rdf:Description>
    </rdf:li>"""


def render_xmp(s: DevelopSettings) -> str:
    crop_attrs = ""
    if s.has_crop:
        crop_attrs = f"""
   crs:CropLeft="{s.crop_left:.6f}"
   crs:CropTop="{s.crop_top:.6f}"
   crs:CropRight="{s.crop_right:.6f}"
   crs:CropBottom="{s.crop_bottom:.6f}"
   crs:CropAngle="{s.crop_angle:.6f}\""""

    masks_xml = ""
    if s.masks:
        items = "\n".join(_mask_xml(m) for m in s.masks)
        masks_xml = f"""
   <crs:CircularGradientBasedCorrections>
    <rdf:Seq>
{items}
    </rdf:Seq>
   </crs:CircularGradientBasedCorrections>"""

    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="revelado">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   crs:Version="11.0"
   crs:ProcessVersion="11.0"
   crs:WhiteBalance="Custom"
   crs:Temperature="{s.temperature}"
   crs:Tint="{_fmt_signed_int(s.tint)}"
   crs:Exposure2012="{_fmt_signed_float(s.exposure)}"
   crs:Contrast2012="{_fmt_signed_int(s.contrast)}"
   crs:Highlights2012="{_fmt_signed_int(s.highlights)}"
   crs:Shadows2012="{_fmt_signed_int(s.shadows)}"
   crs:Whites2012="{_fmt_signed_int(s.whites)}"
   crs:Blacks2012="{_fmt_signed_int(s.blacks)}"
   crs:Sharpness="{s.sharpness}"
   crs:LuminanceSmoothing="{s.luminance_smoothing}"
   crs:HasCrop="{'True' if s.has_crop else 'False'}"{crop_attrs}
   crs:HasSettings="True">{masks_xml}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


def write_sidecar(raw_path: Path, s: DevelopSettings, overwrite: bool = False) -> Path:
    path = sidecar_path(raw_path)
    if path.exists() and not overwrite:
        raise SidecarExists(str(path))
    path.write_text(render_xmp(s), encoding="utf-8")
    return path


def delete_sidecar(raw_path: Path) -> bool:
    path = sidecar_path(raw_path)
    if path.exists():
        path.unlink()
        return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_xmp.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/xmp.py tests/test_xmp.py && git commit -m "feat: generación de sidecars XMP con máscaras radiales"
```

---

### Task 10: pipeline (`pipeline.py`)

**Files:**
- Create: `revelado/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 2–9.
- Produces:
  - `PhotoResult` dataclass: `path: str`, `status: str` (`"done" | "done_local_only" | "skipped_existing" | "error"`), `message: str = ""`, `settings: DevelopSettings | None = None`
  - `process_photo(raw_path: Path, overwrite: bool, client) -> PhotoResult` — `client=None` forces local-only mode; `AIUnavailable` downgrades to local-only; `PreviewError`/other exceptions → `"error"`; `SidecarExists` → `"skipped_existing"`

- [ ] **Step 1: Write the failing tests** (patch the module-level function references)

```python
# tests/test_pipeline.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/pipeline.py
import logging
from dataclasses import dataclass
from pathlib import Path

from revelado.ai import AIUnavailable, decide
from revelado.analysis.faces import detect_faces
from revelado.analysis.horizon import estimate_rotation
from revelado.analysis.metrics import compute_metrics
from revelado.config import SETTINGS
from revelado.develop import DevelopSettings, compute_settings
from revelado.exif import extract_preview_jpeg, read_exif
from revelado.imageio import decode_upright, encode_jpeg
from revelado.xmp import SidecarExists, sidecar_path, write_sidecar

log = logging.getLogger(__name__)


@dataclass
class PhotoResult:
    path: str
    status: str  # done | done_local_only | skipped_existing | error
    message: str = ""
    settings: DevelopSettings | None = None


def process_photo(raw_path: Path, overwrite: bool, client) -> PhotoResult:
    try:
        if sidecar_path(raw_path).exists() and not overwrite:
            return PhotoResult(str(raw_path), "skipped_existing",
                               "Ya existe un XMP; no se sobrescribe sin confirmación")

        exif = read_exif(raw_path)
        jpeg = extract_preview_jpeg(raw_path)
        img = decode_upright(jpeg, exif.orientation, SETTINGS.preview_long_edge)
        metrics = compute_metrics(img, exif.iso)
        faces = detect_faces(img, SETTINGS.yunet_model_path)
        rotation = estimate_rotation(img)

        ai = None
        status = "done_local_only"
        if client is not None:
            try:
                ai = decide(client, encode_jpeg(img), metrics, faces, rotation)
                status = "done"
            except AIUnavailable as exc:
                log.warning("API no disponible para %s: %s", raw_path.name, exc)

        settings = compute_settings(metrics, faces, rotation, ai)
        write_sidecar(raw_path, settings, overwrite=overwrite)
        return PhotoResult(str(raw_path), status, settings=settings)

    except SidecarExists:
        return PhotoResult(str(raw_path), "skipped_existing",
                           "Ya existe un XMP; no se sobrescribe sin confirmación")
    except Exception as exc:
        log.exception("Error procesando %s", raw_path)
        return PhotoResult(str(raw_path), "error", f"{type(exc).__name__}: {exc}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/pipeline.py tests/test_pipeline.py && git commit -m "feat: pipeline por foto con degradación a modo local"
```

---

### Task 11: jobs + notifications (`jobs.py`, `notify.py`)

**Files:**
- Create: `revelado/jobs.py`, `revelado/notify.py`, `tests/test_jobs.py`

**Interfaces:**
- Consumes: `PhotoResult` shape, `SETTINGS.worker_concurrency`.
- Produces (`jobs.py`):
  - `JobManager` class:
    - `create_job(paths: list[Path], overwrite: bool, processor) -> str` — `processor(path, overwrite) -> PhotoResult` is injected (server binds the real pipeline + client); starts an asyncio task via `asyncio.create_task` (**must be called from async code** — the `/api/process` route is `async def` for this reason); returns `job_id` (uuid4 hex)
    - `get(job_id) -> dict | None` — `{"id", "total", "completed", "running", "results": [{"path","status","message","adjust"?}, ...]}` where `adjust` (present when the photo produced settings) is `{"exposure": float, "angle": float, "crop": [l,t,r,b] | null, "masks": int}` — the frontend uses it to simulate the before/after preview
    - `async events(job_id)` — async generator yielding dicts: `{"type": "photo", ...result}` per photo and a final `{"type": "finished", "total", "ok", "errors"}`; subscribers attaching mid-job first receive all past events (replay list)
  - Photos run concurrently via `asyncio.to_thread` bounded by `asyncio.Semaphore(SETTINGS.worker_concurrency)`; a photo raising unexpectedly yields a `status="error"` event, never kills the job
  - On finish, calls `notify.notify_macos(...)` (injected as `on_finish` callable, default the real one)
- Produces (`notify.py`): `notify_macos(title: str, message: str) -> None` — `subprocess.run(["osascript", "-e", ...])`, swallows all errors

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_jobs.py
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revelado.jobs import JobManager
from revelado.pipeline import PhotoResult


def _proc(path: Path, overwrite: bool) -> PhotoResult:
    if "bad" in path.name:
        raise RuntimeError("explota")
    return PhotoResult(str(path), "done")


async def _collect(manager, job_id):
    events = []
    async for ev in manager.events(job_id):
        events.append(ev)
    return events


@pytest.mark.asyncio
async def test_job_processes_all_and_finishes():
    manager = JobManager(on_finish=MagicMock())
    paths = [Path(f"/x/IMG_{i}.CR3") for i in range(3)]
    job_id = manager.create_job(paths, overwrite=False, processor=_proc)
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    photo_events = [e for e in events if e["type"] == "photo"]
    assert len(photo_events) == 3
    assert events[-1]["type"] == "finished" and events[-1]["ok"] == 3
    state = manager.get(job_id)
    assert state["completed"] == 3 and not state["running"]


@pytest.mark.asyncio
async def test_processor_exception_becomes_error_event():
    manager = JobManager(on_finish=MagicMock())
    job_id = manager.create_job([Path("/x/bad.CR3"), Path("/x/ok.CR3")],
                                overwrite=False, processor=_proc)
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    statuses = sorted(e["status"] for e in events if e["type"] == "photo")
    assert statuses == ["done", "error"]
    assert events[-1]["errors"] == 1


@pytest.mark.asyncio
async def test_on_finish_called():
    on_finish = MagicMock()
    manager = JobManager(on_finish=on_finish)
    job_id = manager.create_job([Path("/x/a.CR3")], overwrite=False, processor=_proc)
    await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    on_finish.assert_called_once()


@pytest.mark.asyncio
async def test_late_subscriber_gets_replay():
    manager = JobManager(on_finish=MagicMock())
    job_id = manager.create_job([Path("/x/a.CR3")], overwrite=False, processor=_proc)
    await asyncio.sleep(0.3)  # dejar terminar
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    assert events[-1]["type"] == "finished"


def test_notify_macos_swallows_errors():
    from revelado.notify import notify_macos
    with patch("revelado.notify.subprocess.run", side_effect=FileNotFoundError):
        notify_macos("t", "m")  # no lanza
```

Add `pytest-asyncio` to `requirements.txt` and `asyncio_mode = "auto"`? No — keep explicit: add to `requirements.txt` the line `pytest-asyncio>=0.23` and create `pytest.ini`:

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
```

(with `asyncio_mode = auto` the `@pytest.mark.asyncio` decorators are optional but harmless).

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pip install pytest-asyncio && ./.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/notify.py
import subprocess


def notify_macos(title: str, message: str) -> None:
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Glass"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass  # la notificación nunca debe romper el flujo
```

```python
# revelado/jobs.py
import asyncio
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from revelado.config import SETTINGS
from revelado.notify import notify_macos
from revelado.pipeline import PhotoResult


class JobManager:
    def __init__(self, on_finish: Callable[[str, str], None] = notify_macos):
        self._jobs: dict[str, dict] = {}
        self._on_finish = on_finish

    def create_job(self, paths: list[Path], overwrite: bool,
                   processor: Callable[[Path, bool], PhotoResult]) -> str:
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id, "total": len(paths), "completed": 0,
            "running": True, "results": [], "events": [],
            "condition": asyncio.Condition(),
        }
        self._jobs[job_id] = job
        # Requiere un event loop en ejecución: create_job debe llamarse desde
        # código async (la ruta /api/process es `async def` por esto).
        asyncio.create_task(self._run(job, paths, overwrite, processor))
        return job_id

    def get(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return {k: job[k] for k in ("id", "total", "completed", "running", "results")}

    async def _emit(self, job: dict, event: dict) -> None:
        async with job["condition"]:
            job["events"].append(event)
            job["condition"].notify_all()

    async def _run(self, job, paths, overwrite, processor) -> None:
        sem = asyncio.Semaphore(SETTINGS.worker_concurrency)

        async def one(path: Path):
            async with sem:
                try:
                    result = await asyncio.to_thread(processor, path, overwrite)
                except Exception as exc:
                    result = PhotoResult(str(path), "error",
                                         f"{type(exc).__name__}: {exc}")
            entry = {"path": result.path, "status": result.status,
                     "message": result.message}
            if result.settings is not None:
                s = result.settings
                entry["adjust"] = {
                    "exposure": s.exposure, "angle": s.crop_angle,
                    "crop": [s.crop_left, s.crop_top, s.crop_right, s.crop_bottom]
                            if s.has_crop else None,
                    "masks": len(s.masks),
                }
            job["results"].append(entry)
            job["completed"] += 1
            await self._emit(job, {"type": "photo", **entry,
                                   "completed": job["completed"],
                                   "total": job["total"]})

        await asyncio.gather(*(one(p) for p in paths))
        ok = sum(1 for r in job["results"] if r["status"].startswith("done"))
        errors = sum(1 for r in job["results"] if r["status"] == "error")
        job["running"] = False
        await self._emit(job, {"type": "finished", "total": job["total"],
                               "ok": ok, "errors": errors})
        self._on_finish("Revelado terminado",
                        f"{ok} de {job['total']} fotos procesadas"
                        + (f", {errors} con error" if errors else ""))

    async def events(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is None:
            return
        index = 0
        while True:
            async with job["condition"]:
                while index >= len(job["events"]):
                    await job["condition"].wait()
                event = job["events"][index]
            index += 1
            yield event
            if event["type"] == "finished":
                return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the whole suite and commit**

Run: `./.venv/bin/python -m pytest -q` — Expected: all green.

```bash
git add revelado/jobs.py revelado/notify.py tests/test_jobs.py pytest.ini requirements.txt
git commit -m "feat: gestor de trabajos con eventos y notificación macOS"
```

---

### Task 12: FastAPI server (`server.py`)

**Files:**
- Create: `revelado/server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `JobManager`, `process_photo`, `read_exif`/`extract_preview_jpeg`/`decode_upright`/`encode_jpeg`, `delete_sidecar`, `sidecar_path`, `SETTINGS`.
- Produces: `create_app(job_manager: JobManager | None = None, client_factory=None) -> FastAPI` (factory for testability) with routes:
  - `GET /` → `static/index.html`; `GET /static/*` → static files
  - `GET /api/browse?path=` → `{"path", "parent", "dirs": [{"name","path","raw_count"}]}` (defaults to `Path.home()`; only directories; `raw_count` = files matching `SETTINGS.raw_extensions`)
  - `GET /api/photos?dir=` → `{"photos": [{"name", "path", "has_xmp"}]}` sorted by name
  - `GET /api/thumb?path=` → JPEG thumbnail (preview extracted + downscaled to `SETTINGS.thumb_long_edge`, cached in `SETTINGS.cache_dir/thumbs/<sha1(path+mtime)>.jpg`); 404 with Spanish detail on failure
  - `POST /api/process` (**`async def`** — `JobManager.create_job` needs the running loop) body `{"files": [...], "overwrite": false}` → `{"job_id", "local_only"}`; builds the Anthropic client once via `client_factory` (default: `anthropic.Anthropic()` if `ANTHROPIC_API_KEY` is resolvable, else `None` → local-only) and binds `processor = lambda p, ow: process_photo(p, ow, client)`
  - `GET /api/jobs/{job_id}` → job state or 404
  - `GET /api/jobs/{job_id}/events` → SSE (`text/event-stream`, each event `data: <json>\n\n`)
  - `DELETE /api/xmp?path=` → `{"deleted": bool}`
- Module-level `app = create_app()` for uvicorn.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from revelado.exif import ExifData
from revelado.jobs import JobManager
from revelado.pipeline import PhotoResult
from revelado.server import create_app


def _client():
    app = create_app(job_manager=JobManager(on_finish=MagicMock()),
                     client_factory=lambda: None)
    return TestClient(app)


def test_browse_lists_dirs(tmp_path):
    (tmp_path / "sesion1").mkdir()
    (tmp_path / "sesion1" / "IMG_1.CR3").write_bytes(b"x")
    (tmp_path / "archivo.txt").write_text("no soy carpeta")
    r = _client().get("/api/browse", params={"path": str(tmp_path)})
    assert r.status_code == 200
    dirs = r.json()["dirs"]
    assert [d["name"] for d in dirs] == ["sesion1"]
    assert dirs[0]["raw_count"] == 1


def test_photos_lists_raws_with_xmp_flag(tmp_path):
    (tmp_path / "IMG_2.CR2").write_bytes(b"x")
    (tmp_path / "IMG_1.CR3").write_bytes(b"x")
    (tmp_path / "IMG_1.xmp").write_text("previo")
    (tmp_path / "nota.txt").write_text("ignorar")
    r = _client().get("/api/photos", params={"dir": str(tmp_path)})
    photos = r.json()["photos"]
    assert [p["name"] for p in photos] == ["IMG_1.CR3", "IMG_2.CR2"]
    assert photos[0]["has_xmp"] is True and photos[1]["has_xmp"] is False


def test_thumb_returns_jpeg(tmp_path):
    raw = tmp_path / "IMG_1.CR3"
    raw.write_bytes(b"x")
    img = np.full((100, 150, 3), 90, dtype=np.uint8)
    with patch("revelado.server.read_exif", return_value=ExifData(100, 1, 0, 0)), \
         patch("revelado.server.extract_preview_jpeg", return_value=b"\xff\xd8x"), \
         patch("revelado.server.decode_upright", return_value=img):
        r = _client().get("/api/thumb", params={"path": str(raw)})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_process_and_stream_events(tmp_path):
    raw = tmp_path / "IMG_1.CR3"
    raw.write_bytes(b"x")
    fake = PhotoResult(str(raw), "done")
    with patch("revelado.server.process_photo", return_value=fake):
        client = _client()
        r = client.post("/api/process", json={"files": [str(raw)], "overwrite": False})
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        # SSE: leer hasta el evento finished
        events = []
        with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                    if events[-1]["type"] == "finished":
                        break
        assert events[-1]["ok"] == 1
        state = client.get(f"/api/jobs/{job_id}").json()
        assert state["completed"] == 1


def test_job_not_found():
    assert _client().get("/api/jobs/nope").status_code == 404


def test_delete_xmp(tmp_path):
    raw = tmp_path / "IMG_1.CR3"
    raw.write_bytes(b"x")
    (tmp_path / "IMG_1.xmp").write_text("x")
    c = _client()
    assert c.delete("/api/xmp", params={"path": str(raw)}).json()["deleted"] is True
    assert c.delete("/api/xmp", params={"path": str(raw)}).json()["deleted"] is False


def test_index_served():
    r = _client().get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
```

Note: `TestClient` runs the app in a worker thread with a real event loop, so `create_job` (called inside the request) has a running loop. `test_index_served` requires Task 13's `index.html` to exist — create a placeholder now: `revelado/static/index.html` containing `<!-- placeholder -->` (Task 13 replaces it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

```python
# revelado/server.py
import hashlib
import json
import os
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from revelado.config import SETTINGS
from revelado.exif import extract_preview_jpeg, read_exif
from revelado.imageio import decode_upright, encode_jpeg
from revelado.jobs import JobManager
from revelado.pipeline import process_photo
from revelado.xmp import delete_sidecar, sidecar_path

_STATIC = Path(__file__).parent / "static"


def _default_client_factory():
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


class ProcessRequest(BaseModel):
    files: list[str]
    overwrite: bool = False


def create_app(job_manager: JobManager | None = None, client_factory=None) -> FastAPI:
    app = FastAPI(title="Revelado")
    manager = job_manager or JobManager()
    make_client = client_factory or _default_client_factory

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/browse")
    def browse(path: str = ""):
        base = Path(path).expanduser() if path else Path.home()
        if not base.is_dir():
            raise HTTPException(404, "Carpeta no encontrada")
        dirs = []
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                count = sum(1 for f in child.iterdir()
                            if f.suffix.lower() in SETTINGS.raw_extensions) \
                        if os.access(child, os.R_OK) else 0
                dirs.append({"name": child.name, "path": str(child),
                             "raw_count": count})
        return {"path": str(base), "parent": str(base.parent), "dirs": dirs}

    @app.get("/api/photos")
    def photos(dir: str):
        base = Path(dir).expanduser()
        if not base.is_dir():
            raise HTTPException(404, "Carpeta no encontrada")
        items = sorted(f for f in base.iterdir()
                       if f.suffix.lower() in SETTINGS.raw_extensions)
        return {"photos": [{"name": f.name, "path": str(f),
                            "has_xmp": sidecar_path(f).exists()} for f in items]}

    @app.get("/api/thumb")
    def thumb(path: str):
        raw = Path(path)
        if not raw.exists():
            raise HTTPException(404, "Archivo no encontrado")
        cache_dir = SETTINGS.cache_dir / "thumbs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(f"{raw}:{raw.stat().st_mtime}".encode()).hexdigest()
        cached = cache_dir / f"{key}.jpg"
        if not cached.exists():
            try:
                exif = read_exif(raw)
                jpeg = extract_preview_jpeg(raw)
                img = decode_upright(jpeg, exif.orientation, SETTINGS.thumb_long_edge)
                cached.write_bytes(encode_jpeg(img, quality=80))
            except Exception as exc:
                raise HTTPException(404, f"Sin miniatura: {exc}")
        return Response(cached.read_bytes(), media_type="image/jpeg")

    @app.post("/api/process")
    async def process(req: ProcessRequest):
        paths = [Path(f) for f in req.files]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise HTTPException(400, f"Archivos inexistentes: {missing[0]}")
        client = make_client()
        processor = lambda p, ow: process_photo(p, ow, client)
        job_id = manager.create_job(paths, req.overwrite, processor)
        return {"job_id": job_id, "local_only": client is None}

    @app.get("/api/jobs/{job_id}")
    def job_state(job_id: str):
        state = manager.get(job_id)
        if state is None:
            raise HTTPException(404, "Trabajo no encontrado")
        return state

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        if manager.get(job_id) is None:
            raise HTTPException(404, "Trabajo no encontrado")

        async def stream():
            async for event in manager.events(job_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.delete("/api/xmp")
    def remove_xmp(path: str):
        return {"deleted": delete_sidecar(Path(path))}

    return app


app = create_app()
```

Also create placeholder `revelado/static/index.html` (`<!-- placeholder -->`), empty `revelado/static/app.js` and `revelado/static/style.css` so StaticFiles mounts.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add revelado/server.py revelado/static tests/test_server.py
git commit -m "feat: servidor FastAPI con navegación, proceso y SSE"
```

---

### Task 13: frontend (static files) + entry point

**Files:**
- Modify: `revelado/static/index.html`, `revelado/static/app.js`, `revelado/static/style.css`
- Create: `run.py`

**Interfaces:**
- Consumes the HTTP API from Task 12 exactly as specified there.

- [ ] **Step 1: Write `run.py`**

```python
# run.py
import webbrowser

import uvicorn

from revelado.config import SETTINGS

if __name__ == "__main__":
    webbrowser.open(f"http://localhost:{SETTINGS.port}")
    uvicorn.run("revelado.server:app", host="127.0.0.1", port=SETTINGS.port)
```

- [ ] **Step 2: Write the frontend**

```html
<!-- revelado/static/index.html -->
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Revelado — asistente para Lightroom</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>Revelado</h1>
    <p id="subtitle">Selecciona la carpeta de la sesión</p>
  </header>

  <section id="browser">
    <div id="crumb"></div>
    <ul id="dirs"></ul>
  </section>

  <section id="gallery" hidden>
    <div class="toolbar">
      <button id="back">← Carpetas</button>
      <button id="select-all">Seleccionar todas</button>
      <label><input type="checkbox" id="overwrite"> Sobrescribir XMP existentes</label>
      <button id="process" class="primary" disabled>Procesar seleccionadas</button>
    </div>
    <div id="grid"></div>
  </section>

  <section id="progress" hidden>
    <h2 id="progress-title">Procesando…</h2>
    <div class="bar"><div id="bar-fill"></div></div>
    <p id="progress-text"></p>
    <ul id="log"></ul>
    <div class="toolbar" id="done-actions" hidden>
      <button id="show-review" class="primary">Revisar resultados</button>
      <button id="restart">Procesar otra carpeta</button>
    </div>
  </section>

  <section id="review" hidden>
    <div class="toolbar">
      <button id="review-back">← Progreso</button>
      <p>Antes / después (simulación aproximada). Descarta las que no te convenzan antes de ir a Lightroom.</p>
    </div>
    <div id="review-grid"></div>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
```

```css
/* revelado/static/style.css */
* { box-sizing: border-box; margin: 0; }
body { font: 15px/1.5 -apple-system, sans-serif; background: #16181d; color: #e8e8e8;
       max-width: 1100px; margin: 0 auto; padding: 1.5rem; }
header { margin-bottom: 1.5rem; }
h1 { font-size: 1.6rem; }
#subtitle { color: #9aa0aa; }
button { background: #2a2e37; color: #e8e8e8; border: 1px solid #3a3f4a;
         border-radius: 8px; padding: .5rem 1rem; cursor: pointer; }
button.primary { background: #3b6ef5; border-color: #3b6ef5; }
button:disabled { opacity: .4; cursor: default; }
.toolbar { display: flex; gap: .8rem; align-items: center; flex-wrap: wrap;
           margin-bottom: 1rem; }
#crumb { color: #9aa0aa; margin-bottom: .6rem; font-size: .85rem; }
#dirs { list-style: none; }
#dirs li { padding: .55rem .8rem; border-bottom: 1px solid #2a2e37; cursor: pointer;
           display: flex; justify-content: space-between; }
#dirs li:hover { background: #22252c; }
.raw-count { color: #7fb069; font-size: .85rem; }
#grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: .7rem; }
.photo { position: relative; border: 2px solid transparent; border-radius: 8px;
         overflow: hidden; cursor: pointer; background: #22252c; }
.photo img { width: 100%; height: 120px; object-fit: cover; display: block; }
.photo .name { font-size: .72rem; padding: .25rem .4rem; color: #9aa0aa;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.photo.selected { border-color: #3b6ef5; }
.photo .badge { position: absolute; top: 6px; right: 6px; background: #c9a227;
                color: #111; font-size: .65rem; padding: 1px 6px; border-radius: 6px; }
.bar { background: #2a2e37; border-radius: 8px; height: 14px; overflow: hidden;
       margin: .8rem 0; }
#bar-fill { background: #3b6ef5; height: 100%; width: 0; transition: width .3s; }
#log { list-style: none; max-height: 320px; overflow-y: auto; font-size: .85rem; }
#log li { padding: .2rem 0; color: #9aa0aa; }
#log li.error { color: #e06c75; }
#log li.skipped { color: #c9a227; }
#review-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
               gap: 1rem; }
.review-card { background: #22252c; border-radius: 8px; padding: .6rem; }
.review-card .pair { display: flex; gap: .4rem; }
.review-card .frame { flex: 1; height: 130px; overflow: hidden; border-radius: 6px;
                      background: #111; display: flex; align-items: center;
                      justify-content: center; }
.review-card .frame img { max-width: 100%; max-height: 100%; }
.review-card .caption { font-size: .7rem; color: #9aa0aa; text-align: center; }
.review-card .actions { display: flex; gap: .5rem; margin-top: .5rem; }
.review-card .actions button { font-size: .8rem; padding: .3rem .7rem; }
.review-card.discarded { opacity: .45; }
```

```javascript
// revelado/static/app.js
const $ = (id) => document.getElementById(id);
const state = { dir: null, selected: new Set(), results: [] };

function show(section) {
  for (const id of ["browser", "gallery", "progress", "review"])
    $(id).hidden = id !== section;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

// --- Pantalla 1: carpetas ---
async function loadDirs(path = "") {
  const data = await api(`/api/browse?path=${encodeURIComponent(path)}`);
  $("crumb").textContent = data.path;
  const ul = $("dirs");
  ul.innerHTML = "";
  const up = document.createElement("li");
  up.textContent = "⬆︎ Subir";
  up.onclick = () => loadDirs(data.parent);
  ul.appendChild(up);
  for (const d of data.dirs) {
    const li = document.createElement("li");
    li.innerHTML = `<span>📁 ${d.name}</span>` +
      (d.raw_count ? `<span class="raw-count">${d.raw_count} RAW</span>` : "");
    li.onclick = () => d.raw_count ? openGallery(d.path) : loadDirs(d.path);
    ul.appendChild(li);
  }
  show("browser");
  $("subtitle").textContent = "Selecciona la carpeta de la sesión (las que tienen RAW se abren como galería)";
}

// --- Pantalla 2: galería ---
async function openGallery(dir) {
  state.dir = dir;
  state.selected.clear();
  const data = await api(`/api/photos?dir=${encodeURIComponent(dir)}`);
  const grid = $("grid");
  grid.innerHTML = "";
  for (const p of data.photos) {
    const div = document.createElement("div");
    div.className = "photo";
    div.dataset.path = p.path;
    div.innerHTML = `<img loading="lazy" src="/api/thumb?path=${encodeURIComponent(p.path)}">` +
      (p.has_xmp ? '<span class="badge">XMP</span>' : "") +
      `<div class="name">${p.name}</div>`;
    div.onclick = () => {
      div.classList.toggle("selected");
      div.classList.contains("selected") ? state.selected.add(p.path)
                                         : state.selected.delete(p.path);
      $("process").disabled = state.selected.size === 0;
      $("process").textContent = `Procesar ${state.selected.size} foto(s)`;
    };
    grid.appendChild(div);
  }
  $("subtitle").textContent = dir;
  $("process").disabled = true;
  $("process").textContent = "Procesar seleccionadas";
  show("gallery");
}

$("back").onclick = () => loadDirs(state.dir ? state.dir.split("/").slice(0, -1).join("/") : "");
$("select-all").onclick = () => {
  document.querySelectorAll(".photo").forEach((el) => {
    el.classList.add("selected");
    state.selected.add(el.dataset.path);
  });
  $("process").disabled = state.selected.size === 0;
  $("process").textContent = `Procesar ${state.selected.size} foto(s)`;
};

// --- Pantalla 3: progreso ---
$("process").onclick = async () => {
  if (Notification.permission === "default") await Notification.requestPermission();
  const body = { files: [...state.selected], overwrite: $("overwrite").checked };
  const { job_id, local_only } = await api("/api/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  show("progress");
  $("done-actions").hidden = true;
  $("log").innerHTML = "";
  state.results = [];
  $("progress-title").textContent = local_only
    ? "Procesando (modo solo local — sin API)…" : "Procesando…";

  const source = new EventSource(`/api/jobs/${job_id}/events`);
  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.type === "photo") {
      state.results.push(ev);
      $("bar-fill").style.width = `${(100 * ev.completed) / ev.total}%`;
      $("progress-text").textContent = `Foto ${ev.completed} de ${ev.total}`;
      const li = document.createElement("li");
      const name = ev.path.split("/").pop();
      const labels = { done: "✓", done_local_only: "✓ (solo local)",
                       skipped_existing: "⏭ ya tenía XMP", error: "✗" };
      li.textContent = `${labels[ev.status] || ev.status} ${name} ${ev.message || ""}`;
      if (ev.status === "error") li.className = "error";
      if (ev.status === "skipped_existing") li.className = "skipped";
      $("log").prepend(li);
    } else if (ev.type === "finished") {
      source.close();
      $("progress-title").textContent = "¡Terminado!";
      $("progress-text").textContent =
        `${ev.ok} de ${ev.total} fotos listas` +
        (ev.errors ? `, ${ev.errors} con error` : "") +
        ". Ya puedes importar la carpeta en Lightroom (o Metadatos → Leer metadatos desde archivos).";
      $("done-actions").hidden = false;
      if (Notification.permission === "granted")
        new Notification("Revelado terminado", { body: $("progress-text").textContent });
    }
  };
};

$("restart").onclick = () => loadDirs(state.dir ? state.dir.split("/").slice(0, -1).join("/") : "");

// --- Pantalla 4: revisión antes/después ---
function adjustedStyle(adjust) {
  if (!adjust) return "";
  const brightness = Math.pow(2, adjust.exposure || 0).toFixed(2);
  const rotate = -(adjust.angle || 0);
  let scale = 1;
  if (adjust.crop) {
    const [l, t, r, b] = adjust.crop;
    scale = 1 / Math.max(0.3, Math.min(r - l, b - t));
  }
  return `filter: brightness(${brightness}); transform: rotate(${rotate}deg) scale(${scale});`;
}

function renderReview() {
  const grid = $("review-grid");
  grid.innerHTML = "";
  for (const ev of state.results.filter((r) => r.status.startsWith("done"))) {
    const name = ev.path.split("/").pop();
    const thumb = `/api/thumb?path=${encodeURIComponent(ev.path)}`;
    const card = document.createElement("div");
    card.className = "review-card";
    card.innerHTML = `
      <div class="pair">
        <div><div class="frame"><img src="${thumb}"></div><div class="caption">Antes</div></div>
        <div><div class="frame"><img src="${thumb}" style="${adjustedStyle(ev.adjust)}"></div>
             <div class="caption">Después${ev.adjust && ev.adjust.masks ? ` · ${ev.adjust.masks} máscara(s)` : ""}</div></div>
      </div>
      <div class="caption">${name}</div>
      <div class="actions">
        <button class="discard">Descartar edición</button>
        <button class="redo">Reprocesar</button>
      </div>`;
    card.querySelector(".discard").onclick = async () => {
      await api(`/api/xmp?path=${encodeURIComponent(ev.path)}`, { method: "DELETE" });
      card.classList.add("discarded");
    };
    card.querySelector(".redo").onclick = async () => {
      card.style.opacity = ".6";
      const { job_id } = await api("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: [ev.path], overwrite: true }),
      });
      const source = new EventSource(`/api/jobs/${job_id}/events`);
      source.onmessage = (msg) => {
        const e = JSON.parse(msg.data);
        if (e.type === "photo") {
          ev.adjust = e.adjust;
          card.classList.remove("discarded");
        }
        if (e.type === "finished") { source.close(); renderReview(); }
      };
    };
    grid.appendChild(card);
  }
  show("review");
}

$("show-review").onclick = renderReview;
$("review-back").onclick = () => show("progress");

loadDirs();
```

- [ ] **Step 3: Run the full test suite** (guards against regressions; `test_index_served` now exercises the real page)

Run: `./.venv/bin/python -m pytest -q`
Expected: all passed

- [ ] **Step 4: Manual smoke test**

Run: `./.venv/bin/python run.py` — browser opens at `http://localhost:8420`.
Verify: folder browser shows home directories; navigating works; a folder with `.CR2/.CR3` (drop test RAWs into `samples/`) opens the gallery with thumbnails; selecting photos enables the button. Stop with Ctrl+C.

- [ ] **Step 5: Commit**

```bash
git add revelado/static run.py && git commit -m "feat: interfaz web (carpetas, galería, progreso SSE)"
```

---

### Task 14: end-to-end acceptance (real RAWs + Lightroom)

This task is manual verification with the user's real files. No new code unless fixes are needed.

- [ ] **Step 1: Real-RAW integration run (local-only)**

With at least 3 real `.CR2`/`.CR3` files in `samples/` (ideally: one with a face in shadow, one tilted horizon, one high ISO): unset `ANTHROPIC_API_KEY`, start the app, process the folder. Expected: all photos end `done_local_only`, `.xmp` files appear next to the RAWs, macOS notification fires.

- [ ] **Step 2: Real API run**

Guide the user to create a key at `console.anthropic.com` if needed; `export ANTHROPIC_API_KEY=...`, delete the sidecars from Step 1 (or tick "Sobrescribir"), reprocess. Expected: statuses `done`; each photo cost ≈ fractions of a cent (Haiku, ~1500px image + ~1K output tokens).

- [ ] **Step 3: Lightroom Classic verification (the real acceptance test)**

Import the `samples/` folder into Lightroom Classic. Verify for each photo:
1. Develop settings applied (temperature, exposure, highlights/shadows, sharpening visible in the Develop panel).
2. Crop and angle applied and editable (press R).
3. Faces in shadow show a radial mask in the Masking panel, affecting only the face region, with local exposure ≈ the computed EV. If the mask affects the *outside* of the ellipse instead of the inside, flip `<crs:Flipped>` in `xmp.py:_mask_xml` and re-run `test_xmp.py` after updating the assertion.
4. A tilted photo is leveled, not doubled — if doubled, flip the sign in `horizon.py:estimate_rotation` (see Task 6 note).
5. Deleting the `.xmp` and re-reading metadata returns the photo to default — proves nothing else was touched.

- [ ] **Step 4: Fix findings, re-run full suite, commit**

```bash
./.venv/bin/python -m pytest -q
git add -A && git commit -m "fix: ajustes tras validación en Lightroom Classic"
```

- [ ] **Step 5: Write README and final commit**

Create `README.md` (Spanish): what it is, `bash scripts/setup.sh`, `export ANTHROPIC_API_KEY=...` (optional — without it runs local-only), `./.venv/bin/python run.py`, the Lightroom workflow (process **before** importing; or *Metadatos → Leer metadatos desde archivos*), and the product rules (never touches RAWs/catalog, delete `.xmp` to undo, never overwrites XMP without the checkbox).

```bash
git add README.md && git commit -m "docs: README de uso"
```
