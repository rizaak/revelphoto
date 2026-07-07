import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from revelado.ai import AIUnavailable
from revelado.config import SETTINGS
from revelado.jobs import JobManager
from revelado.learn import (apply_learned_style, collect_stats,
                            read_xmp_settings, summarize_style)
from revelado.server import create_app


def _lr_xmp(exposure="+0.30", contrast="15", temp="5200", wb="Custom"):
    """XMP como los que escribe Lightroom (atributos, xmptk de Adobe)."""
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   crs:Exposure2012="{exposure}"
   crs:Contrast2012="{contrast}"
   crs:Shadows2012="+20"
   crs:WhiteBalance="{wb}"
   crs:Temperature="{temp}"
   crs:Tint="+8"/>
 </rdf:RDF>
</x:xmpmeta>
"""


def test_lee_ajustes_en_forma_atributo(tmp_path):
    p = tmp_path / "IMG_1.xmp"
    p.write_text(_lr_xmp())
    v = read_xmp_settings(p)
    assert v["Exposure2012"] == 0.30
    assert v["Contrast2012"] == 15
    assert v["WhiteBalance"] == "Custom"
    assert v["Temperature"] == 5200


def test_lee_ajustes_en_forma_elemento(tmp_path):
    p = tmp_path / "IMG_1.xmp"
    p.write_text('<rdf:Description xmlns:crs="x"><crs:Exposure2012>-0.5</crs:Exposure2012>'
                 "<crs:Vibrance>25</crs:Vibrance></rdf:Description>")
    v = read_xmp_settings(p)
    assert v == {"Exposure2012": -0.5, "Vibrance": 25}


def test_ignora_los_xmp_de_revelado(tmp_path):
    p = tmp_path / "IMG_1.xmp"
    p.write_text('<x:xmpmeta x:xmptk="revelado"><rdf:Description '
                 'crs:Exposure2012="+1.00"/></x:xmpmeta>')
    assert read_xmp_settings(p) is None


def test_ignora_xmp_sin_ajustes(tmp_path):
    p = tmp_path / "nota.xmp"
    p.write_text("<x:xmpmeta>sin nada de camera raw</x:xmpmeta>")
    assert read_xmp_settings(p) is None


def test_collect_stats_medianas(tmp_path):
    for i, expo in enumerate(("+0.10", "+0.30", "+0.50")):
        (tmp_path / f"IMG_{i}.xmp").write_text(_lr_xmp(exposure=expo))
    (tmp_path / "propio.xmp").write_text('<x:xmpmeta x:xmptk="revelado" crs:x="1"/>')
    stats = collect_stats(tmp_path)
    assert stats["count"] == 3
    assert stats["sliders"]["Exposure2012"]["mediana"] == 0.30
    assert stats["sliders"]["Exposure2012"]["fotos"] == 3
    assert stats["balance_blancos"] == {"Custom": 3}


def test_collect_stats_recursivo_y_vacio(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "IMG_1.xmp").write_text(_lr_xmp())
    assert collect_stats(tmp_path)["count"] == 1
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    assert collect_stats(vacia)["count"] == 0


def test_apply_crea_y_reemplaza_bloque(tmp_path):
    style = tmp_path / "estilo.txt"
    style.write_text("# comentario\nMi preferencia manual.\n")
    apply_learned_style("Sombras abiertas.\nContraste suave.", path=style)
    text = style.read_text()
    assert "Mi preferencia manual." in text
    assert "Sombras abiertas." in text
    assert text.count("Estilo aprendido") == 1
    # Reaprender reemplaza el bloque, no lo duplica
    apply_learned_style("Colores vivos.", path=style)
    text = style.read_text()
    assert "Sombras abiertas." not in text
    assert "Colores vivos." in text
    assert "Mi preferencia manual." in text
    assert text.count("# === Estilo aprendido") == 1


def test_apply_sin_estilo_previo(tmp_path):
    style = tmp_path / "estilo.txt"
    apply_learned_style("Piel luminosa.", path=style)
    assert "Piel luminosa." in style.read_text()


def _client_returning(text):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
    )
    return client


def test_summarize_style_ok():
    client = _client_returning("  Sombras abiertas.\nCálido sutil.  ")
    out = summarize_style(client, {"count": 9, "sliders": {}})
    assert out == "Sombras abiertas.\nCálido sutil."
    kwargs = client.messages.create.call_args.kwargs
    assert "9" in kwargs["messages"][0]["content"]


def test_summarize_style_error_degrada():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("red caída")
    with pytest.raises(AIUnavailable):
        summarize_style(client, {})


def _app_client(api_client):
    app = create_app(job_manager=JobManager(on_finish=MagicMock()),
                     client_factory=lambda: api_client)
    return TestClient(app)


def test_ruta_learn_completa(tmp_path):
    for i in range(5):
        (tmp_path / f"IMG_{i}.xmp").write_text(_lr_xmp())
    style = tmp_path / "estilo.txt"
    fake_settings = replace(SETTINGS, style_path=style)
    with patch("revelado.learn.SETTINGS", fake_settings):
        r = _app_client(_client_returning("Contraste suave.")).post(
            "/api/style/learn", json={"dir": str(tmp_path)})
    assert r.status_code == 200
    assert r.json() == {"count": 5, "summary": "Contraste suave."}
    assert "Contraste suave." in style.read_text()


def test_ruta_learn_pocos_xmp(tmp_path):
    (tmp_path / "IMG_1.xmp").write_text(_lr_xmp())
    r = _app_client(_client_returning("x")).post("/api/style/learn",
                                                 json={"dir": str(tmp_path)})
    assert r.status_code == 400
    assert "5" in r.json()["detail"]


def test_ruta_learn_sin_api(tmp_path):
    assert _app_client(None).post("/api/style/learn",
                                  json={"dir": str(tmp_path)}).status_code == 503


def test_ruta_learn_carpeta_inexistente():
    r = _app_client(_client_returning("x")).post(
        "/api/style/learn", json={"dir": "/no/existe"})
    assert r.status_code == 404
