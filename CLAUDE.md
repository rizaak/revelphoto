# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

**Revelado**: app local (FastAPI en `localhost:8420`, frontend vanilla JS con SSE)
que analiza RAW de Canon (`.CR2`/`.CR3`) con Claude (`claude-haiku-4-5`, visión +
salida estructurada JSON) y escribe **sidecars XMP** que Lightroom Classic lee de
forma nativa: revelado, recorte/enderezado, máscaras por rostro, armonía de sesión
y culling con estrellas (`xmp:Rating`).

## El usuario

Isaac es **fotógrafo de retratos, no programador, habla español**. Toda la
comunicación con él va en español, paso a paso y sin jerga. Sus reportes de
producto son precisos ("el enderezado no actúa", "esta foto movida puntuó 4") —
tómalos como bugs reales y **reprodúcelos con fotos reales antes de tocar código**.

## Comandos

```bash
bash scripts/setup.sh                     # entorno + modelo YuNet + dependencias (exiftool vía Homebrew)
./.venv/bin/python -m pytest -q           # suite completa
./.venv/bin/python -m pytest tests/test_cull.py -q          # un archivo
./.venv/bin/python -m pytest tests/test_ai.py -k rating -q  # un test
# servidor (siempre relanzar tras tocar código; sirve el proceso viejo si no):
pkill -f "uvicorn revelado.server:app"; nohup ./.venv/bin/python -m uvicorn \
  revelado.server:app --host 127.0.0.1 --port 8420 > ~/.cache/revelado/server.log 2>&1 &
```

La clave API vive en `.env` (`ANTHROPIC_API_KEY=...`), cargada por `config.py`.
Python 3.10 (el Mac de Isaac no tiene 3.11).

## Arquitectura (el flujo que hay que entender)

```
server.py /api/process
  └─ jobs.py (JobManager, eventos SSE con replay)
       ├─ fase análisis (concurrente): pipeline.analyze_photo
       │    exif.py (exiftool) → imageio.decode_upright → metrics/faces/horizon
       │    → ai.decide (llamada de revelado) → ai.assess_faces (llamada de
       │      culling con recortes de cara en alta resolución) → cap_rating_for_faces
       ├─ fase lote (composición en server.py): harmonize + cull.flag_blurry
       │    + cull.rank_bursts — todas MUTAN analysis.ai
       └─ fase final por foto: develop.compute_settings → xmp.write_sidecar
```

- `config.py`: `Settings` frozen con todos los umbrales afinables. En tests se
  parchea con `dataclasses.replace(SETTINGS, ...)` + `patch("revelado.<mod>.SETTINGS", fake)`.
- `estilo.txt` (preferencias permanentes; `learn.py` escribe un bloque marcado),
  `presets.json` (gitignored) — ambos viajan con la carpeta.
- Modo sin API = solo-local: ajustes técnicos, nunca color, sin estrellas.

## Reglas duras del producto

- **Nunca** escribir en el catálogo `.lrcat` ni modificar los RAW. Solo XMP.
- **Nunca** sobrescribir un XMP sin `overwrite` explícito.
- El color solo lo decide la IA, como **desviación relativa** al WB de cámara
  (Kelvin absoluto desde JPEG creaba dominantes — validado con fotos reales).
- **El repo es PÚBLICO. Jamás commitear fotos de clientes**: `sample/` y
  `samples/` están gitignoradas y deben seguir así.

## Límites del modelo, verificados con fotos reales (no re-descubrir)

- Haiku **no percibe inclinación** (devuelve 0 con la foto girada 6°): el ángulo
  sale del estimador local (`horizon.py`, líneas horizontales Y verticales) y el
  prompt le pide a la IA *confirmarlo*, no estimarlo.
- Haiku **ignora tareas secundarias dentro de la llamada grande**: el culling de
  caras necesita su llamada dedicada (`assess_faces`) con recortes ampliados
  desde `cull_long_edge=3600px`; a 1500px el veredicto es inestable.
- En **perfiles** marca "ojos_cerrados" a ojos abiertos (a cualquier resolución):
  ese veredicto solo cuenta en caras frontales (`Face.frontal`, separación de
  ojos ≥ 0.28 del ancho, landmarks YuNet).
- La **varianza del laplaciano no tiene escala absoluta**: el grano ISO la infla
  y el barrido real NO la colapsa. Solo sirve comparada con la mediana de la
  sesión (`flag_blurry`, `blur_ratio`).
- La API devuelve JSON inválido esporádicamente → `analyze_photo` reintenta 1 vez.
- Límite abierto: barrido global sin cara defectuosa detectable no se caza
  (necesita ejemplos de Isaac para calibrar un detector direccional).

## Cómo trabajar aquí

- **TDD**: test que falla → implementación → suite completa en verde → commit por
  feature/fix, mensajes en español explicando el porqué.
- Verificar de punta a punta con la API real sobre `samples/` (céntimos por
  llamada); ante bugs de percepción, correr 3 veces para comprobar estabilidad.
- Al tocar estáticos, subir `?v=N` en `index.html` (el navegador cachea `app.js`).
- `TestClient` de FastAPI necesita context manager para SSE.
- OpenCV: `HoughLinesP` necesita `reshape(-1, 4)` (difiere entre 4.x y 5.x).
- Lightroom no reimporta fotos ya catalogadas (quitar del catálogo primero); tras
  reprocesar: *Metadatos → Leer metadatos desde archivos*.
- Specs de diseño en `docs/superpowers/specs/`; decidir alcance con Isaac antes
  de construir (lo imposible vía XMP — borrar objetos, píxeles — se dice claro).

## Estado

v1.0 etiquetada; v2 (culling/estrellas, aprender estilo, presets) y v3 (ruido por
ISO, recorte de intrusos, sombras decididas) en `main`, pendientes de etiqueta
hasta que Isaac las valide con una sesión real. Fuera de alcance salvo que él lo
pida: más formatos RAW (NEF/ARW/DNG) y modo catálogo experimental.
