import base64
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from revelado.ai_client import GeminiClient, get_ai_client
from revelado.config import SETTINGS, default_model_for


class FakeModels:
    def __init__(self, text):
        self.calls = []
        self._text = text

    def generate_content(self, *, model, contents, config):
        self.calls.append((model, contents, config))
        return SimpleNamespace(text=self._text)


def _gemini(text='{"ok": true}'):
    fake = SimpleNamespace(models=FakeModels(text))
    return GeminiClient(client=fake), fake.models


def test_gemini_envia_imagenes_y_schema():
    cli, models = _gemini()
    resp = cli.messages.create(
        model="gemini-2.5-flash", max_tokens=100, system="sys",
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.standard_b64encode(b"JPG").decode()}},
            {"type": "text", "text": "hola"},
        ]}],
        output_config={"format": {"type": "json_schema",
                                  "schema": {"type": "object"}}})
    model, contents, config = models.calls[0]
    assert contents[0].inline_data.data == b"JPG"          # la foto viaja
    assert contents[0].inline_data.mime_type == "image/jpeg"
    assert contents[1].text == "hola"
    assert config.system_instruction == "sys"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == {"type": "object"}
    # y la respuesta habla el dialecto que ai.py espera
    assert resp.stop_reason != "refusal"
    assert next(b.text for b in resp.content if b.type == "text") == '{"ok": true}'


def test_gemini_flash_sin_pensamiento():
    cli, models = _gemini()
    cli.messages.create(model="gemini-2.5-flash", max_tokens=50, system="s",
                        messages=[{"role": "user", "content": "hola"}])
    _, _, config = models.calls[0]
    assert config.thinking_config.thinking_budget == 0


def test_gemini_respuesta_vacia_no_revienta():
    cli, _ = _gemini(text=None)
    resp = cli.messages.create(model="gemini-2.5-flash", max_tokens=50, system="s",
                               messages=[{"role": "user", "content": "hola"}])
    assert resp.content[0].text == ""


def test_get_ai_client_none_sin_clave_gemini(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake = replace(SETTINGS, ai_provider="google")
    with patch("revelado.ai_client.SETTINGS", fake):
        assert get_ai_client() is None


def test_modelo_por_defecto_segun_proveedor():
    assert default_model_for("google") == "gemini-2.5-flash"
    assert default_model_for("anthropic") == "claude-haiku-4-5"
