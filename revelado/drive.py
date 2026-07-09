"""Sincronización automática de Google Drive antes de procesar."""
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import set


def _ensure_synced(file_path: Path, timeout: int = 30) -> bool:
    """Ensure a file from Google Drive is locally available.

    Uses brctl (Google Drive's CLI) to download if needed.
    Returns True if file is accessible, False if timeout.
    """
    # Si el archivo ya existe, probablemente está sincronizado
    if file_path.exists():
        return True

    # Intentar usar brctl para forzar descarga
    try:
        result = subprocess.run(
            ["brctl", "download", str(file_path)],
            capture_output=True,
            timeout=5,
            text=True
        )
        if result.returncode != 0:
            return False
    except FileNotFoundError:
        # brctl no disponible; asumir que el archivo está sincronizado
        return True
    except subprocess.TimeoutExpired:
        return False

    # Esperar a que se sincronice (max `timeout` segundos)
    start = time.time()
    while time.time() - start < timeout:
        if file_path.exists():
            return True
        time.sleep(0.5)

    return False


def ensure_local(file_path: Path) -> None:
    """Ensure file is accessible locally, synchronizing from Drive if needed.

    Raises RuntimeError if file cannot be accessed after timeout.
    """
    if not _ensure_synced(file_path):
        raise RuntimeError(
            f"No se pudo acceder a {file_path.name} "
            "(probablemente está en Google Drive sin sincronizar). "
            "Abre el archivo en el Finder para sincronizarlo automáticamente."
        )


def list_drive_files(directory: Path) -> set[str]:
    """List files in a Google Drive folder (including not-yet-synced files).

    Uses brctl (Google Drive CLI) to discover files that may not exist locally.
    Returns set of filenames visible in Drive, even if not synced.
    """
    if not directory.exists():
        return set()

    try:
        result = subprocess.run(
            ["brctl", "ls", str(directory)],
            capture_output=True,
            timeout=5,
            text=True
        )
        if result.returncode == 0:
            # brctl ls outputs one filename per line
            return set(line.strip() for line in result.stdout.splitlines() if line.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return set()
