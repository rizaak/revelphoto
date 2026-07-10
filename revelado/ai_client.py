"""Adaptador para múltiples proveedores de IA (Anthropic, Google Gemini)."""
import os

from revelado.config import SETTINGS


class MessageContent:
    """Simula el formato de respuesta de Anthropic."""
    def __init__(self, text: str):
        self.text = text


class MessageResponse:
    """Simula la respuesta de Anthropic."""
    def __init__(self, text: str):
        self.content = [MessageContent(text)]


class AnthropicWrapper:
    """Wrapper que devuelve el cliente de Anthropic directamente."""

    def __init__(self):
        import anthropic
        self.messages = anthropic.Anthropic().messages

    def create(self, model: str, max_tokens: int, system: str, messages: list):
        return self.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )


class GoogleGeminiWrapper:
    """Wrapper que adapta Google Gemini a la interfaz de Anthropic."""

    def __init__(self):
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY no está definida en .env")
        genai.configure(api_key=api_key)
        self.genai = genai

    class Messages:
        def __init__(self, genai_module):
            self.genai = genai_module

        def create(self, model: str, max_tokens: int, system: str, messages: list):
            """Adapta llamada Anthropic a Gemini."""
            # Convertir messages al formato de Gemini
            gemini_messages = []

            for msg in messages:
                role = msg["role"]
                content = msg["content"]

                # Extraer texto
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part["text"])
                    text = "\n".join(text_parts)
                else:
                    text = str(content)

                gemini_messages.append({
                    "role": "user" if role == "user" else "model",
                    "parts": [{"text": text}]
                })

            # Incluir system prompt en el primer mensaje
            if gemini_messages and system:
                first_text = gemini_messages[0]["parts"][0]["text"]
                gemini_messages[0]["parts"][0]["text"] = f"{system}\n\n{first_text}"

            # Llamada a Gemini
            try:
                model_obj = self.genai.GenerativeModel(model)
                response = model_obj.generate_content(
                    gemini_messages,
                    generation_config={"max_output_tokens": max_tokens},
                )
                return MessageResponse(response.text)
            except Exception as e:
                raise RuntimeError(f"Gemini API error: {e}")

    def __init__(self, genai_module):
        self.genai = genai_module
        self.messages = self.Messages(genai_module)


def get_ai_client():
    """Obtiene cliente de IA según la configuración (compatible con Anthropic API)."""
    try:
        if SETTINGS.ai_provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            wrapper = GoogleGeminiWrapper(genai)
            return wrapper
        else:  # anthropic (default)
            return AnthropicWrapper()
    except Exception:
        return None
