from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from revelado.config import SETTINGS
from revelado.jobs import JobManager
from revelado.presets import delete_preset, list_presets, save_preset
from revelado.server import create_app


def test_sin_archivo_no_hay_presets(tmp_path):
    assert list_presets(tmp_path / "presets.json") == []


def test_archivo_corrupto_equivale_a_vacio(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("esto no es json")
    assert list_presets(path) == []


def test_guardar_listar_ordenado(tmp_path):
    path = tmp_path / "presets.json"
    save_preset("Estudio", "luz suave", 0.2, -100, path=path)
    save_preset("bodas exterior", "cálido", -0.1, 200, path=path)
    names = [p["name"] for p in list_presets(path)]
    assert names == ["bodas exterior", "Estudio"]  # orden alfabético sin mayúsculas


def test_guardar_reemplaza_mismo_nombre(tmp_path):
    path = tmp_path / "presets.json"
    save_preset("Estudio", "v1", path=path)
    save_preset("Estudio", "v2", 0.5, 300, path=path)
    presets = list_presets(path)
    assert len(presets) == 1
    assert presets[0] == {"name": "Estudio", "prompt": "v2",
                          "exposure_bias": 0.5, "temp_bias": 300}


def test_nombre_vacio_rechazado(tmp_path):
    with pytest.raises(ValueError):
        save_preset("   ", path=tmp_path / "presets.json")


def test_borrar(tmp_path):
    path = tmp_path / "presets.json"
    save_preset("Estudio", path=path)
    assert delete_preset("Estudio", path=path) is True
    assert delete_preset("Estudio", path=path) is False
    assert list_presets(path) == []


def _client():
    app = create_app(job_manager=JobManager(on_finish=MagicMock()),
                     client_factory=lambda: None)
    return TestClient(app)


def test_rutas_de_presets(tmp_path):
    fake = replace(SETTINGS, presets_path=tmp_path / "presets.json")
    with patch("revelado.presets.SETTINGS", fake):
        c = _client()
        assert c.get("/api/presets").json() == {"presets": []}
        r = c.post("/api/presets", json={"name": " Estudio ", "prompt": "suave",
                                         "exposure_bias": 5.0, "temp_bias": -9999})
        assert r.status_code == 200
        saved = r.json()
        assert saved["name"] == "Estudio"          # sin espacios
        assert saved["exposure_bias"] == 1.0       # topes de sesión
        assert saved["temp_bias"] == -800
        assert [p["name"] for p in c.get("/api/presets").json()["presets"]] == ["Estudio"]
        assert c.post("/api/presets", json={"name": "  "}).status_code == 400
        assert c.delete("/api/presets", params={"name": "Estudio"}).json()["deleted"] is True
        assert c.delete("/api/presets", params={"name": "Estudio"}).json()["deleted"] is False
