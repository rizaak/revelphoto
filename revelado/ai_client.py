"""Clientes de IA: Anthropic nativo o Google Gemini tras un adaptador.

El resto de la app habla el dialecto de Anthropic (messages.create con
bloques de imagen base64, output_config con JSON Schema, response.content
con bloques .type/.text y response.stop_reason). El adaptador de Gemini
traduce ese dialecto completo: imágenes incluidas y respuesta forzada al
mismo JSON Schema, así ai.py no sabe qué proveedor hay detrás.
"""
import base64
import os

from revelado.config import SETTINGS


class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _Response:
    stop_reason = "end_turn"

    def __init__(self, text: str):
        self.content = [_TextBlock(text)]


class _GeminiMessages:
    def __init__(self, client):
        self._client = client

    def create(self, *, model: str, max_tokens: int, system: str,
               messages: list, output_config: dict | None = None) -> _Response:
        from google.genai import types
        parts = []
        for msg in messages:
            blocks = msg["content"]
            if isinstance(blocks, str):
                blocks = [{"type": "text", "text": blocks}]
            for b in blocks:
                if b["type"] == "image":
                    parts.append(types.Part.from_bytes(
                        data=base64.b64decode(b["source"]["data"]),
                        mime_type=b["source"]["media_type"]))
                else:
                    parts.append(types.Part.from_text(text=b["text"]))
        config = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=max_tokens)
        if output_config is not None:
            config.response_mime_type = "application/json"
            config.response_json_schema = output_config["format"]["schema"]
        if "flash" in model:
            # Sin "pensamiento": consumiría el presupuesto de tokens de la
            # respuesta y la dejaría vacía (los modelos pro no permiten quitarlo)
            config.thinking_config = types.ThinkingConfig(thinking_budget=0)
        response = self._client.models.generate_content(
            model=model, contents=parts, config=config)
        # Los errores de red/API burbujean: ai.py ya los convierte en
        # AIUnavailable y reintenta; aquí no se traga nada en silencio.
        return _Response(response.text or "")


class GeminiClient:
    """Expone .messages.create como el SDK de Anthropic."""

    def __init__(self, client=None):
        if client is None:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.messages = _GeminiMessages(client)


def get_ai_client():
    """Cliente según AI_PROVIDER en .env; None => modo solo-local."""
    if SETTINGS.ai_provider == "google":
        if not os.getenv("GEMINI_API_KEY"):
            return None
        return GeminiClient()
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()
