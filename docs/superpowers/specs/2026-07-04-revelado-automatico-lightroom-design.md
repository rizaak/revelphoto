# Especificación: Asistente de revelado automático para Lightroom Classic

**Fecha:** 2026-07-04
**Estado:** Aprobado en diseño, pendiente de plan de implementación

## 1. Objetivo

Automatizar la primera pasada de edición de fotos RAW (Canon `.CR2`/`.CR3`) que hoy se hace foto a foto en Lightroom Classic: exposición y color, encuadre y enderezado, enfoque y reducción de ruido. El fotógrafo selecciona las fotos en una interfaz web local, la app las procesa con IA y escribe las ediciones como archivos XMP que Lightroom Classic lee al importar. El repaso final se hace en Lightroom como siempre, pero partiendo del trabajo ya hecho.

**Usuario:** fotógrafo de retratos/sesiones, 50–300 fotos por sesión, Mac.

**Fuera de alcance en v1 (fase 2):** puntuación con estrellas y culling (ojos cerrados, desenfocadas, duplicados), aprendizaje del estilo personal.

## 2. Reglas de producto (no negociables)

1. **Nunca se modifica el archivo RAW ni el catálogo de Lightroom.** Toda edición vive en un XMP sidecar (`IMG_1234.xmp` junto al RAW). Borrar el XMP deshace todo.
2. **Los rostros nunca quedan oscuros**, y su corrección **jamás** se hace a costa del resto de la imagen: la exposición global es conservadora y cada rostro por debajo del umbral de luminosidad recibe su propia **máscara radial local** con corrección medida individualmente. El fondo y las demás personas no se alteran.
3. **No se sobrescribe un XMP existente** sin confirmación explícita del usuario (podría contener ediciones manuales).
4. Si la API de Claude no está disponible, la app sigue funcionando en **modo solo-local** (ajustes técnicos sin decisión estética de encuadre) y lo indica claramente.

## 3. Arquitectura

App local en Python que corre en el Mac del usuario y sirve una interfaz web en `http://localhost:8420`.

```
┌─────────────┐   HTTP/SSE   ┌──────────────────────────────┐
│ Navegador   │◄────────────►│ FastAPI (localhost:8420)     │
│ (interfaz)  │              │  ├─ Explorador de carpetas   │
└─────────────┘              │  ├─ Cola de procesamiento    │
                             │  └─ Pipeline por foto        │
                             └──────┬───────────┬───────────┘
                                    │           │
                        análisis local      API Claude (visión)
                        (caras, histograma,  solo preview ~1500px
                         nitidez, horizonte) decisión estética
                                    │           │
                                    └─────┬─────┘
                                          ▼
                              XMP sidecar junto al RAW
                                          ▼
                              Lightroom Classic (importar /
                              "Leer metadatos desde archivos")
```

- **Privacidad:** los RAW nunca salen del Mac; a la API solo viaja una vista previa JPEG reducida (~1500 px lado largo) por foto.
- **Backend:** Python 3.11+, FastAPI + Uvicorn. Procesamiento en cola con workers concurrentes (análisis local en paralelo; llamadas a la API con límite de concurrencia).
- **Frontend:** HTML/CSS/JS sin framework, servido por FastAPI. Progreso por SSE (Server-Sent Events).
- **Dependencias externas:** `exiftool` (extracción de previews y metadatos EXIF), OpenCV (detección de caras con YuNet incluido en OpenCV, Hough para horizonte, métricas), SDK `anthropic`.

## 4. Pipeline por foto

1. **Extracción de preview:** se extrae el JPEG embebido en el CR2/CR3 con `exiftool` (sin decodificar el RAW completo → procesar 300 fotos toma minutos). Se lee también EXIF: ISO, lente, orientación, balance de blancos de cámara.
2. **Análisis local (gratis, en el Mac):**
   - Detección de caras (OpenCV YuNet): posición, tamaño y **luminosidad media de cada rostro**.
   - Histograma global: exposición general, recorte de altas luces/sombras.
   - Estimación de balance de blancos (gray-world + tono de piel si hay caras).
   - Nitidez (varianza del laplaciano) → cantidad de sharpening.
   - ISO → nivel de reducción de ruido de luminancia.
   - Detección de horizonte/verticales (transformada de Hough) → ángulo de enderezado candidato.
3. **Decisión estética (API de Claude, modelo `claude-haiku-4-5` con visión):** recibe la preview reducida + las métricas locales y devuelve JSON con: recorte propuesto (composición, sujeto bien situado), ángulo fino de enderezado, y validación/ajuste de los valores de exposición y color. Salida estructurada y acotada (la app aplica límites de seguridad a todos los valores).
4. **Cálculo de máscaras de rostro:** para cada cara con luminosidad media inferior al umbral (por defecto 35% — configurable), se genera una máscara radial (óvalo con degradado suave centrado en la cara, en coordenadas normalizadas de la imagen completa (espacio que usa Lightroom para máscaras; se valida empíricamente en la aceptación con el caso cara oscura + recorte)) con su subida de exposición/sombras individual, calculada para llevar el rostro a la zona objetivo (45–55%) con un tope de +1.5 EV local.
5. **Escritura del XMP** (namespace `crs` de Camera Raw, ProcessVersion actual):
   - Globales: `WhiteBalance` ("As Shot" salvo dominante de color clara, entonces Custom con Temperature/Tint), `Exposure2012`, `Contrast2012`, `Highlights2012`, `Shadows2012`, `Whites2012`, `Blacks2012`, `Sharpness`, `LuminanceSmoothing`.
   - Geometría: `CropLeft/Top/Right/Bottom`, `CropAngle`, `HasCrop`.
   - Locales: `CircularGradientBasedCorrections` (una por rostro corregido) con `LocalExposure2012`/`LocalShadows2012` — Lightroom Classic las muestra como máscaras editables en el panel de mascarado.
   - Si existe un XMP previo: se detiene y pide confirmación (regla 3).

## 5. Interfaz web

Tres pantallas:

1. **Selección de carpeta:** navegador del sistema de archivos (carpetas del Mac), recuerda las últimas usadas.
2. **Galería de selección:** miniaturas de los RAW de la carpeta (desde el preview embebido), selección individual / todas / rango. Indica cuáles ya tienen XMP. Botón **Procesar**.
3. **Progreso y revisión:**
   - Barra en vivo ("foto 47 de 220"), errores marcados en rojo sin detener el lote.
   - Al terminar: **notificación de macOS** (osascript) + notificación del navegador.
   - Galería antes/después (preview original vs. preview con ajustes simulados). Por cada foto: botón "descartar edición" (borra su XMP) y "reprocesar".

## 6. Flujo con Lightroom Classic

- **Fotos nuevas (flujo ideal):** procesar con la app **antes** de importar → al importar, LR lee los XMP automáticamente y las fotos aparecen editadas.
- **Fotos ya importadas:** seleccionar en LR → menú *Metadatos → Leer metadatos desde archivos*.
- Todas las ediciones aparecen como ajustes normales de revelado y máscaras normales: cualquier deslizador o máscara se puede afinar o quitar en el repaso.

## 7. Manejo de errores

| Situación | Comportamiento |
|---|---|
| RAW corrupto o preview no extraíble | Se marca en rojo, el lote continúa |
| API caída / sin conexión / sin crédito | Modo solo-local con aviso visible; ajustes técnicos sin encuadre estético |
| Valores fuera de rango devueltos por la IA | Se recortan a límites de seguridad predefinidos |
| XMP existente | No se toca; se pide confirmación (por foto o "aplicar a todas") |
| App cerrada a mitad de lote | Los XMP ya escritos quedan válidos; al reabrir se puede reanudar (las fotos con XMP aparecen como hechas) |

## 8. Pruebas

- **Unitarias:** generador de XMP (valores conocidos → XML esperado, redondeos, coordenadas de recorte y máscaras), límites de seguridad, detección de XMP existente.
- **Integración:** pipeline completo sobre un set de CR2/CR3 de muestra con caras en sombra, horizonte torcido y altas ISO; API simulada (mock) y real.
- **Aceptación manual:** importar los XMP generados en Lightroom Classic y verificar que recorte, ángulo, color y máscaras aparecen y son editables.

## 9. Requisitos y costos

- macOS con Python 3.11+ y `exiftool` (instalación automatizada con un script/comando único).
- Clave de API de Anthropic (`console.anthropic.com`), pago por uso, separada de la suscripción de Claude Code. Costo estimado con Haiku: **~$0.10–0.40 USD por sesión de 300 fotos**.

## 10. Fase 2 (tras validar v1)

- Puntuación 1–5 estrellas escrita en el XMP (`xmp:Rating`) y culling: ojos cerrados, desenfocadas, duplicados/ráfagas.
- Aprendizaje del estilo personal a partir de ediciones previas del usuario.
