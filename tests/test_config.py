from pathlib import Path

from revelado.config import SETTINGS


def test_defaults():
    assert SETTINGS.port == 8420
    assert SETTINGS.model == "claude-haiku-4-5"
    assert SETTINGS.preview_long_edge == 1500
    assert SETTINGS.face_lum_threshold == 0.35
    assert SETTINGS.face_lum_target == 0.50
    assert SETTINGS.max_face_ev == 1.5
    assert SETTINGS.max_global_exposure == 1.0
    assert SETTINGS.raw_extensions == (".cr2", ".cr3")
    assert isinstance(SETTINGS.yunet_model_path, Path)
    assert SETTINGS.yunet_model_path.name == "face_detection_yunet_2023mar.onnx"


def test_load_env_file(tmp_path, monkeypatch):
    from revelado.config import load_env_file

    env = tmp_path / ".env"
    env.write_text('# comentario\nANTHROPIC_API_KEY="sk-prueba"\nOTRA=valor\nlinea-invalida\n')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OTRA", "ya-definida")
    load_env_file(env)
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-prueba"
    assert os.environ["OTRA"] == "ya-definida"  # no pisa las existentes
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_load_env_file_missing_is_noop(tmp_path):
    from revelado.config import load_env_file

    load_env_file(tmp_path / "no-existe.env")  # no lanza
