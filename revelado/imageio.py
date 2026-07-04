import cv2
import numpy as np

# Rotaciones por valor EXIF Orientation (solo las de cámara: 1,3,6,8)
_ROTATIONS = {
    3: cv2.ROTATE_180,
    6: cv2.ROTATE_90_CLOCKWISE,
    8: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def decode_upright(jpeg: bytes, orientation: int, max_edge: int) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("JPEG ilegible")
    rot = _ROTATIONS.get(orientation)
    if rot is not None:
        img = cv2.rotate(img, rot)
    h, w = img.shape[:2]
    long_edge = max(h, w)
    if long_edge > max_edge:
        scale = max_edge / long_edge
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("No se pudo codificar JPEG")
    return buf.tobytes()
