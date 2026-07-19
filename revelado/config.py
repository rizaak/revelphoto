import os
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path = _ROOT / ".env") -> None:
    """Carga variables tipo KEY=VALOR desde un .env (sin pisar las ya definidas)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def default_model_for(provider: str) -> str:
    """Cada proveedor con su modelo por defecto (AI_MODEL en .env lo pisa)."""
    return "gemini-2.5-flash" if provider == "google" else "claude-haiku-4-5"


@dataclass(frozen=True)
class Settings:
    port: int = 8420
    ai_provider: str = os.getenv("AI_PROVIDER", "anthropic")  # anthropic, google
    model: str = os.getenv("AI_MODEL") or default_model_for(
        os.getenv("AI_PROVIDER", "anthropic"))
    preview_long_edge: int = 1500
    cull_long_edge: int = 3600   # resolución de los recortes de cara para el culling
    thumb_long_edge: int = 400
    face_lum_threshold: float = 0.35
    face_lum_target: float = 0.50
    max_face_ev: float = 1.5
    min_face_ev: float = -0.5        # oscurecer una cara quemada, como mucho
    min_face_lift_apply: float = 0.1  # por debajo no vale la pena una máscara
    max_global_exposure: float = 1.0
    max_total_exposure: float = 1.5  # tope con el sesgo de sesión incluido
    max_crop_angle: float = 10.0
    max_temp_shift: int = 1500      # desviación máxima de WB (Kelvin) respecto al de cámara
    max_tint_shift: int = 40
    min_temp_shift_apply: int = 100  # por debajo, se respeta el "As Shot" tal cual
    min_tint_shift_apply: int = 5
    style_path: Path = _ROOT / "estilo.txt"
    presets_path: Path = _ROOT / "presets.json"
    burst_gap: int = 2             # segundos entre tomas para considerarlas ráfaga
    blur_ratio: float = 0.2        # nitidez < 20% de la mediana de la sesión => desenfocada
    learn_min_xmp: int = 5         # mínimo de XMP editados para aprender el estilo
    harmony_time_gap: int = 480     # segundos entre tomas para considerar nueva escena
    harmony_wb_delta: int = 400     # cambio de WB de cámara (K) que marca nueva escena
    worker_concurrency: int = 4
    api_max_tokens: int = 1024
    raw_extensions: tuple[str, ...] = (".cr2", ".cr3")
    yunet_model_path: Path = _ROOT / "models" / "face_detection_yunet_2023mar.onnx"
    cache_dir: Path = Path.home() / ".cache" / "revelado"


SETTINGS = Settings()
