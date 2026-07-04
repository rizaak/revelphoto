from pathlib import Path

from revelado.develop import DevelopSettings, RadialMask


class SidecarExists(Exception):
    """Ya existe un XMP para esta foto; se necesita confirmación para sobrescribir."""


def sidecar_path(raw_path: Path) -> Path:
    return raw_path.with_suffix(".xmp")


def _fmt_signed_float(v: float) -> str:
    return f"{v:+.2f}" if v != 0 else "0.00"


def _fmt_signed_int(v: int) -> str:
    return f"{v:+d}" if v != 0 else "0"


def _mask_xml(m: RadialMask) -> str:
    return f"""    <rdf:li>
     <rdf:Description
      crs:What="Correction"
      crs:CorrectionAmount="1.000000"
      crs:CorrectionActive="true"
      crs:LocalExposure2012="{m.exposure_ev / 4:.6f}"
      crs:LocalShadows2012="{m.shadows / 100:.6f}"
      crs:LocalContrast2012="0.000000"
      crs:LocalHighlights2012="0.000000">
      <crs:CorrectionMasks>
       <rdf:Seq>
        <rdf:li rdf:parseType="Resource">
         <crs:What>Mask/CircularGradient</crs:What>
         <crs:MaskValue>1.000000</crs:MaskValue>
         <crs:Top>{m.top:.6f}</crs:Top>
         <crs:Left>{m.left:.6f}</crs:Left>
         <crs:Bottom>{m.bottom:.6f}</crs:Bottom>
         <crs:Right>{m.right:.6f}</crs:Right>
         <crs:Angle>0</crs:Angle>
         <crs:Midpoint>50</crs:Midpoint>
         <crs:Roundness>0</crs:Roundness>
         <crs:Feather>75</crs:Feather>
         <crs:Flipped>true</crs:Flipped>
         <crs:Version>2</crs:Version>
        </rdf:li>
       </rdf:Seq>
      </crs:CorrectionMasks>
     </rdf:Description>
    </rdf:li>"""


def render_xmp(s: DevelopSettings) -> str:
    crop_attrs = ""
    if s.has_crop:
        crop_attrs = f"""
   crs:CropLeft="{s.crop_left:.6f}"
   crs:CropTop="{s.crop_top:.6f}"
   crs:CropRight="{s.crop_right:.6f}"
   crs:CropBottom="{s.crop_bottom:.6f}"
   crs:CropAngle="{s.crop_angle:.6f}\""""

    masks_xml = ""
    if s.masks:
        items = "\n".join(_mask_xml(m) for m in s.masks)
        masks_xml = f"""
   <crs:CircularGradientBasedCorrections>
    <rdf:Seq>
{items}
    </rdf:Seq>
   </crs:CircularGradientBasedCorrections>"""

    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="revelado">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   crs:Version="11.0"
   crs:ProcessVersion="11.0"
   crs:WhiteBalance="Custom"
   crs:Temperature="{s.temperature}"
   crs:Tint="{_fmt_signed_int(s.tint)}"
   crs:Exposure2012="{_fmt_signed_float(s.exposure)}"
   crs:Contrast2012="{_fmt_signed_int(s.contrast)}"
   crs:Highlights2012="{_fmt_signed_int(s.highlights)}"
   crs:Shadows2012="{_fmt_signed_int(s.shadows)}"
   crs:Whites2012="{_fmt_signed_int(s.whites)}"
   crs:Blacks2012="{_fmt_signed_int(s.blacks)}"
   crs:Sharpness="{s.sharpness}"
   crs:LuminanceSmoothing="{s.luminance_smoothing}"
   crs:HasCrop="{'True' if s.has_crop else 'False'}"{crop_attrs}
   crs:HasSettings="True">{masks_xml}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


def write_sidecar(raw_path: Path, s: DevelopSettings, overwrite: bool = False) -> Path:
    path = sidecar_path(raw_path)
    if path.exists() and not overwrite:
        raise SidecarExists(str(path))
    path.write_text(render_xmp(s), encoding="utf-8")
    return path


def delete_sidecar(raw_path: Path) -> bool:
    path = sidecar_path(raw_path)
    if path.exists():
        path.unlink()
        return True
    return False
