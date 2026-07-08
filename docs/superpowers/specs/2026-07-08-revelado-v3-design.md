# Revelado v3 — la IA completa la edición (diseño)

Fecha: 2026-07-08 · Estado: aprobado por Isaac

## Petición

Que la IA haga toda la edición: recorte, armonizado, colores, temperatura,
eliminación de sombras, recorte de elementos ajenos a la escena, reducción de
ruido y eliminación de objetos.

## Alcance acordado

Ya existe (v1/v2): recorte+enderezado, armonía de sesión, color/WB relativo,
sombras con deslizador y máscaras por rostro, y reducción de ruido de
luminancia por ISO (`noise_reduction_for`).

Se construye en v3:

1. **Ruido de color + tabla afinada** — `color_noise_for(iso)` nuevo en
   `analysis/metrics.py`; se escribe `crs:ColorNoiseReduction` en el XMP.
   Determinista por ISO (el ruido no se aprecia en la vista previa reducida;
   el ISO es la señal fiable). Funciona también en modo solo-local.
2. **Recorte que excluye elementos ajenos** — ampliación del prompt del
   sistema: si por un borde se cuela algo ajeno a la escena (brazo, cono,
   cartel, transeúnte, basura), recortar para dejarlo fuera, sin cortar
   nunca al sujeto. Sigue vigente el tope del 50% por lado en `clamp_decision`.
3. **Sombras más decididas** — ampliación del prompt: rescatar sombras del
   sujeto y su entorno con más decisión cuando la escena lo pida,
   manteniendo la red de seguridad de rostros existente.

**Fuera de alcance** (imposible vía XMP, es edición de píxeles): borrar
objetos dentro de la escena y borrar sombras proyectadas. Se hace en
Lightroom con la herramienta *Eliminar*. Revelado nunca modifica los RAW.

## Cambios por archivo

- `revelado/analysis/metrics.py`: `color_noise_for(iso)` (≤1600→25 —el
  valor por defecto de Lightroom—, ≤6400→35, más→50).
- `revelado/develop.py`: `DevelopSettings.color_noise: int = 25`, asignado
  en ambas ramas de `compute_settings`.
- `revelado/xmp.py`: atributo `crs:ColorNoiseReduction`.
- `revelado/ai.py`: dos ampliaciones de `_SYSTEM` (encuadre y luz). Sin
  campos nuevos en el esquema de decisión.
- Sin cambios de UI ni de API HTTP.

## Pruebas

- Tabla `color_noise_for` (ISO bajo/alto/extremo).
- XMP contiene `crs:ColorNoiseReduction` con el valor de settings.
- `compute_settings` propaga `color_noise` en modo IA y solo-local.
- El prompt del sistema menciona elementos ajenos en bordes y sombras decididas.
