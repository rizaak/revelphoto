import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from revelado.develop import DevelopSettings, RadialMask
from revelado.xmp import (SidecarExists, delete_sidecar, render_xmp,
                          sidecar_path, write_sidecar)

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"


def _settings(masks=()):
    return DevelopSettings(
        temperature=5300, tint=8, exposure=0.35, contrast=12, highlights=-25,
        shadows=30, whites=0, blacks=-5, sharpness=45, luminance_smoothing=15,
        has_crop=True, crop_left=0.05, crop_top=0.02, crop_right=0.98,
        crop_bottom=0.95, crop_angle=-1.2, masks=list(masks), ai_used=True)


def test_sidecar_path():
    assert sidecar_path(Path("/a/IMG_1.CR3")) == Path("/a/IMG_1.xmp")


def test_render_is_valid_xml_with_crs_values():
    root = ET.fromstring(render_xmp(_settings()))
    desc = root.find(f".//{{{'http://www.w3.org/1999/02/22-rdf-syntax-ns#'}}}Description")
    assert desc.get(f"{{{CRS}}}Temperature") == "5300"
    assert desc.get(f"{{{CRS}}}Exposure2012") == "+0.35"
    assert desc.get(f"{{{CRS}}}Highlights2012") == "-25"
    assert desc.get(f"{{{CRS}}}HasCrop") == "True"
    assert desc.get(f"{{{CRS}}}CropAngle") == "-1.200000"
    assert desc.get(f"{{{CRS}}}CropLeft") == "0.050000"
    assert desc.get(f"{{{CRS}}}Sharpness") == "45"
    assert desc.get(f"{{{CRS}}}LuminanceSmoothing") == "15"
    assert desc.get(f"{{{CRS}}}HasSettings") == "True"


def test_render_mask_normalization():
    mask = RadialMask(left=0.3, top=0.2, right=0.6, bottom=0.5,
                      exposure_ev=1.0, shadows=25)
    text = render_xmp(_settings([mask]))
    assert "CircularGradientBasedCorrections" in text
    assert 'crs:LocalExposure2012="0.250000"' in text  # 1.0 EV / 4
    assert 'crs:LocalShadows2012="0.250000"' in text   # 25 / 100
    assert "<crs:Top>0.200000</crs:Top>" in text
    ET.fromstring(text)  # sigue siendo XML válido


def test_render_as_shot_when_no_temperature():
    s = _settings()
    s.temperature = None
    text = render_xmp(s)
    assert 'crs:WhiteBalance="As Shot"' in text
    assert "crs:Temperature=" not in text
    assert "crs:Tint=" not in text
    ET.fromstring(text)  # sigue siendo XML válido


def test_render_without_crop_or_masks():
    s = _settings()
    s.has_crop = False
    s.masks = []
    text = render_xmp(s)
    assert 'crs:HasCrop="False"' in text
    assert "CircularGradientBasedCorrections" not in text


def test_write_respects_existing(tmp_path):
    raw = tmp_path / "IMG_2.CR2"
    raw.write_bytes(b"fake")
    out = write_sidecar(raw, _settings())
    assert out.exists() and out.suffix == ".xmp"
    with pytest.raises(SidecarExists):
        write_sidecar(raw, _settings())
    write_sidecar(raw, _settings(), overwrite=True)  # no lanza


def test_delete(tmp_path):
    raw = tmp_path / "IMG_3.CR2"
    raw.write_bytes(b"fake")
    write_sidecar(raw, _settings())
    assert delete_sidecar(raw) is True
    assert delete_sidecar(raw) is False
