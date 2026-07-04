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
