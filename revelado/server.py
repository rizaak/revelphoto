import hashlib
import json
import os
from pathlib import Path

import anthropic
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from revelado.ai import AIUnavailable
from revelado.config import SETTINGS
from revelado.cull import flag_blurry, rank_bursts
from revelado.drive import list_drive_files
from revelado.exif import extract_preview_jpeg, read_exif
from revelado.learn import apply_learned_style, collect_stats, summarize_style
from revelado.imageio import decode_upright, encode_jpeg
from revelado.jobs import JobManager
from revelado.harmonize import harmonize
from revelado.lrcat import CatalogLocked, find_catalogs
from revelado.lrcat import photos as lrcat_photos
from revelado.lrcat import sources as lrcat_sources
from revelado.pipeline import analyze_photo, finalize_photo
from revelado.presets import delete_preset, list_presets, save_preset
from revelado.simulate import simulate
from revelado.xmp import delete_sidecar, sidecar_path

_STATIC = Path(__file__).parent / "static"


def _default_client_factory():
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


class XmpDeleteRequest(BaseModel):
    files: list[str]


class LearnRequest(BaseModel):
    dir: str


class PresetRequest(BaseModel):
    name: str
    prompt: str = ""
    exposure_bias: float = 0.0
    temp_bias: int = 0


class ProcessRequest(BaseModel):
    files: list[str]
    overwrite: bool = False
    harmonize: bool = True  # armonía de sesión: mismo look por escena
    rate: bool = True            # puntuar con estrellas 1-5 (culling)
    exposure_bias: float = 0.0   # sesgo de sesión: más oscuras/claras (EV)
    temp_bias: int = 0           # sesgo de sesión: más frías/cálidas (Kelvin)
    session_prompt: str = ""     # indicaciones del fotógrafo para esta sesión


def _thumb_bytes(raw: Path) -> bytes:
    """Miniatura JPEG vertical-correcta, cacheada por ruta+mtime."""
    if not raw.exists():
        raise HTTPException(404, "Archivo no encontrado")
    cache_dir = SETTINGS.cache_dir / "thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{raw}:{raw.stat().st_mtime}".encode()).hexdigest()
    cached = cache_dir / f"{key}.jpg"
    if not cached.exists():
        try:
            exif = read_exif(raw)
            jpeg = extract_preview_jpeg(raw)
            img = decode_upright(jpeg, exif.orientation, SETTINGS.thumb_long_edge)
            cached.write_bytes(encode_jpeg(img, quality=80))
        except Exception as exc:
            raise HTTPException(404, f"Sin miniatura: {exc}")
    return cached.read_bytes()


def create_app(job_manager: JobManager | None = None, client_factory=None) -> FastAPI:
    app = FastAPI(title="Revelado")
    manager = job_manager or JobManager()
    make_client = client_factory or _default_client_factory

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.get("/api/browse")
    def browse(path: str = ""):
        base = Path(path).expanduser() if path else Path.home()
        if not base.is_dir():
            raise HTTPException(404, "Carpeta no encontrada")
        dirs = []
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                if os.access(child, os.R_OK):
                    # Contar RAW locales
                    count = sum(1 for f in child.iterdir()
                                if f.suffix.lower() in SETTINGS.raw_extensions)
                    # Agregar RAW de Google Drive sin sincronizar
                    drive_files = list_drive_files(child)
                    count += sum(1 for f in drive_files
                                if Path(f).suffix.lower() in SETTINGS.raw_extensions)
                else:
                    count = 0
                dirs.append({"name": child.name, "path": str(child),
                             "raw_count": count})
        return {"path": str(base), "parent": str(base.parent), "dirs": dirs}

    @app.get("/api/photos")
    def photos(dir: str):
        base = Path(dir).expanduser()
        if not base.is_dir():
            raise HTTPException(404, "Carpeta no encontrada")
        # Listar RAW locales
        items = set(f for f in base.iterdir()
                    if f.suffix.lower() in SETTINGS.raw_extensions)
        # Agregar RAW de Google Drive sin sincronizar
        drive_files = list_drive_files(base)
        for fname in drive_files:
            if Path(fname).suffix.lower() in SETTINGS.raw_extensions:
                fpath = base / fname
                items.add(fpath)
        # Ordenar por nombre
        items = sorted(items, key=lambda f: f.name)
        return {"photos": [{"name": f.name, "path": str(f),
                            "has_xmp": sidecar_path(f).exists()} for f in items]}

    @app.get("/api/thumb")
    def thumb(path: str):
        return Response(_thumb_bytes(Path(path)), media_type="image/jpeg")

    @app.get("/api/preview")
    def preview(path: str, exposure: float = 0.0, contrast: int = 0,
                highlights: int = 0, shadows: int = 0, temp_shift: int = 0,
                tint: int = 0, angle: float = 0.0, crop: str = ""):
        """Miniatura con los ajustes simulados (aproximación del resultado en LR)."""
        img = cv2.imdecode(np.frombuffer(_thumb_bytes(Path(path)), np.uint8),
                           cv2.IMREAD_COLOR)
        crop_rect = None
        if crop:
            try:
                left, top, right, bottom = (float(v) for v in crop.split(","))
                crop_rect = (left, top, right, bottom)
            except ValueError:
                raise HTTPException(400, "Parámetro crop inválido")
        out = simulate(img, exposure=exposure, contrast=contrast,
                       highlights=highlights, shadows=shadows,
                       temp_shift=temp_shift, tint=tint, angle=angle,
                       crop=crop_rect)
        return Response(encode_jpeg(out, quality=80), media_type="image/jpeg")

    @app.get("/api/lrcat/catalogs")
    def lr_catalogs():
        return {"catalogs": [{"path": str(c), "name": c.stem}
                             for c in find_catalogs()]}

    @app.get("/api/lrcat/sources")
    def lr_sources(cat: str):
        cat_path = Path(cat)
        if not cat_path.exists():
            raise HTTPException(404, "Catálogo no encontrado")
        try:
            return lrcat_sources(cat_path)
        except CatalogLocked:
            raise HTTPException(423, "El catálogo está bloqueado por Lightroom; ciérralo e inténtalo de nuevo")

    @app.get("/api/lrcat/photos")
    def lr_photos(cat: str, type: str, id: int):
        if type not in ("folder", "collection"):
            raise HTTPException(400, "type debe ser folder o collection")
        try:
            paths = lrcat_photos(Path(cat), type, id)
        except CatalogLocked:
            raise HTTPException(423, "El catálogo está bloqueado por Lightroom; ciérralo e inténtalo de nuevo")
        return {"photos": [{"name": p.name, "path": str(p),
                            "has_xmp": sidecar_path(p).exists(),
                            "missing": not p.exists()} for p in paths]}

    @app.post("/api/process")
    async def process(req: ProcessRequest):
        paths = [Path(f) for f in req.files]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise HTTPException(400, f"Archivos inexistentes: {missing[0]}")
        client = make_client()
        exposure_bias = min(max(req.exposure_bias, -1.0), 1.0)
        temp_bias = min(max(req.temp_bias, -800), 800)
        analyzer = lambda p, ow: analyze_photo(p, ow, client,
                                               session_prompt=req.session_prompt)
        finalizer = lambda a, ow: finalize_photo(a, ow, exposure_bias=exposure_bias,
                                                 temp_bias=temp_bias, rate=req.rate)
        do_harmony = req.harmonize and len(paths) > 1
        do_bursts = req.rate and len(paths) > 1
        harmonizer = None
        if do_harmony or do_bursts:
            def harmonizer(analyses):
                if do_harmony:
                    harmonize(analyses)
                if do_bursts:
                    flag_blurry(analyses)  # antes que las ráfagas: la nota ya corregida
                    rank_bursts(analyses)
        job_id = manager.create_job(paths, req.overwrite, analyzer,
                                    finalizer, harmonizer)
        return {"job_id": job_id, "local_only": client is None}

    @app.get("/api/jobs/{job_id}")
    def job_state(job_id: str):
        state = manager.get(job_id)
        if state is None:
            raise HTTPException(404, "Trabajo no encontrado")
        return state

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        if manager.get(job_id) is None:
            raise HTTPException(404, "Trabajo no encontrado")

        async def generate():
            async for event in manager.events(job_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/api/style/learn")
    def style_learn(req: LearnRequest):
        """Aprende el estilo desde los XMP editados a mano en una carpeta."""
        base = Path(req.dir).expanduser()
        if not base.is_dir():
            raise HTTPException(404, "Carpeta no encontrada")
        client = make_client()
        if client is None:
            raise HTTPException(503, "Se necesita la clave de API para aprender el estilo")
        stats = collect_stats(base)
        if stats["count"] < SETTINGS.learn_min_xmp:
            raise HTTPException(
                400,
                f"Se necesitan al menos {SETTINGS.learn_min_xmp} XMP editados por ti "
                f"(en Lightroom: Metadatos → Guardar metadatos en archivos); "
                f"se encontraron {stats['count']}")
        try:
            summary = summarize_style(client, stats)
        except AIUnavailable as exc:
            raise HTTPException(502, f"La IA no pudo resumir el estilo: {exc}")
        apply_learned_style(summary)
        return {"count": stats["count"], "summary": summary}

    @app.get("/api/presets")
    def presets_list():
        return {"presets": list_presets()}

    @app.post("/api/presets")
    def presets_save(req: PresetRequest):
        name = req.name.strip()
        if not name:
            raise HTTPException(400, "El preset necesita un nombre")
        return save_preset(name, req.prompt,
                           min(max(req.exposure_bias, -1.0), 1.0),
                           min(max(req.temp_bias, -800), 800))

    @app.delete("/api/presets")
    def presets_delete(name: str):
        return {"deleted": delete_preset(name)}

    @app.delete("/api/xmp")
    def remove_xmp(path: str):
        return {"deleted": delete_sidecar(Path(path))}

    @app.post("/api/xmp/delete")
    def remove_xmps(req: XmpDeleteRequest):
        """Borra los sidecars XMP en lote (los RAW nunca se tocan)."""
        return {"deleted": sum(1 for f in req.files if delete_sidecar(Path(f)))}

    return app


app = create_app()
