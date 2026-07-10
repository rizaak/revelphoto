const $ = (id) => document.getElementById(id);
const state = { dir: null, selected: new Set(), results: [] };

// Cargar versión
fetch("/api/version").then(r => r.json()).then(data => {
  $("version").textContent = `Revelado ${data.version}`;
}).catch(() => {
  $("version").textContent = "Revelado";
});

function show(section) {
  for (const id of ["browser", "gallery", "progress", "review"])
    $(id).hidden = id !== section;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

// --- Pantalla 1: carpetas ---
async function loadDirs(path = "") {
  $("loading").hidden = false;
  $("dirs").innerHTML = "";
  try {
    const data = await api(`/api/browse?path=${encodeURIComponent(path)}`);
    $("crumb").textContent = data.path;
    const ul = $("dirs");
    ul.innerHTML = "";
    const up = document.createElement("li");
  up.textContent = "⬆︎ Subir";
  up.onclick = () => loadDirs(data.parent || "");
  ul.appendChild(up);
  for (const d of data.dirs) {
    const li = document.createElement("li");
    li.className = "dir-item";
    const info = document.createElement("div");
    info.className = "dir-info";
    info.innerHTML = `<span>📁 ${d.name}</span>` +
      (d.raw_count ? `<span class="raw-count">${d.raw_count} RAW</span>` : "");
    info.onclick = () => loadDirs(d.path);
    li.appendChild(info);
    if (d.has_xmp) {
      const learnBtn = document.createElement("button");
      learnBtn.className = "learn-btn";
      learnBtn.textContent = "🎓 Aprender";
      learnBtn.title = "Aprender el estilo de esta carpeta";
      learnBtn.onclick = (e) => { e.stopPropagation(); learnStyle(d.path, learnBtn); };
      li.appendChild(learnBtn);
    }
    if (d.raw_count) {
      const btn = document.createElement("button");
      btn.className = "process-btn";
      btn.textContent = "Procesar";
      btn.onclick = (e) => { e.stopPropagation(); openGallery(d.path); };
      li.appendChild(btn);
    }
    ul.appendChild(li);
  }
  // Si no hay subcarpetas pero la carpeta actual tiene RAW o XMP, mostrar opciones
  if (!data.dirs.length && (data.current_raw_count || data.current_has_xmp)) {
    const li = document.createElement("li");
    li.className = "dir-item current-dir";
    const info = document.createElement("div");
    info.className = "dir-info";
    let infoHtml = `<span>📁 Esta carpeta</span>`;
    if (data.current_raw_count) infoHtml += `<span class="raw-count">${data.current_raw_count} RAW</span>`;
    info.innerHTML = infoHtml;
    li.appendChild(info);
    if (data.current_has_xmp) {
      const learnBtn = document.createElement("button");
      learnBtn.className = "learn-btn";
      learnBtn.textContent = "🎓 Aprender";
      learnBtn.title = "Aprender el estilo de esta carpeta";
      learnBtn.onclick = () => learnStyle(data.path, learnBtn);
      li.appendChild(learnBtn);
    }
    if (data.current_raw_count) {
      const btn = document.createElement("button");
      btn.className = "process-btn";
      btn.textContent = "Procesar";
      btn.onclick = () => openGallery(data.path);
      li.appendChild(btn);
    }
    ul.appendChild(li);
  }
    show("browser");
    $("subtitle").textContent = "Selecciona una carpeta o una fuente del catálogo de Lightroom";
  } finally {
    $("loading").hidden = true;
  }
}

// --- Catálogo de Lightroom (solo lectura) ---
async function loadLrcat() {
  const box = $("lrcat");
  box.innerHTML = "";
  try {
    const { catalogs } = await api("/api/lrcat/catalogs");
    if (!catalogs.length) return;
    const cat = catalogs[0];
    const { folders, collections } = await api(
      `/api/lrcat/sources?cat=${encodeURIComponent(cat.path)}`);
    if (!folders.length && !collections.length) return;

    const header = document.createElement("div");
    header.className = "lr-header";
    const title = document.createElement("div");
    title.className = "lr-title";
    title.textContent = `📔 Catálogo de Lightroom (${cat.name})`;
    const toggle = document.createElement("button");
    toggle.id = "lr-toggle";
    toggle.textContent = "☰";
    toggle.title = "Mostrar/ocultar catálogo";
    toggle.onclick = (e) => {
      e.stopPropagation();
      const isHidden = ul.style.display === "none";
      ul.style.display = isHidden ? "" : "none";
      search.style.display = isHidden ? "" : "none";
      toggle.textContent = isHidden ? "☰" : "▸";
    };
    header.appendChild(title);
    header.appendChild(toggle);
    box.appendChild(header);

    const ul = document.createElement("ul");
    ul.id = "lr-sources";

    const search = document.createElement("input");
    search.type = "text";
    search.id = "lr-search";
    search.placeholder = "Buscar carpeta/colección…";
    search.oninput = () => {
      const q = search.value.toLowerCase();
      for (const li of ul.querySelectorAll("li")) {
        const name = li.querySelector("span").textContent.toLowerCase();
        li.style.display = q && !name.includes(q) ? "none" : "flex";
      }
    };
    box.appendChild(search);
    for (const f of folders) {
      const li = document.createElement("li");
      li.innerHTML = `<span>📁 ${f.name}</span><span class="raw-count">${f.count} RAW</span>`;
      li.onclick = () => openLrGallery(cat.path, "folder", f.id, `LR · ${f.name}`);
      ul.appendChild(li);
    }
    for (const c of collections) {
      const li = document.createElement("li");
      li.innerHTML = `<span>🗂 ${c.name}</span><span class="raw-count">${c.count} RAW</span>`;
      li.onclick = () => openLrGallery(cat.path, "collection", c.id, `LR · ${c.name}`);
      ul.appendChild(li);
    }
    box.appendChild(ul);
  } catch (e) {
    box.innerHTML = `<div class="lr-title">📔 Lightroom: ${e.message}</div>`;
  }
}

async function openLrGallery(cat, type, id, subtitle) {
  const data = await api(`/api/lrcat/photos?cat=${encodeURIComponent(cat)}&type=${type}&id=${id}`);
  state.dir = null;  // galería de catálogo: sin carpeta única (p. ej. para aprender estilo)
  state.reloadGallery = () => openLrGallery(cat, type, id, subtitle);
  renderGallery(data.photos.filter((p) => !p.missing), subtitle);
}

function updateToolbar() {
  const n = state.selected.size;
  $("process").disabled = n === 0;
  $("process").textContent = n ? `Procesar ${n} foto(s)` : "Procesar seleccionadas";
  $("remove-xmp").disabled = n === 0;
}

// --- Pantalla 2: galería ---
function renderGallery(photos, subtitle) {
  state.selected.clear();
  const grid = $("grid");
  grid.innerHTML = "";
  for (const p of photos) {
    const div = document.createElement("div");
    div.className = "photo";
    div.dataset.path = p.path;
    div.innerHTML = `<img loading="lazy" src="/api/thumb?path=${encodeURIComponent(p.path)}">` +
      (p.has_xmp ? '<span class="badge">XMP</span>' : "") +
      `<div class="name">${p.name}</div>`;
    div.onclick = () => {
      div.classList.toggle("selected");
      div.classList.contains("selected") ? state.selected.add(p.path)
                                         : state.selected.delete(p.path);
      updateToolbar();
    };
    grid.appendChild(div);
  }
  $("subtitle").textContent = subtitle;
  $("learn-style").hidden = false;
  $("learn-style").disabled = !state.dir;
  $("learn-style").title = state.dir ? "Aprender el estilo de esta carpeta" : "Solo funciona con carpetas (no con catálogos de Lightroom)";
  updateToolbar();
  show("gallery");
}

async function openGallery(dir) {
  $("loading").hidden = false;
  try {
    state.dir = dir;
    const data = await api(`/api/photos?dir=${encodeURIComponent(dir)}`);
    state.reloadGallery = () => openGallery(dir);
    renderGallery(data.photos, dir);
  } finally {
    $("loading").hidden = true;
  }
}

$("remove-xmp").onclick = async () => {
  const n = state.selected.size;
  if (!n) return;
  if (!confirm(`¿Quitar el XMP de ${n} foto(s)? Sus ediciones se descartan (los RAW no se tocan).`)) return;
  const { deleted } = await api("/api/xmp/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files: [...state.selected] }),
  });
  alert(`${deleted} XMP eliminados.`);
  if (state.reloadGallery) state.reloadGallery();
};

async function learnStyle(dir, btn) {
  if (!confirm("Voy a leer los XMP de esta carpeta (ediciones hechas por TI en Lightroom) " +
               "para aprender tu estilo y guardarlo en estilo.txt. ¿Continuar?")) return;
  if (btn) btn.disabled = true;
  const origText = btn ? btn.textContent : "";
  if (btn) btn.textContent = "Aprendiendo…";
  try {
    const { count, summary } = await api("/api/style/learn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dir }),
    });
    alert(`Estilo aprendido de ${count} fotos y guardado en estilo.txt ` +
          `(puedes editarlo o borrarlo cuando quieras):\n\n${summary}`);
  } catch (e) {
    alert(`No se pudo aprender el estilo: ${e.message}`);
  }
  if (btn) {
    btn.disabled = false;
    btn.textContent = origText;
  }
}

$("learn-style").onclick = () => learnStyle(state.dir, $("learn-style"));

$("back").onclick = () => loadDirs(state.dir ? state.dir.split("/").slice(0, -1).join("/") : "");
$("select-all").onclick = () => {
  document.querySelectorAll(".photo").forEach((el) => {
    el.classList.add("selected");
    state.selected.add(el.dataset.path);
  });
  updateToolbar();
};

// --- Opciones de sesión: sesgos e indicaciones para la IA ---
const CHIP_SUGGESTIONS = [
  { label: "Luminosas y aireadas",
    text: "Look luminoso y aireado (bright & airy): sube ligeramente la exposición general, abre las sombras con suavidad y controla las altas luces sin quemar la piel. Contraste bajo, color limpio con un matiz cálido muy sutil. Evita negros profundos y saturaciones fuertes; la piel debe verse fresca y clara." },
  { label: "Cálidas y acogedoras",
    text: "Ambiente cálido y acogedor: desplaza el balance hacia cálido de forma notable pero creíble, sombras ligeramente levantadas y contraste medio. Favorece tonos tierra y dorados; la piel con un brillo dorado natural sin ponerse naranja. Conserva la sensación de la luz real de la escena." },
  { label: "Frías y limpias",
    text: "Estética fría y limpia: balance ligeramente hacia azul, blancos puros sin dominantes, contraste medio-alto con negros definidos y saturación contenida. La piel debe seguir viéndose sana y natural, nunca grisácea. Look moderno y minimalista." },
  { label: "Mate, contraste suave",
    text: "Acabado mate de contraste suave: levanta un poco las sombras (negros ligeramente lavados), baja levemente las altas luces y reduce el contraste general. Saturación moderada, sensación de película analógica suave — pero sin que la foto quede plana o sin vida." },
  { label: "Colores vivos",
    text: "Colores vivos y presentes: contraste medio-alto, saturación notoria pero sin caer en HDR ni posterizar, altas luces protegidas. Aunque la escena sea vibrante, la piel se mantiene natural y sin sobresaturar. Energía y frescura." },
  { label: "Piel protagonista",
    text: "La piel es la prioridad absoluta: decide la exposición para que los rostros queden luminosos y uniformes, con tonos de piel naturales sin dominantes (ni naranja ni magenta) y contraste suave en las caras. Todos los demás ajustes quedan al servicio del retrato." },
  { label: "Respeta la luz original",
    text: "Intervención mínima: respeta el carácter, la dirección y el ambiente de la luz original de la escena. Corrige solo defectos técnicos claros (exposición desviada, dominante evidente) sin imponer ningún look. Todos los cambios deben ser sutiles." },
  { label: "Editorial elegante",
    text: "Estilo editorial elegante, de revista: contraste refinado con negros ricos, altas luces sedosas, paleta contenida y sofisticada, ligera desaturación de los colores chillones. Resultado pulido, intencional y atemporal." },
];

function initSessionOpts() {
  const chips = $("chips");
  for (const { label, text } of CHIP_SUGGESTIONS) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = "+ " + label;
    b.title = text;  // el brief completo se ve al pasar el ratón
    b.onclick = () => {
      $("session-prompt").value = text;  // reemplaza lo anterior
    };
    chips.appendChild(b);
  }
  $("clear-prompt").onclick = () => { $("session-prompt").value = ""; };
  $("bias-expo").oninput = () => {
    const v = parseFloat($("bias-expo").value);
    $("bias-expo-val").textContent = `${v > 0 ? "+" : ""}${v.toFixed(1)} EV`;
  };
  $("bias-temp").oninput = () => {
    const v = parseInt($("bias-temp").value, 10);
    $("bias-temp-val").textContent = `${v > 0 ? "+" : ""}${v} K`;
  };
}

// --- Presets: brief + deslizadores guardados con nombre ---
async function loadPresets(selectName = "") {
  const sel = $("preset-select");
  try {
    const { presets } = await api("/api/presets");
    state.presets = presets;
    sel.innerHTML = '<option value="">Presets guardados…</option>';
    for (const p of presets) {
      const o = document.createElement("option");
      o.value = p.name;
      o.textContent = p.name;
      sel.appendChild(o);
    }
    sel.value = selectName;
  } catch (e) { /* sin presets no pasa nada */ }
}

function initPresets() {
  const sel = $("preset-select");
  sel.onchange = () => {
    const p = (state.presets || []).find((x) => x.name === sel.value);
    if (!p) return;
    $("session-prompt").value = p.prompt || "";
    $("bias-expo").value = p.exposure_bias || 0;
    $("bias-temp").value = p.temp_bias || 0;
    $("bias-expo").dispatchEvent(new Event("input"));
    $("bias-temp").dispatchEvent(new Event("input"));
  };
  $("preset-save").onclick = async () => {
    const name = window.prompt("Nombre del preset (si ya existe, se reemplaza):",
                               sel.value || "");
    if (!name || !name.trim()) return;
    const o = sessionOpts();
    const saved = await api("/api/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), prompt: o.session_prompt,
                             exposure_bias: o.exposure_bias, temp_bias: o.temp_bias }),
    });
    await loadPresets(saved.name);
  };
  $("preset-delete").onclick = async () => {
    if (!sel.value) return;
    if (!confirm(`¿Borrar el preset «${sel.value}»?`)) return;
    await api(`/api/presets?name=${encodeURIComponent(sel.value)}`, { method: "DELETE" });
    await loadPresets();
  };
  loadPresets();
}

function sessionOpts() {
  return {
    overwrite: $("overwrite").checked,
    harmonize: $("harmonize").checked,
    rate: $("rate").checked,
    exposure_bias: parseFloat($("bias-expo").value) || 0,
    temp_bias: parseInt($("bias-temp").value, 10) || 0,
    session_prompt: $("session-prompt").value.trim(),
  };
}

// Estrellas de culling (xmp:Rating) para el registro y la revisión
function starsOf(ev) {
  const r = ev.adjust && ev.adjust.rating;
  if (!r) return "";
  return "★".repeat(r) + "☆".repeat(5 - r);
}

// --- Pantalla 3: progreso ---
$("process").onclick = async () => {
  if (Notification.permission === "default") await Notification.requestPermission();
  state.opts = sessionOpts();
  const body = { files: [...state.selected], ...state.opts };
  const { job_id, local_only } = await api("/api/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  show("progress");
  $("done-actions").hidden = true;
  $("log").innerHTML = "";
  state.results = [];
  $("progress-title").textContent = local_only
    ? "Procesando (modo solo local — sin API)…" : "Procesando…";

  const source = new EventSource(`/api/jobs/${job_id}/events`);
  source.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    if (ev.type === "progress") {
      $("bar-fill").style.width = `${(100 * ev.completed) / ev.total}%`;
      $("progress-text").textContent = `Analizando foto ${ev.completed} de ${ev.total}…`;
      return;
    }
    if (ev.type === "photo") {
      state.results.push(ev);
      $("bar-fill").style.width = `${(100 * ev.completed) / ev.total}%`;
      $("progress-text").textContent = `Foto ${ev.completed} de ${ev.total}`;
      const li = document.createElement("li");
      const name = ev.path.split("/").pop();
      const labels = { done: "✓", done_local_only: "✓ (solo local)",
                       skipped_existing: "⏭ ya tenía XMP", error: "✗" };
      const reason = ev.adjust && ev.adjust.rating_reason
        ? ` — ${ev.adjust.rating_reason}` : "";
      li.textContent = `${labels[ev.status] || ev.status} ${name} ` +
        `${starsOf(ev)}${reason} ${ev.message || ""}`;
      if (ev.status === "error") li.className = "error";
      if (ev.status === "skipped_existing") li.className = "skipped";
      $("log").prepend(li);
    } else if (ev.type === "finished") {
      source.close();
      $("progress-title").textContent = "¡Terminado!";
      $("progress-text").textContent =
        `${ev.ok} de ${ev.total} fotos listas` +
        (ev.skipped ? `, ${ev.skipped} saltadas (ya tenían XMP)` : "") +
        (ev.errors ? `, ${ev.errors} con error` : "") +
        ". Ya puedes importar la carpeta en Lightroom (o Metadatos → Leer metadatos desde archivos).";
      $("done-actions").hidden = false;
      if (Notification.permission === "granted")
        new Notification("Revelado terminado", { body: $("progress-text").textContent });
    }
  };
  source.onerror = () => {
    if (source.readyState !== EventSource.CLOSED) return;
    source.close();
    $("progress-title").textContent = "Conexión perdida";
    $("progress-text").textContent =
      "Se perdió la conexión con el servidor. Las fotos ya procesadas conservan su XMP; recarga la página para reintentar.";
    $("done-actions").hidden = false;
  };
};

$("restart").onclick = () => loadDirs(state.dir ? state.dir.split("/").slice(0, -1).join("/") : "");

// --- Pantalla 4: revisión antes/después ---
function previewURL(ev) {
  // Simulación en el servidor con los mismos ajustes escritos al XMP
  const a = ev.adjust || {};
  const q = new URLSearchParams({
    path: ev.path,
    exposure: a.exposure || 0, contrast: a.contrast || 0,
    highlights: a.highlights || 0, shadows: a.shadows || 0,
    temp_shift: a.temp_shift || 0, tint: a.tint || 0,
    angle: a.angle || 0,
  });
  if (a.crop) q.set("crop", a.crop.join(","));
  return `/api/preview?${q.toString()}`;
}

function renderReview() {
  const grid = $("review-grid");
  grid.innerHTML = "";
  for (const ev of state.results.filter((r) => r.status.startsWith("done"))) {
    const name = ev.path.split("/").pop();
    const thumb = `/api/thumb?path=${encodeURIComponent(ev.path)}`;
    const card = document.createElement("div");
    card.className = "review-card";
    card.innerHTML = `
      <div class="pair">
        <div><div class="frame"><img src="${thumb}"></div><div class="caption">Antes</div></div>
        <div><div class="frame"><img src="${previewURL(ev)}"></div>
             <div class="caption">Después${ev.adjust && ev.adjust.masks ? ` · ${ev.adjust.masks} máscara(s)` : ""}</div></div>
      </div>
      <div class="caption">${name}${starsOf(ev) ? ` · ${starsOf(ev)}` : ""}${
        ev.adjust && ev.adjust.rating_reason ? ` · ${ev.adjust.rating_reason}` : ""}</div>
      <div class="actions">
        <button class="discard">Descartar edición</button>
        <button class="redo">Reprocesar</button>
      </div>`;
    card.querySelector(".discard").onclick = async () => {
      await api(`/api/xmp?path=${encodeURIComponent(ev.path)}`, { method: "DELETE" });
      card.classList.add("discarded");
    };
    card.querySelector(".redo").onclick = async () => {
      card.style.opacity = ".6";
      const { job_id } = await api("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: [ev.path], ...(state.opts || {}),
                               overwrite: true }),
      });
      const source = new EventSource(`/api/jobs/${job_id}/events`);
      source.onmessage = (msg) => {
        const e = JSON.parse(msg.data);
        if (e.type === "photo") {
          if (e.status === "error") {
            alert(`Error al reprocesar ${name}: ${e.message || ""}`);
          } else {
            ev.adjust = e.adjust;
            card.classList.remove("discarded");
          }
        }
        if (e.type === "finished") { source.close(); renderReview(); }
      };
      source.onerror = () => { source.close(); card.style.opacity = "1"; };
    };
    grid.appendChild(card);
  }
  show("review");
}

$("show-review").onclick = renderReview;
$("review-back").onclick = () => show("progress");

initSessionOpts();
initPresets();
loadDirs();
loadLrcat();
