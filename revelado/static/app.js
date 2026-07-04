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
  $("subtitle").textContent = "Selecciona la carpeta de la sesión (las que tienen RAW se abren como galería)";
}

// --- Pantalla 2: galería ---
async function openGallery(dir) {
  state.dir = dir;
  state.selected.clear();
  const data = await api(`/api/photos?dir=${encodeURIComponent(dir)}`);
  const grid = $("grid");
  grid.innerHTML = "";
  for (const p of data.photos) {
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
  $("subtitle").textContent = dir;
  $("process").disabled = true;
  $("process").textContent = "Procesar seleccionadas";
  show("gallery");
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

// --- Pantalla 3: progreso ---
$("process").onclick = async () => {
  if (Notification.permission === "default") await Notification.requestPermission();
  const body = { files: [...state.selected], overwrite: $("overwrite").checked };
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
function adjustedStyle(adjust) {
  if (!adjust) return "";
  const brightness = Math.pow(2, adjust.exposure || 0).toFixed(2);
  const rotate = -(adjust.angle || 0);
  let scale = 1;
  if (adjust.crop) {
    const [l, t, r, b] = adjust.crop;
    scale = 1 / Math.max(0.3, Math.min(r - l, b - t));
  }
  return `filter: brightness(${brightness}); transform: rotate(${rotate}deg) scale(${scale});`;
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
        <div><div class="frame"><img src="${thumb}" style="${adjustedStyle(ev.adjust)}"></div>
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
        body: JSON.stringify({ files: [ev.path], overwrite: true }),
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

loadDirs();
