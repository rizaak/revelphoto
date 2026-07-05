const $ = (id) => document.getElementById(id);
const state = { dir: null, selected: new Set(), results: [] };

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
    li.innerHTML = `<span>📁 ${d.name}</span>` +
      (d.raw_count ? `<span class="raw-count">${d.raw_count} RAW</span>` : "");
    li.onclick = () => d.raw_count ? openGallery(d.path) : loadDirs(d.path);
    ul.appendChild(li);
  }
  show("browser");
  $("subtitle").textContent = "Selecciona una carpeta o una fuente del catálogo de Lightroom";
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
    const title = document.createElement("div");
    title.className = "lr-title";
    title.textContent = `📔 Catálogo de Lightroom (${cat.name})`;
    box.appendChild(title);
    const ul = document.createElement("ul");
    ul.id = "lr-sources";
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
  renderGallery(data.photos.filter((p) => !p.missing), subtitle);
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
      $("process").disabled = state.selected.size === 0;
      $("process").textContent = `Procesar ${state.selected.size} foto(s)`;
    };
    grid.appendChild(div);
  }
  $("subtitle").textContent = subtitle;
  $("process").disabled = true;
  $("process").textContent = "Procesar seleccionadas";
  show("gallery");
}

async function openGallery(dir) {
  state.dir = dir;
  const data = await api(`/api/photos?dir=${encodeURIComponent(dir)}`);
  renderGallery(data.photos, dir);
}

$("back").onclick = () => loadDirs(state.dir ? state.dir.split("/").slice(0, -1).join("/") : "");
$("select-all").onclick = () => {
  document.querySelectorAll(".photo").forEach((el) => {
    el.classList.add("selected");
    state.selected.add(el.dataset.path);
  });
  $("process").disabled = state.selected.size === 0;
  $("process").textContent = `Procesar ${state.selected.size} foto(s)`;
};

// --- Opciones de sesión: sesgos e indicaciones para la IA ---
const CHIP_SUGGESTIONS = [
  "Luminosas y aireadas",
  "Cálidas y acogedoras",
  "Frías y limpias",
  "Contraste suave, acabado mate",
  "Colores vivos y saturados",
  "Piel natural y uniforme",
  "Respeta el ambiente de la luz original",
  "Estilo editorial elegante",
];

function initSessionOpts() {
  const chips = $("chips");
  for (const text of CHIP_SUGGESTIONS) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = "+ " + text;
    b.onclick = () => {
      const area = $("session-prompt");
      area.value = (area.value.trim() ? area.value.trim() + ". " : "") + text;
    };
    chips.appendChild(b);
  }
  $("bias-expo").oninput = () => {
    const v = parseFloat($("bias-expo").value);
    $("bias-expo-val").textContent = `${v > 0 ? "+" : ""}${v.toFixed(1)} EV`;
  };
  $("bias-temp").oninput = () => {
    const v = parseInt($("bias-temp").value, 10);
    $("bias-temp-val").textContent = `${v > 0 ? "+" : ""}${v} K`;
  };
}

function sessionOpts() {
  return {
    overwrite: $("overwrite").checked,
    harmonize: $("harmonize").checked,
    exposure_bias: parseFloat($("bias-expo").value) || 0,
    temp_bias: parseInt($("bias-temp").value, 10) || 0,
    session_prompt: $("session-prompt").value.trim(),
  };
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
      li.textContent = `${labels[ev.status] || ev.status} ${name} ${ev.message || ""}`;
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
      <div class="caption">${name}</div>
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
loadDirs();
loadLrcat();
