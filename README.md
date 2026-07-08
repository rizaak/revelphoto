# Revelado — asistente de revelado automático para Lightroom Classic

Aplicación local (tu Mac, tus fotos: nada sale de tu equipo salvo una vista
previa reducida por foto hacia la API de Claude) que hace la primera pasada de
edición de tus RAW de Canon (`.CR2`/`.CR3`) y escribe los resultados como
archivos **XMP** que Lightroom Classic lee de forma nativa. Tú haces el repaso
fino en Lightroom, partiendo del 90% hecho.

## Qué hace

- **Análisis con IA por foto** (modelo Claude Haiku): exposición, contraste,
  altas luces/sombras (con rescate decidido del sujeto cuando la escena lo
  pide), encuadre y enderezado (solo con referencia clara), y color como
  desviación relativa respecto al balance de blancos de tu cámara. El recorte
  también deja fuera elementos que se cuelan por los bordes (un brazo ajeno,
  un cono, un cartel) sin sacrificar al sujeto.
- **Reducción de ruido según el ISO** de cada foto (luminancia y color), con
  los mismos deslizadores del panel *Detalle* de Lightroom. Funciona incluso
  sin IA. Borrar objetos DENTRO de la escena sí requiere píxeles: hazlo en
  Lightroom con la herramienta *Eliminar* (Revelado nunca modifica tus RAW).
- **Máscaras radiales por rostro decididas por la IA** (contraluz, lado en
  sombra, cara quemada) — editables en el panel de mascarado de Lightroom.
  Red de seguridad: una cara muy oscura siempre se rescata.
- **Armonía de sesión**: agrupa por escena (hora de captura + WB de cámara),
  unifica el look del grupo y ajusta la exposición foto a foto para igualar
  el brillo aunque el diafragma/obturador variara.
- **Sesgos de sesión**: deslizadores "más claras/oscuras" (±1 EV) y "más
  frías/cálidas" (±800 K) aplicados a todo el lote.
- **Indicaciones a la IA por sesión** con briefs de editor listos para usar
  (luminoso y aireado, cálido, mate, editorial…), más tu estilo permanente
  en `estilo.txt`.
- **Culling con estrellas (1–5)**: la IA puntúa cada foto (ojos cerrados,
  sujeto desenfocado, expresión, momento) y entre las tomas de una ráfaga
  destaca solo la mejor. En Lightroom aparecen como estrellas normales.
- **Aprende tu estilo**: lee los XMP de sesiones que TÚ editaste a mano y
  convierte tus tendencias en preferencias guardadas en `estilo.txt`.
- **Presets de briefs**: guarda con nombre tus combinaciones favoritas de
  indicaciones + deslizadores («Bodas exterior», «Estudio», …).
- **Revisión antes/después** simulada en el servidor, con descarte y
  reprocesado por foto, y borrado de XMP en lote.
- **Lee tu catálogo de Lightroom (solo lectura)** para elegir carpetas y
  colecciones directamente.
- Sin API o sin conexión funciona en **modo solo-local** (ajustes técnicos).

## Reglas de seguridad

- **Nunca** modifica tus RAW ni el catálogo de Lightroom.
- **Nunca** sobrescribe un XMP existente sin que marques la casilla.
- Borrar el `.xmp` (desde la app o el Finder) deshace todo.

## Instalación (también en otro Mac)

1. Copia la carpeta completa del proyecto al equipo (AirDrop, USB…).
2. Doble clic en **`Instalar Revelado.command`**. La primera vez macOS puede
   bloquearlo: clic derecho → *Abrir*. El instalador prepara todo y te pide
   la clave de API (opcional).
   - Requisitos: Python 3.10+ y Homebrew (para `exiftool`).
3. Al terminar tendrás **`Revelado.app`**: ábrela con doble clic (arrástrala
   al Dock si quieres). La página aparece sola en `http://localhost:8420`.

La clave de API vive en el archivo `.env` (`ANTHROPIC_API_KEY=...`). El costo
es de centavos por sesión de cientos de fotos.

## Flujo recomendado con Lightroom

- **Sesión nueva (sin pasos extra):** procesa la carpeta con la app y después
  impórtala en Lightroom — las fotos entran ya editadas.
- **Fotos ya importadas:** procesa y luego en Lightroom selecciona todo →
  *Metadatos → Leer metadatos desde archivos*. (Así además funciona el
  antes/después nativo con la tecla `\`.)

## Estrellas y selección (culling)

Con la casilla **«Puntuar con estrellas (1–5)»** marcada (lo está por
defecto), cada foto procesada llega a Lightroom ya puntuada:

- 5 excepcional · 4 buena · 3 correcta · 2 con un problema claro (ojos
  cerrados, desenfocada, mala expresión) · 1 fallida.
- En una ráfaga (tomas a menos de 2 segundos), solo la mejor conserva su
  puntuación; las repetidas bajan un escalón.
- En Lightroom, filtra por «3 estrellas o más» y repasa solo lo bueno. Las
  estrellas se cambian ahí mismo como siempre (teclas 1–5); el motivo de las
  puntuaciones bajas se ve en la pantalla de progreso y en la revisión.

## Aprender tu estilo

1. En Lightroom, abre una (o varias) sesiones que ya editaste a tu gusto,
   selecciona las fotos y usa *Metadatos → Guardar metadatos en archivos*
   (crea los XMP con tus ajustes junto a los RAW).
2. En Revelado, entra a esa carpeta y pulsa **«🎓 Aprender mi estilo»**.
3. La IA resume tus tendencias (necesita al menos 5 fotos editadas) y las
   guarda en un bloque marcado de `estilo.txt`, que puedes editar o borrar.
   Los XMP generados por Revelado se ignoran: solo aprende de TUS ediciones.
   Repetirlo reemplaza lo aprendido anterior, sin tocar lo que escribiste a mano.

## Presets de briefs

En el panel de sesión, ajusta los deslizadores y el texto de indicaciones y
pulsa **«💾 Guardar preset»** para bautizarlo (por ejemplo «Bodas exterior»).
Después basta elegirlo en el desplegable; 🗑 borra el seleccionado. Se
guardan en `presets.json`, que viaja con la carpeta si la copias a otro Mac.

## Personalización

- `estilo.txt`: tus preferencias permanentes, en tus palabras — la IA las lee
  en cada foto.
- Campo de indicaciones por sesión + chips con briefs completos.
- Valores finos (umbrales, topes, agrupación de escenas) en
  `revelado/config.py`.

## Desarrollo

```bash
bash scripts/setup.sh            # entorno + modelo de caras + dependencias
./.venv/bin/python -m pytest -q  # suite de tests
./.venv/bin/python run.py        # arrancar a mano
```

Especificación y plan: `docs/superpowers/`.
