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
