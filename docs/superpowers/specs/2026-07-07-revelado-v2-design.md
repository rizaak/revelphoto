# Revelado v2 — culling con estrellas, aprendizaje de estilo y presets de briefs

Fecha: 2026-07-07. Alcance acordado con Isaac al cierre de la v1: puntos 1, 2 y 3
del roadmap («culling y estrellas», «aprender tu estilo de verdad», «presets de
briefs»). Los puntos 4 (más formatos RAW) y 5 (modo catálogo) quedan fuera.

## 1. Culling y estrellas

**Objetivo:** que en Lightroom se pueda filtrar de inmediato lo mejor de la
sesión (ojos cerrados, desenfocadas y repeticiones de ráfaga quedan abajo).

- La IA devuelve dos campos nuevos en su decisión por foto:
  - `rating` (entero 1–5): 5 excepcional, 4 buena, 3 correcta, 2 con un
    problema claro (ojos cerrados, sujeto desenfocado, expresión desafortunada),
    1 fallida. En caso de duda, 3.
  - `rating_reason` (texto corto en español, vacío si no hay nada que señalar).
- Dato local nuevo para la IA: nitidez por cara (varianza del laplaciano del
  60% central del recuadro, igual que la luminancia). Campo `sharpness` en
  `Face`; la IA lo recibe junto a `luma` para detectar sujeto desenfocado
  aunque el fondo esté nítido.
- **Ráfagas** (`revelado/cull.py`, `rank_bursts(analyses)`): fotos consecutivas
  con `timestamp` a ≤ `burst_gap` (2 s) forman una ráfaga. En ráfagas de 2+,
  la mejor (mayor `rating`; desempate por nitidez de caras y global) conserva
  su puntuación y las demás bajan a `min(propio, mejor − 1)` con suelo 1.
  Solo ajusta la decisión de la IA (mismo patrón mutador que `harmonize`).
- **XMP:** atributo `xmp:Rating="N"` (namespace `xmp`, el estándar que
  Lightroom lee como estrellas). Solo se escribe si hubo IA y el usuario no
  desactivó la casilla. Modo solo-local: sin estrellas.
- **API/UI:** `ProcessRequest.rate: bool = True`; casilla «Puntuar con
  estrellas (1–5)» en la galería; las estrellas y el motivo se muestran en el
  registro de progreso y en las tarjetas de revisión.
- Config nueva: `burst_gap = 2` (segundos).

## 2. Aprendizaje de estilo desde sus ediciones

**Objetivo:** destilar el estilo real de Isaac a partir de sesiones que él ya
editó a mano, en vez de que lo escriba de memoria.

- `revelado/learn.py`:
  - `read_xmp_settings(path)`: parsea los ajustes `crs:` de un XMP (forma
    atributo y forma elemento). **Ignora los XMP generados por Revelado**
    (`x:xmptk="revelado"`): se aprende de SUS ediciones, no de las nuestras.
  - `collect_stats(folder)`: recorre `**/*.xmp`, junta Exposure2012, Contrast,
    Highlights, Shadows, Whites, Blacks, Clarity, Texture, Vibrance,
    Saturation, Temperature, Tint y WhiteBalance; devuelve mediana y cuartiles
    por ajuste + recuento de WB As Shot/Custom.
  - `summarize_style(client, stats)`: la IA convierte las estadísticas en 3–6
    frases de preferencias en español (texto plano, mismas reglas de tono que
    estilo.txt).
  - `apply_learned_style(text)`: escribe/reemplaza en `estilo.txt` un bloque
    delimitado por marcadores, sin tocar lo escrito a mano:
    `# === Estilo aprendido de tus ediciones === … # === Fin del estilo aprendido ===`.
    Los marcadores son comentarios `#` (que `_style_text()` filtra) y el
    contenido aprendido son líneas normales que la IA sí lee.
- **API:** `POST /api/style/learn {dir}` → 404 si no existe la carpeta, 400 si
  hay menos de `learn_min_xmp` (5) XMP utilizables, 503 sin clave de API.
  Aplica el bloque a estilo.txt y devuelve `{count, summary}`.
- **UI:** botón «🎓 Aprender mi estilo» en la galería de carpetas (requiere
  Lightroom → *Metadatos → Guardar metadatos en archivos* previo, documentado
  en README). Muestra el resumen aprendido al terminar.
- Config nueva: `learn_min_xmp = 5`.

## 3. Presets de briefs

**Objetivo:** guardar combinaciones favoritas (texto del brief + deslizadores)
con nombre: «Bodas exterior», «Estudio», …

- `revelado/presets.py`: `list_presets()`, `save_preset(name, prompt,
  exposure_bias, temp_bias)` (reemplaza si el nombre ya existe),
  `delete_preset(name)`. Persistencia en `presets.json` en la raíz del
  proyecto (viaja con la carpeta al copiarla a otro Mac); JSON corrupto o
  ausente ⇒ lista vacía. Gitignored.
- **API:** `GET /api/presets`, `POST /api/presets` (nombre no vacío; sesgos
  con los mismos topes que /api/process), `DELETE /api/presets?name=…`.
- **UI:** en el panel de sesión, desplegable «Presets guardados…» que aplica
  brief + deslizadores, botón «💾 Guardar preset» (pide nombre) y «🗑» para
  borrar el seleccionado.
- Config nueva: `presets_path = raíz/presets.json`.

## Fuera de alcance

Borrar o mover fotos según la puntuación (las estrellas solo se escriben, el
descarte se hace filtrando en Lightroom); aprendizaje continuo automático;
sincronizar presets entre equipos.

## Pruebas

Cada módulo nuevo con su test (`test_cull`, `test_learn`, `test_presets`) más
ampliaciones de `test_ai` (rating en esquema y clamp), `test_develop`/`test_xmp`
(Rating presente/ausente), `test_faces` (sharpness), `test_server` (rutas
nuevas y `rate=False`), `test_jobs` (rating en el evento). La suite completa
debe seguir en verde.
