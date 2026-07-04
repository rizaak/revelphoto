import hashlib
import json
import os
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from revelado.config import SETTINGS
from revelado.exif import extract_preview_jpeg, read_exif
from revelado.imageio import decode_upright, encode_jpeg
from revelado.jobs import JobManager
from revelado.pipeline import process_photo
from revelado.xmp import delete_sidecar, sidecar_path

_STATIC = Path(__file__).parent / "static"


def _default_client_factory():
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


class ProcessRequest(BaseModel):
    files: list[str]
    overwrite: bool = False


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
                count = sum(1 for f in child.iterdir()
                            if f.suffix.lower() in SETTINGS.raw_extensions) \
                        if os.access(child, os.R_OK) else 0
                dirs.append({"name": child.name, "path": str(child),
                             "raw_count": count})
        return {"path": str(base), "parent": str(base.parent), "dirs": dirs}

    @app.get("/api/photos")
    def photos(dir: str):
        base = Path(dir).expanduser()
        if not base.is_dir():
            raise HTTPException(404, "Carpeta no encontrada")
        items = sorted(f for f in base.iterdir()
                       if f.suffix.lower() in SETTINGS.raw_extensions)
        return {"photos": [{"name": f.name, "path": str(f),
                            "has_xmp": sidecar_path(f).exists()} for f in items]}

    @app.get("/api/thumb")
    def thumb(path: str):
        raw = Path(path)
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
        return Response(cached.read_bytes(), media_type="image/jpeg")

    @app.post("/api/process")
    async def process(req: ProcessRequest):
        paths = [Path(f) for f in req.files]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise HTTPException(400, f"Archivos inexistentes: {missing[0]}")
        client = make_client()
        processor = lambda p, ow: process_photo(p, ow, client)
        job_id = manager.create_job(paths, req.overwrite, processor)
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

    @app.delete("/api/xmp")
    def remove_xmp(path: str):
        return {"deleted": delete_sidecar(Path(path))}

    return app


app = create_app()
