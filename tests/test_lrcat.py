import sqlite3
from pathlib import Path

from revelado.lrcat import find_catalogs, photos, sources


def _fake_catalog(path: Path) -> Path:
    """Catálogo mínimo con el subconjunto de esquema que usa lrcat.py."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE AgLibraryRootFolder (id_local INTEGER PRIMARY KEY, absolutePath TEXT);
        CREATE TABLE AgLibraryFolder (id_local INTEGER PRIMARY KEY, rootFolder INTEGER,
                                      pathFromRoot TEXT);
        CREATE TABLE AgLibraryFile (id_local INTEGER PRIMARY KEY, folder INTEGER,
                                    idx_filename TEXT, extension TEXT);
        CREATE TABLE Adobe_images (id_local INTEGER PRIMARY KEY, rootFile INTEGER);
        CREATE TABLE AgLibraryCollection (id_local INTEGER PRIMARY KEY, name TEXT,
                                          creationId TEXT);
        CREATE TABLE AgLibraryCollectionImage (collection INTEGER, image INTEGER);

        INSERT INTO AgLibraryRootFolder VALUES (1, '/fotos/');
        INSERT INTO AgLibraryFolder VALUES (10, 1, 'boda/');
        INSERT INTO AgLibraryFolder VALUES (11, 1, 'vacia/');
        INSERT INTO AgLibraryFile VALUES (100, 10, 'IMG_1.CR3', 'CR3');
        INSERT INTO AgLibraryFile VALUES (101, 10, 'IMG_2.cr2', 'cr2');
        INSERT INTO AgLibraryFile VALUES (102, 10, 'video.mp4', 'mp4');
        INSERT INTO Adobe_images VALUES (200, 100);
        INSERT INTO Adobe_images VALUES (201, 101);
        INSERT INTO AgLibraryCollection VALUES (50, 'Seleccion', 'com.adobe.ag.library.collection');
        INSERT INTO AgLibraryCollection VALUES (51, 'Smart', 'com.adobe.ag.library.smart_collection');
        INSERT INTO AgLibraryCollectionImage VALUES (50, 200);
    """)
    con.commit()
    con.close()
    return path


def test_sources_lists_folders_and_regular_collections(tmp_path):
    cat = _fake_catalog(tmp_path / "test.lrcat")
    data = sources(cat)
    assert [f["name"] for f in data["folders"]] == ["boda"]
    assert data["folders"][0]["count"] == 2  # solo los RAW, no el mp4
    assert [c["name"] for c in data["collections"]] == ["Seleccion"]  # sin smart
    assert data["collections"][0]["count"] == 1


def test_photos_from_folder_and_collection(tmp_path):
    cat = _fake_catalog(tmp_path / "test.lrcat")
    folder_photos = photos(cat, "folder", 10)
    assert [p.name for p in folder_photos] == ["IMG_1.CR3", "IMG_2.cr2"]
    assert str(folder_photos[0]) == "/fotos/boda/IMG_1.CR3"
    col_photos = photos(cat, "collection", 50)
    assert [p.name for p in col_photos] == ["IMG_1.CR3"]


def test_find_catalogs(tmp_path):
    (tmp_path / "sub").mkdir()
    _fake_catalog(tmp_path / "sub" / "mi.lrcat")
    assert [c.name for c in find_catalogs(tmp_path)] == ["mi.lrcat"]
