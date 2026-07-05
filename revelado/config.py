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
    wb_cast_temp_delta: int = 800   # desviación de 5500K que consideramos dominante de color
    wb_cast_tint: int = 25
    worker_concurrency: int = 4
    api_max_tokens: int = 1024
    raw_extensions: tuple[str, ...] = (".cr2", ".cr3")
    yunet_model_path: Path = _ROOT / "models" / "face_detection_yunet_2023mar.onnx"
    cache_dir: Path = Path.home() / ".cache" / "revelado"


SETTINGS = Settings()
