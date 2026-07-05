"""Lectura (SOLO lectura) del catálogo de Lightroom Classic.

Nunca se escribe en el .lrcat: solo se consulta para listar carpetas y
colecciones y resolver las rutas de los RAW. Si Lightroom tiene bloqueado
el catálogo, se trabaja sobre una copia temporal.
"""
import shutil
import sqlite3
from pathlib import Path

from revelado.config import SETTINGS

_REGULAR_COLLECTION = "com.adobe.ag.library.collection"


class CatalogLocked(Exception):
    """El catálogo está bloqueado por Lightroom y no se pudo leer."""


def find_catalogs(base: Path = Path.home() / "Pictures") -> list[Path]:
    found: list[Path] = []
    for pattern in ("*.lrcat", "*/*.lrcat", "*/*/*.lrcat"):
        try:
            found.extend(p for p in base.glob(pattern) if p.is_file())
        except OSError:
            pass
    return sorted(set(found))


def _connect(cat: Path) -> sqlite3.Connection:
    try:
        con = sqlite3.connect(f"file:{cat}?mode=ro", uri=True, timeout=1)
        con.execute("SELECT 1 FROM AgLibraryRootFolder LIMIT 1")
        return con
    except sqlite3.OperationalError:
        # Bloqueado por Lightroom: usar una copia de solo lectura en caché
        cache = SETTINGS.cache_dir / "lrcat"
        cache.mkdir(parents=True, exist_ok=True)
        copy = cache / f"{cat.stem}-{int(cat.stat().st_mtime)}.lrcat"
        if not copy.exists():
            shutil.copy2(cat, copy)
        try:
            return sqlite3.connect(f"file:{copy}?mode=ro", uri=True, timeout=1)
        except sqlite3.OperationalError as exc:
            raise CatalogLocked(str(cat)) from exc


def _exts_sql() -> str:
    return ",".join(f"'{e.lstrip('.')}'" for e in SETTINGS.raw_extensions)


def sources(cat: Path) -> dict:
    """Carpetas y colecciones (normales) del catálogo con nº de RAW."""
    con = _connect(cat)
    try:
        folders = []
        for fid, abs_path, from_root, count in con.execute(f"""
                SELECT f.id_local, r.absolutePath, f.pathFromRoot, COUNT(fi.id_local)
                FROM AgLibraryFolder f
                JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
                LEFT JOIN AgLibraryFile fi ON fi.folder = f.id_local
                     AND lower(fi.extension) IN ({_exts_sql()})
                GROUP BY f.id_local
                ORDER BY r.absolutePath, f.pathFromRoot"""):
            if not count:
                continue
            full = abs_path + (from_root or "")
            name = (from_root or "").rstrip("/") or Path(abs_path.rstrip("/")).name
            folders.append({"id": fid, "name": name, "path": full, "count": count})

        collections = [
            {"id": cid, "name": name, "count": count}
            for cid, name, count in con.execute(f"""
                SELECT c.id_local, c.name, COUNT(fi.id_local)
                FROM AgLibraryCollection c
                LEFT JOIN AgLibraryCollectionImage ci ON ci.collection = c.id_local
                LEFT JOIN Adobe_images i ON ci.image = i.id_local
                LEFT JOIN AgLibraryFile fi ON i.rootFile = fi.id_local
                     AND lower(fi.extension) IN ({_exts_sql()})
                WHERE c.creationId = '{_REGULAR_COLLECTION}'
                GROUP BY c.id_local ORDER BY c.name""")
            if count]
        return {"folders": folders, "collections": collections}
    finally:
        con.close()


def photos(cat: Path, source_type: str, source_id: int) -> list[Path]:
    """Rutas absolutas de los RAW de una carpeta o colección del catálogo."""
    con = _connect(cat)
    try:
        if source_type == "folder":
            rows = con.execute(f"""
                SELECT r.absolutePath, f.pathFromRoot, fi.idx_filename
                FROM AgLibraryFile fi
                JOIN AgLibraryFolder f ON fi.folder = f.id_local
                JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
                WHERE f.id_local = ?
                  AND lower(fi.extension) IN ({_exts_sql()})
                ORDER BY fi.idx_filename""", (source_id,))
        else:
            rows = con.execute(f"""
                SELECT r.absolutePath, f.pathFromRoot, fi.idx_filename
                FROM AgLibraryCollectionImage ci
                JOIN Adobe_images i ON ci.image = i.id_local
                JOIN AgLibraryFile fi ON i.rootFile = fi.id_local
                JOIN AgLibraryFolder f ON fi.folder = f.id_local
                JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
                WHERE ci.collection = ?
                  AND lower(fi.extension) IN ({_exts_sql()})
                ORDER BY fi.idx_filename""", (source_id,))
        return [Path(a + (p or "") + n) for a, p, n in rows]
    finally:
        con.close()
