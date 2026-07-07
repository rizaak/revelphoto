import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from revelado.exif import ExifData
from revelado.jobs import JobManager
from revelado.pipeline import PhotoAnalysis, PhotoResult
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
    with patch("revelado.server.analyze_photo", return_value=PhotoAnalysis(raw)), \
         patch("revelado.server.finalize_photo", return_value=fake):
        with _client() as client:  # portal único: la tarea de fondo sobrevive entre peticiones
            r = client.post("/api/process", json={"files": [str(raw)], "overwrite": False})
            assert r.status_code == 200
            job_id = r.json()["job_id"]
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


def test_preview_returns_simulated_jpeg(tmp_path):
    raw = tmp_path / "IMG_1.CR3"
    raw.write_bytes(b"x")
    img = np.full((100, 150, 3), 90, dtype=np.uint8)
    with patch("revelado.server.read_exif", return_value=ExifData(100, 1, 0, 0)), \
         patch("revelado.server.extract_preview_jpeg", return_value=b"\xff\xd8x"), \
         patch("revelado.server.decode_upright", return_value=img):
        r = _client().get("/api/preview", params={
            "path": str(raw), "exposure": 0.5, "temp_shift": 400,
            "crop": "0.1,0.1,0.9,0.9"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content.startswith(b"\xff\xd8")


def test_preview_bad_crop_param(tmp_path):
    raw = tmp_path / "IMG_1.CR3"
    raw.write_bytes(b"x")
    img = np.full((50, 50, 3), 90, dtype=np.uint8)
    with patch("revelado.server.read_exif", return_value=ExifData(100, 1, 0, 0)), \
         patch("revelado.server.extract_preview_jpeg", return_value=b"\xff\xd8x"), \
         patch("revelado.server.decode_upright", return_value=img):
        r = _client().get("/api/preview", params={"path": str(raw), "crop": "no-valido"})
    assert r.status_code == 400


def test_bulk_xmp_delete(tmp_path):
    for i in (1, 2, 3):
        (tmp_path / f"IMG_{i}.CR3").write_bytes(b"x")
    (tmp_path / "IMG_1.xmp").write_text("x")
    (tmp_path / "IMG_2.xmp").write_text("x")
    r = _client().post("/api/xmp/delete", json={
        "files": [str(tmp_path / f"IMG_{i}.CR3") for i in (1, 2, 3)]})
    assert r.json()["deleted"] == 2  # la 3 no tenía XMP
    assert not (tmp_path / "IMG_1.xmp").exists()
    assert (tmp_path / "IMG_1.CR3").exists()  # el RAW intacto


def test_process_ejecuta_armonia_y_rafagas_segun_opciones(tmp_path):
    raws = []
    for i in (1, 2):
        raw = tmp_path / f"IMG_{i}.CR3"
        raw.write_bytes(b"x")
        raws.append(str(raw))
    fake = PhotoResult(raws[0], "done")
    with patch("revelado.server.analyze_photo",
               side_effect=lambda p, *a, **k: PhotoAnalysis(p)), \
         patch("revelado.server.finalize_photo", return_value=fake), \
         patch("revelado.server.harmonize") as mock_harm, \
         patch("revelado.server.rank_bursts") as mock_rank:
        with _client() as client:
            r = client.post("/api/process", json={"files": raws})
            _drain(client, r.json()["job_id"])
            assert mock_harm.call_count == 1
            assert mock_rank.call_count == 1
            # con las casillas apagadas no se llama ninguna
            r = client.post("/api/process", json={"files": raws,
                                                  "harmonize": False, "rate": False})
            _drain(client, r.json()["job_id"])
            assert mock_harm.call_count == 1
            assert mock_rank.call_count == 1


def _drain(client, job_id):
    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: ") and '"finished"' in line:
                break
