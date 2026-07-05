# Revelado — asistente de revelado automático para Lightroom Classic

Aplicación local (tu Mac, tus fotos: nada sale de tu equipo salvo una vista
previa reducida por foto hacia la API de Claude) que hace la primera pasada de
edición de tus RAW de Canon (`.CR2`/`.CR3`) y escribe los resultados como
archivos **XMP** que Lightroom Classic lee de forma nativa. Tú haces el repaso
fino en Lightroom, partiendo del 90% hecho.

## Qué hace

- **Análisis con IA por foto** (modelo Claude Haiku): exposición, contraste,
  altas luces/sombras, encuadre y enderezado (solo con referencia clara), y
  color como desviación relativa respecto al balance de blancos de tu cámara.
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
