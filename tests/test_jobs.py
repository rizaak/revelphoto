import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revelado.jobs import JobManager
from revelado.pipeline import PhotoResult


def _proc(path: Path, overwrite: bool) -> PhotoResult:
    if "bad" in path.name:
        raise RuntimeError("explota")
    return PhotoResult(str(path), "done")


async def _collect(manager, job_id):
    events = []
    async for ev in manager.events(job_id):
        events.append(ev)
    return events


@pytest.mark.asyncio
async def test_job_processes_all_and_finishes():
    manager = JobManager(on_finish=MagicMock())
    paths = [Path(f"/x/IMG_{i}.CR3") for i in range(3)]
    job_id = manager.create_job(paths, overwrite=False, processor=_proc)
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    photo_events = [e for e in events if e["type"] == "photo"]
    assert len(photo_events) == 3
    assert events[-1]["type"] == "finished" and events[-1]["ok"] == 3
    state = manager.get(job_id)
    assert state["completed"] == 3 and not state["running"]


@pytest.mark.asyncio
async def test_processor_exception_becomes_error_event():
    manager = JobManager(on_finish=MagicMock())
    job_id = manager.create_job([Path("/x/bad.CR3"), Path("/x/ok.CR3")],
                                overwrite=False, processor=_proc)
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    statuses = sorted(e["status"] for e in events if e["type"] == "photo")
    assert statuses == ["done", "error"]
    assert events[-1]["errors"] == 1


@pytest.mark.asyncio
async def test_on_finish_called():
    on_finish = MagicMock()
    manager = JobManager(on_finish=on_finish)
    job_id = manager.create_job([Path("/x/a.CR3")], overwrite=False, processor=_proc)
    await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    on_finish.assert_called_once()


@pytest.mark.asyncio
async def test_late_subscriber_gets_replay():
    manager = JobManager(on_finish=MagicMock())
    job_id = manager.create_job([Path("/x/a.CR3")], overwrite=False, processor=_proc)
    await asyncio.sleep(0.3)  # dejar terminar
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    assert any(e["type"] == "photo" for e in events)
    assert events[-1]["type"] == "finished"


def test_notify_macos_swallows_errors():
    from revelado.notify import notify_macos
    with patch("revelado.notify.subprocess.run", side_effect=FileNotFoundError):
        notify_macos("t", "m")  # no lanza


@pytest.mark.asyncio
async def test_photo_event_includes_adjust():
    from revelado.develop import DevelopSettings, RadialMask
    settings = DevelopSettings(
        temperature=5300, tint=5, exposure=0.4, contrast=10, highlights=-20,
        shadows=25, whites=0, blacks=0, sharpness=45, luminance_smoothing=15,
        has_crop=True, crop_left=0.1, crop_top=0.05, crop_right=0.95,
        crop_bottom=0.9, crop_angle=-1.5,
        masks=[RadialMask(0.3, 0.2, 0.6, 0.5, 1.0, 25)], ai_used=True)

    def proc(path, overwrite):
        return PhotoResult(str(path), "done", settings=settings)

    manager = JobManager(on_finish=MagicMock())
    job_id = manager.create_job([Path("/x/a.CR3")], overwrite=False, processor=proc)
    events = await asyncio.wait_for(_collect(manager, job_id), timeout=5)
    photo = next(e for e in events if e["type"] == "photo")
    assert photo["adjust"] == {"exposure": 0.4, "angle": -1.5,
                               "crop": [0.1, 0.05, 0.95, 0.9], "masks": 1}
