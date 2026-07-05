import asyncio
import uuid
from pathlib import Path
from typing import Callable

from revelado.config import SETTINGS
from revelado.notify import notify_macos
from revelado.pipeline import PhotoAnalysis, PhotoResult


class JobManager:
    def __init__(self, on_finish: Callable[[str, str], None] = notify_macos):
        self._jobs: dict[str, dict] = {}
        self._on_finish = on_finish

    def create_job(self, paths: list[Path], overwrite: bool,
                   analyzer: Callable[[Path, bool], PhotoAnalysis],
                   finalizer: Callable[[PhotoAnalysis, bool], PhotoResult],
                   harmonizer: Callable[[list[PhotoAnalysis]], None] | None = None) -> str:
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id, "total": len(paths), "completed": 0,
            "running": True, "results": [], "events": [],
            "condition": asyncio.Condition(),
        }
        self._jobs[job_id] = job
        # Requiere un event loop en ejecución: create_job debe llamarse desde
        # código async (la ruta /api/process es `async def` por esto).
        asyncio.create_task(self._run(job, paths, overwrite, analyzer,
                                      finalizer, harmonizer))
        return job_id

    def get(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return {
            "id": job["id"], "total": job["total"], "completed": job["completed"],
            "running": job["running"], "results": list(job["results"]),
        }

    async def _emit(self, job: dict, event: dict) -> None:
        async with job["condition"]:
            job["events"].append(event)
            job["condition"].notify_all()

    async def _run(self, job, paths, overwrite, analyzer, finalizer,
                   harmonizer) -> None:
        sem = asyncio.Semaphore(SETTINGS.worker_concurrency)
        analyses: dict[Path, PhotoAnalysis] = {}
        analyzed = 0

        # Fase 1: análisis concurrente (la parte lenta: preview + IA)
        async def analyze_one(path: Path):
            nonlocal analyzed
            async with sem:
                try:
                    analysis = await asyncio.to_thread(analyzer, path, overwrite)
                except Exception as exc:
                    analysis = PhotoAnalysis(path, error=f"{type(exc).__name__}: {exc}")
            analyses[path] = analysis
            analyzed += 1
            await self._emit(job, {"type": "progress", "completed": analyzed,
                                   "total": job["total"]})

        await asyncio.gather(*(analyze_one(p) for p in paths))

        # Fase 2: armonía de sesión (unifica el look por escena)
        ordered = [analyses[p] for p in paths]
        if harmonizer is not None:
            try:
                await asyncio.to_thread(harmonizer, ordered)
            except Exception:
                pass  # sin armonía es mejor que sin lote

        # Fase 3: escribir los XMP y emitir los resultados
        for analysis in ordered:
            try:
                result = await asyncio.to_thread(finalizer, analysis, overwrite)
            except Exception as exc:
                result = PhotoResult(str(analysis.path), "error",
                                     f"{type(exc).__name__}: {exc}")
            try:
                entry = {"path": result.path, "status": result.status,
                         "message": result.message}
                if result.settings is not None:
                    s = result.settings
                    entry["adjust"] = {
                        "exposure": s.exposure, "angle": s.crop_angle,
                        "crop": [s.crop_left, s.crop_top, s.crop_right, s.crop_bottom]
                                if s.has_crop else None,
                        "masks": len(s.masks),
                        "temp_shift": s.temp_shift, "tint": s.tint,
                        "contrast": s.contrast, "highlights": s.highlights,
                        "shadows": s.shadows,
                    }
            except Exception as exc:
                # Nunca dejar el lote sin evento: convertir en error
                entry = {"path": str(analysis.path), "status": "error",
                         "message": f"{type(exc).__name__}: {exc}"}
            job["results"].append(entry)
            job["completed"] += 1
            await self._emit(job, {"type": "photo", **entry,
                                   "completed": job["completed"],
                                   "total": job["total"]})

        ok = sum(1 for r in job["results"] if r["status"].startswith("done"))
        errors = sum(1 for r in job["results"] if r["status"] == "error")
        skipped = sum(1 for r in job["results"] if r["status"] == "skipped_existing")
        job["running"] = False
        await self._emit(job, {"type": "finished", "total": job["total"],
                               "ok": ok, "errors": errors, "skipped": skipped})
        self._on_finish("Revelado terminado",
                        f"{ok} de {job['total']} fotos procesadas"
                        + (f", {skipped} saltadas" if skipped else "")
                        + (f", {errors} con error" if errors else ""))

    async def events(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is None:
            return
        index = 0
        while True:
            async with job["condition"]:
                while index >= len(job["events"]):
                    await job["condition"].wait()
                event = job["events"][index]
            index += 1
            yield event
            if event["type"] == "finished":
                return
