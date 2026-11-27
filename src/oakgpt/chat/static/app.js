"use strict";

// ---------- Safe Markdown subset ------------------------------------------------------
// All model text is HTML-escaped before any markup is added; only tags generated here
// reach innerHTML. Links are deliberately rendered as plain text (no javascript: URLs).

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const escapeHtml = (text) => text.replace(/[&<>"']/g, (c) => ESCAPES[c]);

function inline(raw) {
  const codes = [];
  let text = escapeHtml(raw).replace(/`([^`\n]+)`/g, (_, code) => {
    codes.push(code);
    return `\u0000${codes.length - 1}\u0000`;
  });
  text = text
    .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\n]+?)\*(?![*\w])/g, "$1<em>$2</em>")
    .replace(/(^|[^_\w])_([^_\n]+?)_(?![_\w])/g, "$1<em>$2</em>");
  return text.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
}

const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));

function renderMarkdown(source) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) out.push(`<p>${paragraph.map(inline).join("<br>")}</p>`);
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(/^\s*```\s*([\w+#.-]*)/);
    if (fence) {
      flush();
      const body = [];
      while (++i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i]);
      const language = escapeHtml(fence[1] || "text");
      out.push(
        `<div class="codeblock"><div class="codeblock-head"><span>${language}</span>` +
          `<button type="button" data-copy>Copy</button></div>` +
          `<pre><code>${escapeHtml(body.join("\n"))}</code></pre></div>`
      );
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flush();
      const level = Math.min(5, heading[1].length + 2);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); out.push("<hr>"); continue; }
    if (line.includes("|") && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1])) {
      flush();
      const head = cells(line);
      const rows = [];
      i += 1;
      while (i + 1 < lines.length && lines[i + 1].includes("|") && lines[i + 1].trim()) {
        rows.push(cells(lines[++i]));
      }
      out.push(
        `<table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
          rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") +
          "</tbody></table>"
      );
      continue;
    }
    if (/^\s*>/.test(line)) {
      flush();
      const quote = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) quote.push(lines[i].replace(/^\s*>\s?/, ""));
      i -= 1;
      out.push(`<blockquote>${renderMarkdown(quote.join("\n"))}</blockquote>`);
      continue;
    }
    const item = line.match(LIST);
    if (item) {
      flush();
      const ordered = /\d/.test(item[2]);
      const items = [];
      for (; i < lines.length; i++) {
        const next = lines[i].match(LIST);
        if (next) items.push(inline(next[3]));
        else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) {
          items[items.length - 1] += "<br>" + inline(lines[i].trim());
        } else break;
      }
      i -= 1;
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((x) => `<li>${x}</li>`).join("")}</${tag}>`);
      continue;
    }
    paragraph.push(line);
  }
  flush();
  return out.join("");
}

// ---------- Elements and state --------------------------------------------------------

const $ = (id) => document.getElementById(id);
const el = {
  sidebar: $("sidebar"), scrim: $("scrim"), menu: $("menu"), history: $("history"),
  search: $("search"), newChat: $("new-chat"), title: $("title"), messages: $("messages"),
  empty: $("empty"), conversation: $("conversation"), composer: $("composer"),
  composerCard: $("composer-card"), input: $("input"), send: $("send"), attach: $("attach"),
  file: $("file"), attachments: $("attachments"), hint: $("hint"), main: $("main"),
  dropOverlay: $("drop-overlay"), mode: $("mode"), visionPill: $("vision-pill"),
  engineText: $("engine-text"), engineVision: $("engine-vision"), statusText: $("status-text"),
  toast: $("toast"), settingsButton: $("settings-button"), settings: $("settings"),
  settingsClose: $("settings-close"), drawerScrim: $("drawer-scrim"),
  systemPrompt: $("system-prompt"), temperature: $("temperature"),
  temperatureValue: $("temperature-value"), maxTokens: $("max-tokens"),
  resetSettings: $("reset-settings"), lightbox: $("lightbox"), lightboxImage: $("lightbox-image"),
  docsToggle: $("docs-toggle"), library: $("library"), libraryDot: $("library-dot"),
  librarySummary: $("library-summary"), libraryNote: $("library-note"),
  libraryAdd: $("library-add"), libraryReindex: $("library-reindex"), libraryFile: $("library-file"),
};
const LEAF = '<svg viewBox="0 0 24 24"><path d="M12 2.5c-1.3 1.6-3.6 2-4.8 3.6-1 1.3-.8 2.9-1.9 4.1C4 11.6 4.3 14 5.6 15.4c1.2 1.4 3.2 1.7 4.9 1.2V21h3v-4.4c1.7.5 3.7.2 4.9-1.2 1.3-1.4 1.6-3.8.3-5.2-1.1-1.2-.9-2.8-1.9-4.1-1.2-1.6-3.5-2-4.8-3.6Z"/></svg>';
const ICONS = {
  copy: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
  retry: '<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  image: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg>',
};
const MAX_IMAGES = 4;
const MAX_IMAGE_SIDE = 1600; // The server caps each image at 1024 tokens; larger only costs upload time.

const state = {
  presets: {}, defaultSystemPrompt: "", conversationId: null, conversation: null,
  busy: false, controller: null, status: null, history: [], pending: [], documents: null,
  prefs: { preset: null, temperature: null, maxTokens: null, systemPrompt: null, theme: "dark", documents: false },
};

function loadPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem("oakgpt.prefs") || "{}");
    // Older versions stored the default mode as if chosen; only explicit choices persist.
    if (saved.presetChosen !== true) delete saved.preset;
    Object.assign(state.prefs, saved);
  } catch { /* Storage may be unavailable; defaults still work. */ }
}
function savePrefs() {
  try { localStorage.setItem("oakgpt.prefs", JSON.stringify(state.prefs)); } catch { /* ignore */ }
}

let toastTimer = 0;
function toast(message) {
  el.toast.textContent = message;
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.toast.hidden = true; }, 6000);
}

async function api(path, options = {}) {
  const init = { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } };
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).error || message; } catch { /* not JSON */ }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response;
}

const timeOf = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");

// ---------- Theme ---------------------------------------------------------------------

function applyTheme() {
  const theme = state.prefs.theme;
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme === "light" ? "light" : "dark");
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.setAttribute("aria-checked", String(button.dataset.themeChoice === theme));
  }
}
for (const button of document.querySelectorAll("[data-theme-choice]")) {
  button.addEventListener("click", () => {
    state.prefs.theme = button.dataset.themeChoice;
    savePrefs();
    applyTheme();
  });
}

// ---------- Settings ------------------------------------------------------------------

// The user's explicit choice, else the server's configured default.
function presetName() { return state.prefs.preset ?? state.status?.default_preset ?? "chat"; }
function preset() { return state.presets[presetName()] || state.presets.chat || {}; }

function renderSettings() {
  for (const button of el.mode.querySelectorAll("button")) {
    button.setAttribute("aria-checked", String(button.dataset.preset === presetName()));
  }
  const temperature = state.prefs.temperature ?? preset().temperature ?? 0.7;
  el.temperature.value = temperature;
  el.temperatureValue.textContent = Number(temperature).toFixed(2);
  el.maxTokens.value = state.prefs.maxTokens ?? preset().max_new_tokens ?? 1024;
  el.systemPrompt.value = state.prefs.systemPrompt ?? state.defaultSystemPrompt;
}

function requestSettings() {
  const settings = { preset: presetName() };
  if (state.prefs.temperature !== null) settings.temperature = Number(state.prefs.temperature);
  if (state.prefs.maxTokens !== null) settings.max_new_tokens = Number(state.prefs.maxTokens);
  return settings;
}

for (const button of el.mode.querySelectorAll("button")) {
  button.addEventListener("click", () => {
    state.prefs.preset = button.dataset.preset;
    state.prefs.presetChosen = true;
    state.prefs.temperature = null;
    state.prefs.maxTokens = null;
    savePrefs();
    renderSettings();
  });
}
function setDrawer(open) {
  el.settings.hidden = !open;
  el.drawerScrim.hidden = !open;
  el.settingsButton.setAttribute("aria-expanded", String(open));
  if (open) el.systemPrompt.focus();
}
el.settingsButton.addEventListener("click", () => setDrawer(el.settings.hidden));
el.settingsClose.addEventListener("click", () => setDrawer(false));
el.drawerScrim.addEventListener("click", () => setDrawer(false));
el.temperature.addEventListener("input", () => {
  state.prefs.temperature = Number(el.temperature.value);
  el.temperatureValue.textContent = state.prefs.temperature.toFixed(2);
  savePrefs();
});
el.maxTokens.addEventListener("change", () => {
  const value = Math.round(Number(el.maxTokens.value));
  state.prefs.maxTokens = Number.isFinite(value) && value >= 16 ? Math.min(value, 8192) : null;
  savePrefs();
  renderSettings();
});
el.systemPrompt.addEventListener("change", () => {
  state.prefs.systemPrompt = el.systemPrompt.value;
  savePrefs();
});
el.resetSettings.addEventListener("click", () => {
  Object.assign(state.prefs, { temperature: null, maxTokens: null, systemPrompt: null });
  savePrefs();
  renderSettings();
});

// A conversation with any image is answered by the vision model; show that instead of the mode.
function usesVision() {
  return state.pending.length > 0 ||
    Boolean(state.conversation && state.conversation.messages.some((m) => m.images && m.images.length));
}
function renderModeIndicator() {
  const vision = usesVision();
  el.mode.hidden = vision;
  el.visionPill.hidden = !vision;
  renderDocsToggle();
}

// ---------- Documents -----------------------------------------------------------------

// Document answers are text-only: a conversation with images goes to the vision model.
function docsActive() {
  return Boolean(state.documents && state.documents.available) && state.prefs.documents && !usesVision();
}
function renderDocsToggle() {
  const available = Boolean(state.documents && state.documents.available);
  el.docsToggle.hidden = !available;
  el.docsToggle.disabled = usesVision();
  el.docsToggle.setAttribute("aria-pressed", String(available && state.prefs.documents));
  el.input.placeholder = docsActive()
    ? "Ask about your documents"
    : "Ask OakGPT anything, or attach an image";
}
el.docsToggle.addEventListener("click", () => {
  state.prefs.documents = !state.prefs.documents;
  savePrefs();
  renderDocsToggle();
  el.input.focus();
});

let documentsTimer = 0;
async function checkDocuments() {
  clearTimeout(documentsTimer);
  let next = 30_000;
  try {
    const status = await (await api("/api/documents")).json();
    state.documents = status;
    el.library.hidden = !status.available;
    if (status.available) {
      const dot = el.libraryDot;
      dot.className = "dot";
      if (status.state === "indexing") { dot.classList.add("loading"); next = 1_500; }
      else if (status.state === "ready") dot.classList.add("loaded");
      else if (status.state === "error") dot.classList.add("bad");
      const counts = status.chunks === undefined
        ? "Not indexed yet"
        : `${status.files} file${status.files === 1 ? "" : "s"} · ${status.chunks} passages`;
      el.librarySummary.textContent = status.state === "indexing" ? `Indexing… ${status.chunks === undefined ? "" : counts}` : counts;
      el.libraryNote.textContent = status.error || `${status.method} search · ${status.folder}`;
      el.libraryNote.title = status.folder || "";
    }
  } catch { next = 10_000; }
  renderDocsToggle();
  documentsTimer = setTimeout(checkDocuments, next);
}
el.libraryAdd.addEventListener("click", () => el.libraryFile.click());
el.libraryFile.addEventListener("change", async () => {
  for (const file of el.libraryFile.files) {
    try {
      const text = await file.text();
      await api("/api/documents", { method: "POST", body: JSON.stringify({ name: file.name, text }) });
      toast(`Added ${file.name}. Indexing…`);
    } catch (error) { toast(`${file.name}: ${error.message}`); }
  }
  el.libraryFile.value = "";
  checkDocuments();
});
el.libraryReindex.addEventListener("click", async () => {
  try { await api("/api/documents/reindex", { method: "POST", body: "{}" }); }
  catch (error) { toast(error.message); }
  checkDocuments();
});

// Citation markers such as [2] or [1, 3] become buttons that open their source card.
const CITATION = /\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]/g;
function citedNumbers(text, count) {
  const cited = new Set();
  for (const match of text.matchAll(CITATION)) {
    for (const part of match[1].split(/[,;]/)) {
      const n = Number(part.trim());
      if (n >= 1 && n <= count) cited.add(n);
    }
  }
  return cited;
}
function linkCitations(html, count) {
  return html.split(/(<pre>[\s\S]*?<\/pre>|<code>[\s\S]*?<\/code>)/).map((part, index) => {
    if (index % 2) return part;
    return part.replace(CITATION, (whole, list) => {
      const numbers = list.split(/[,;]/).map((x) => Number(x.trim()));
      if (!numbers.every((n) => n >= 1 && n <= count)) return whole;
      return numbers.map((n) => `<button type="button" class="cite" data-cite="${n}" aria-label="Source ${n}">${n}</button>`).join("");
    });
  }).join("");
}
function renderAnswer(view) {
  const html = renderMarkdown(view.text);
  return view.sources && view.sources.length ? linkCitations(html, view.sources.length) : html;
}

function sourceCard(source, cited) {
  const card = document.createElement("details");
  card.className = cited ? "source cited" : "source";
  card.dataset.n = String(source.n);
  const summary = document.createElement("summary");
  const number = document.createElement("span");
  number.className = "source-n";
  number.textContent = String(source.n);
  const path = document.createElement("span");
  path.className = "source-path";
  path.textContent = source.path;
  const heading = document.createElement("span");
  heading.className = "source-heading";
  heading.textContent = source.heading || "";
  summary.append(number, path, heading);
  const excerpt = document.createElement("div");
  excerpt.className = "source-excerpt";
  excerpt.textContent = source.excerpt + (source.excerpt.length >= 600 ? "…" : "");
  card.append(summary, excerpt);
  return card;
}
function renderSources(view) {
  view.sourcesBox.replaceChildren();
  const sources = view.sources || [];
  view.sourcesBox.hidden = sources.length === 0;
  if (!sources.length) return;
  const cited = citedNumbers(view.text, sources.length);
  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = cited.size ? "Sources" : `Searched ${sources.length} passages from your documents`;
  view.sourcesBox.append(title);
  for (const source of sources) if (cited.has(source.n)) view.sourcesBox.append(sourceCard(source, true));
  const rest = sources.filter((source) => !cited.has(source.n));
  if (!rest.length) return;
  const more = document.createElement("details");
  more.className = "sources-more";
  const label = document.createElement("summary");
  label.textContent = cited.size ? `${rest.length} more searched passage${rest.length === 1 ? "" : "s"}` : "Show passages";
  more.append(label, ...rest.map((source) => sourceCard(source, false)));
  view.sourcesBox.append(more);
}
el.messages.addEventListener("click", (event) => {
  const button = event.target.closest(".cite");
  if (!button) return;
  const card = button.closest(".entry").querySelector(`.source[data-n="${button.dataset.cite}"]`);
  if (!card) return;
  const group = card.closest(".sources-more");
  if (group) group.open = true;
  card.open = true;
  card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  card.classList.add("flash");
  setTimeout(() => card.classList.remove("flash"), 1200);
});

// ---------- Sidebar -------------------------------------------------------------------

function group(updated) {
  const days = (Date.now() - Date.parse(updated)) / 86_400_000;
  if (days < 1 && new Date(updated).toDateString() === new Date().toDateString()) return "Today";
  if (days < 2) return "Yesterday";
  if (days < 7) return "This week";
  return "Older";
}

async function refreshHistory() {
  state.history = await (await api("/api/conversations")).json();
  renderHistory();
}

function renderHistory() {
  const query = el.search.value.trim().toLowerCase();
  const list = state.history.filter((item) => !query || item.title.toLowerCase().includes(query));
  el.history.replaceChildren();
  if (!list.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = query ? "No matching conversations." : "Your conversations will appear here.";
    el.history.append(empty);
    return;
  }
  let current = "";
  for (const item of list) {
    const label = group(item.updated);
    if (label !== current) {
      current = label;
      const heading = document.createElement("div");
      heading.className = "history-group";
      heading.textContent = label;
      el.history.append(heading);
    }
    const row = document.createElement("div");
    row.className = "history-item" + (item.id === state.conversationId ? " active" : "");
    const link = document.createElement("a");
    link.href = `#/c/${item.id}`;
    link.title = item.title;
    const title = document.createElement("span");
    title.className = "item-title";
    title.textContent = item.title;
    const meta = document.createElement("span");
    meta.className = "item-meta";
    meta.textContent = `${item.messages} message${item.messages === 1 ? "" : "s"} · ${timeOf(item.updated)}`;
    if (item.images) meta.insertAdjacentHTML("afterbegin", ICONS.image);
    link.append(title, meta);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete";
    remove.setAttribute("aria-label", `Delete ${item.title}`);
    remove.innerHTML = ICONS.trash;
    remove.addEventListener("click", async () => {
      if (!confirm(`Delete “${item.title}”? This cannot be undone.`)) return;
      try {
        await api(`/api/conversations/${item.id}`, { method: "DELETE" });
        if (item.id === state.conversationId) location.hash = "";
        await refreshHistory();
      } catch (error) { toast(error.message); }
    });
    row.append(link, remove);
    el.history.append(row);
  }
}

el.search.addEventListener("input", renderHistory);
function closeSidebar() { el.sidebar.classList.remove("open"); el.scrim.hidden = true; }
el.menu.addEventListener("click", () => { el.sidebar.classList.add("open"); el.scrim.hidden = false; });
el.scrim.addEventListener("click", closeSidebar);
el.newChat.addEventListener("click", () => { location.hash = ""; closeSidebar(); el.input.focus(); });

// ---------- Image attachments ---------------------------------------------------------

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

// Decode in the browser and re-encode as PNG or JPEG: this strips metadata such as EXIF
// location, bounds the size and gives llama.cpp a format it is known to decode.
async function prepareImage(file) {
  if (!file.type.startsWith("image/")) throw new Error(`${file.name || "That file"} is not an image.`);
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  const png = file.type === "image/png";
  if (!png) { context.fillStyle = "#ffffff"; context.fillRect(0, 0, width, height); }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const encode = (type) => new Promise((resolve) => canvas.toBlob(resolve, type, 0.9));
  let blob = await encode(png ? "image/png" : "image/jpeg");
  if (png && blob.size > 4 * 1024 * 1024) blob = await encode("image/jpeg");
  return { blob, url: URL.createObjectURL(blob), base64: await blobToBase64(blob) };
}

async function addFiles(files) {
  const images = [...files].filter((file) => file.type.startsWith("image/"));
  if (!images.length) { toast("Only image files can be attached."); return; }
  if (state.status && !state.status.vision_available) { toast("No vision model is configured."); return; }
  for (const file of images) {
    if (state.pending.length >= MAX_IMAGES) { toast(`At most ${MAX_IMAGES} images per message.`); break; }
    try { state.pending.push(await prepareImage(file)); } catch (error) { toast(error.message || "Could not read that image."); }
  }
  renderAttachments();
  el.input.focus();
}

function clearAttachments() {
  for (const item of state.pending) URL.revokeObjectURL(item.url);
  state.pending = [];
  renderAttachments();
}

function renderAttachments() {
  el.attachments.replaceChildren();
  el.attachments.hidden = state.pending.length === 0;
  state.pending.forEach((item, index) => {
    const wrap = document.createElement("div");
    wrap.className = "attachment";
    const img = document.createElement("img");
    img.src = item.url;
    img.alt = `Attached image ${index + 1}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove image ${index + 1}`);
    remove.innerHTML = ICONS.close;
    remove.addEventListener("click", () => {
      URL.revokeObjectURL(item.url);
      state.pending.splice(index, 1);
      renderAttachments();
    });
    wrap.append(img, remove);
    el.attachments.append(wrap);
  });
  el.attach.disabled = state.pending.length >= MAX_IMAGES;
  renderModeIndicator();
  updateSendEnabled();
}

el.attach.addEventListener("click", () => el.file.click());
el.file.addEventListener("change", () => { addFiles(el.file.files); el.file.value = ""; });
el.input.addEventListener("paste", (event) => {
  const files = [...(event.clipboardData?.files || [])];
  if (files.some((file) => file.type.startsWith("image/"))) { event.preventDefault(); addFiles(files); }
});
let dragDepth = 0;
const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
el.main.addEventListener("dragenter", (event) => {
  if (!hasFiles(event)) return;
  event.preventDefault();
  dragDepth += 1;
  el.dropOverlay.hidden = false;
});
el.main.addEventListener("dragover", (event) => { if (hasFiles(event)) event.preventDefault(); });
el.main.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) el.dropOverlay.hidden = true;
});
el.main.addEventListener("drop", (event) => {
  if (!hasFiles(event)) return;
  event.preventDefault();
  dragDepth = 0;
  el.dropOverlay.hidden = true;
  addFiles(event.dataTransfer.files);
});

function openLightbox(src, alt) {
  el.lightboxImage.src = src;
  el.lightboxImage.alt = alt || "";
  el.lightbox.hidden = false;
}
el.lightbox.addEventListener("click", () => { el.lightbox.hidden = true; el.lightboxImage.src = ""; });
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!el.lightbox.hidden) { el.lightbox.hidden = true; el.lightboxImage.src = ""; }
  else if (!el.settings.hidden) setDrawer(false);
});

// ---------- Messages ------------------------------------------------------------------

const MODEL_LABELS = { text: "Qwen3", vision: "Qwen3-VL" };

function formatStats(stats) {
  if (!stats) return "";
  const parts = [`${stats.generated_tokens} tokens`];
  if (stats.server_decode_tokens_per_second) parts.push(`${stats.server_decode_tokens_per_second.toFixed(0)} tok/s`);
  if (stats.ttft_s !== null && stats.ttft_s !== undefined) parts.push(`first token ${stats.ttft_s.toFixed(2)} s`);
  if (stats.stop_type === "limit") parts.push("stopped at token limit");
  return parts.join(" · ");
}

function entry(role, created) {
  const node = document.createElement("article");
  node.className = `entry ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  if (role === "user") avatar.textContent = "Y";
  else avatar.innerHTML = LEAF;
  const head = document.createElement("div");
  head.className = "entry-head";
  const name = document.createElement("span");
  name.className = "entry-name";
  name.textContent = role === "user" ? "You" : "OakGPT";
  const time = document.createElement("span");
  time.className = "entry-time";
  time.textContent = timeOf(created || new Date().toISOString());
  head.append(name, time);
  const body = document.createElement("div");
  body.className = "entry-body";
  node.append(avatar, head, body);
  el.messages.append(node);
  return { node, body };
}

function addUser(message, localImages = []) {
  const { node, body } = entry("user", message.created);
  const sources = localImages.length
    ? localImages.map((item) => item.url)
    : (message.images || []).map((image) => `/api/conversations/${state.conversationId}/images/${image.id}`);
  if (sources.length) {
    const thumbs = document.createElement("div");
    thumbs.className = "thumbs";
    sources.forEach((src, index) => {
      const img = document.createElement("img");
      img.src = src;
      img.alt = `Image ${index + 1}`;
      img.loading = "lazy";
      img.addEventListener("click", () => openLightbox(src, img.alt));
      thumbs.append(img);
    });
    body.append(thumbs);
  }
  const text = document.createElement("div");
  text.className = "text";
  text.textContent = message.content || "";
  body.append(text);
  return node;
}

function addAssistant(message = {}) {
  const { node, body } = entry("assistant", message.created);
  const status = document.createElement("div");
  status.className = "status-line";
  status.hidden = true;
  const notice = document.createElement("div");
  notice.className = "notice";
  notice.hidden = true;
  const details = document.createElement("details");
  details.className = "reasoning";
  details.hidden = !message.reasoning;
  const summary = document.createElement("summary");
  summary.textContent = "Thought process";
  const reasoningBody = document.createElement("div");
  reasoningBody.className = "reasoning-body";
  reasoningBody.textContent = message.reasoning || "";
  details.append(summary, reasoningBody);
  const answer = document.createElement("div");
  answer.className = "answer";
  const sourcesBox = document.createElement("div");
  sourcesBox.className = "sources";
  sourcesBox.hidden = true;
  const footer = document.createElement("div");
  footer.className = "entry-footer";
  body.append(status, notice, details, answer, sourcesBox, footer);
  const view = {
    node, status, notice, details, summary, reasoningBody, answer, sourcesBox, footer,
    text: message.content || "", reasoning: message.reasoning || "",
    sources: (message.meta && message.meta.sources) || null,
  };
  setNotice(view, message.meta);
  if (message.content !== undefined) answer.innerHTML = renderAnswer(view);
  renderSources(view);
  return view;
}

function setStatus(view, text) {
  view.status.replaceChildren();
  view.status.hidden = !text;
  if (!text) return;
  const dot = document.createElement("span");
  dot.className = "dot";
  const label = document.createElement("span");
  label.textContent = text;
  view.status.append(dot, label);
}

function setNotice(view, meta) {
  const notes = [];
  if (meta && meta.dropped_exchanges > 0) {
    const n = meta.dropped_exchanges;
    notes.push(`${n} earlier exchange${n === 1 ? " was" : "s were"} left out so the conversation fits the ${meta.context_length}-token context.`);
  }
  if (meta && meta.model_load_s) notes.push(`Loaded the ${meta.model === "vision" ? "image" : "text"} model in ${meta.model_load_s.toFixed(1)} s.`);
  view.notice.textContent = notes.join(" ");
  view.notice.hidden = notes.length === 0;
}

function finishAssistant(view, message, isLast) {
  renderSources(view);
  view.footer.replaceChildren();
  const copy = document.createElement("button");
  copy.type = "button";
  copy.title = "Copy";
  copy.setAttribute("aria-label", "Copy reply");
  copy.innerHTML = ICONS.copy;
  copy.addEventListener("click", () => copyText(view.text, copy));
  view.footer.append(copy);
  if (isLast) {
    const retry = document.createElement("button");
    retry.type = "button";
    retry.title = "Regenerate";
    retry.setAttribute("aria-label", "Regenerate reply");
    retry.innerHTML = ICONS.retry;
    retry.addEventListener("click", () => regenerate(view));
    view.footer.append(retry);
  }
  const model = message.meta && message.meta.model;
  if (model) {
    const chip = document.createElement("span");
    chip.className = `model-chip ${model}`;
    chip.textContent = MODEL_LABELS[model] || model;
    view.footer.append(chip);
  }
  if (view.sources && view.sources.length) {
    const chip = document.createElement("span");
    chip.className = "model-chip docs";
    chip.textContent = "Docs";
    view.footer.append(chip);
  }
  if (message.interrupted) {
    const note = document.createElement("span");
    note.className = "interrupted";
    note.textContent = "Stopped";
    view.footer.append(note);
  }
  const stats = document.createElement("span");
  stats.className = "stats";
  stats.textContent = formatStats(message.stats);
  view.footer.append(stats);
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    const previous = button.title;
    button.title = "Copied";
    setTimeout(() => { button.title = previous; }, 1500);
  } catch { toast("Copying is not available in this browser context."); }
}

el.messages.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const code = button.closest(".codeblock").querySelector("code").textContent;
  copyText(code, button).then(() => {
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy"; }, 1500);
  });
});

function nearBottom() {
  const c = el.conversation;
  return c.scrollHeight - c.scrollTop - c.clientHeight < 120;
}
function scrollToBottom() { el.conversation.scrollTop = el.conversation.scrollHeight; }

function renderConversation(conversation) {
  el.messages.replaceChildren();
  el.title.textContent = conversation ? conversation.title : "New conversation";
  document.title = conversation ? `${conversation.title} · OakGPT` : "OakGPT";
  const messages = conversation ? conversation.messages : [];
  el.empty.hidden = messages.length > 0;
  messages.forEach((message, index) => {
    if (message.role === "user") addUser(message);
    else finishAssistant(addAssistant(message), message, index === messages.length - 1);
  });
  renderModeIndicator();
  scrollToBottom();
}

// ---------- Streaming -----------------------------------------------------------------

function setBusy(busy) {
  state.busy = busy;
  el.send.classList.toggle("busy", busy);
  el.send.querySelector(".send-label").textContent = busy ? "Stop" : "Send";
  el.send.setAttribute("aria-label", busy ? "Stop generating" : "Send");
  updateSendEnabled();
}
function updateSendEnabled() {
  el.send.disabled = !state.busy && !el.input.value.trim() && state.pending.length === 0;
}

function pendingStatus(vision) {
  const active = state.status && state.status.active_model;
  if (vision && active !== "vision") return "Loading the image model…";
  if (!vision && active === "vision") return "Loading the text model…";
  return vision ? "Looking at the image…" : "Thinking…";
}

async function streamReply(body, view, vision) {
  state.controller = new AbortController();
  setBusy(true);
  let rendered = false;
  const cursor = '<span class="cursor"></span>';
  const paint = () => {
    rendered = false;
    const stick = nearBottom();
    view.answer.innerHTML = renderAnswer(view) + (state.busy ? cursor : "");
    if (stick) scrollToBottom();
  };
  const schedule = () => { if (!rendered) { rendered = true; requestAnimationFrame(paint); } };
  setStatus(view, body.documents ? "Searching your documents…" : pendingStatus(vision));
  let finalMessage = null;
  try {
    const response = await api(`/api/conversations/${state.conversationId}/reply`, {
      method: "POST", body: JSON.stringify(body), signal: state.controller.signal,
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let split;
      while ((split = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        const name = (block.match(/^event: (.*)$/m) || [])[1];
        const data = JSON.parse((block.match(/^data: (.*)$/m) || [, "{}"])[1]);
        if (name === "meta") {
          setNotice(view, data);
          if (data.sources) { view.sources = data.sources; renderSources(view); }
          setStatus(view, data.images ? "Looking at the image…" : "Thinking…");
          checkStatus();
        } else if (name === "reasoning") {
          setStatus(view, "");
          view.reasoning += data.text;
          view.details.hidden = false;
          view.details.open = true;
          view.summary.textContent = "Thinking";
          view.summary.classList.add("thinking-label");
          view.reasoningBody.textContent = view.reasoning;
          if (nearBottom()) scrollToBottom();
        } else if (name === "answer") {
          setStatus(view, "");
          if (view.summary.classList.contains("thinking-label")) {
            view.summary.classList.remove("thinking-label");
            view.summary.textContent = "Thought process";
            view.details.open = false;
          }
          view.text += data.text;
          schedule();
        } else if (name === "error") toast(data.error);
        else if (name === "done") {
          finalMessage = data.message;
          el.title.textContent = data.title;
        }
      }
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      toast(error.message);
      if (body.content !== undefined && !view.text && error.status) {
        // Rejected before streaming: the server rolled the user message back.
        view.node.previousElementSibling?.remove();
        view.node.remove();
        el.input.value = body.content;
        updateSendEnabled();
        el.empty.hidden = el.messages.children.length > 0;
        return false;
      }
    }
  } finally {
    setBusy(false);
    state.controller = null;
    setStatus(view, "");
    view.summary.classList.remove("thinking-label");
    if (view.summary.textContent === "Thinking") view.summary.textContent = "Thought process";
    paint();
  }
  finishAssistant(view, finalMessage || { interrupted: true }, true);
  // The server stores interrupted replies once it notices the closed stream.
  setTimeout(() => syncConversation().catch(() => {}), finalMessage ? 0 : 400);
  return true;
}

async function syncConversation() {
  if (!state.conversationId) return;
  state.conversation = await (await api(`/api/conversations/${state.conversationId}`)).json();
  if (!state.busy) renderConversation(state.conversation);
  await refreshHistory();
  checkStatus();
}

async function send(text) {
  if (!state.conversationId) {
    const systemPrompt = state.prefs.systemPrompt ?? state.defaultSystemPrompt;
    const created = await (await api("/api/conversations", {
      method: "POST", body: JSON.stringify({ system_prompt: systemPrompt }),
    })).json();
    state.conversationId = created.id;
    state.conversation = created;
    history.replaceState(null, "", `#/c/${created.id}`);
  }
  const images = state.pending;
  const vision = usesVision();
  state.pending = [];
  renderAttachments();
  el.empty.hidden = true;
  for (const button of el.messages.querySelectorAll('[aria-label="Regenerate reply"]')) button.remove();
  addUser({ content: text }, images);
  const view = addAssistant();
  scrollToBottom();
  const body = { content: text, settings: requestSettings() };
  if (images.length) body.images = images.map((item) => item.base64);
  else if (docsActive()) body.documents = true;
  const accepted = await streamReply(body, view, vision);
  if (accepted === false) { state.pending = images; renderAttachments(); }
  else for (const item of images) setTimeout(() => URL.revokeObjectURL(item.url), 5000);
}

async function regenerate(view) {
  if (state.busy) return;
  const fresh = addAssistant();
  view.node.replaceWith(fresh.node);
  const body = { regenerate: true, settings: requestSettings() };
  if (view.sources && view.sources.length) body.documents = true; // Keep the reply's mode.
  await streamReply(body, fresh, usesVision());
}

el.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy) { state.controller?.abort(); return; }
  const text = el.input.value.trim();
  if (!text && !state.pending.length) return;
  el.input.value = "";
  autosize();
  updateSendEnabled();
  try { await send(text); } catch (error) { toast(error.message); el.input.value = text; updateSendEnabled(); }
});
el.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!state.busy) el.composer.requestSubmit();
  }
});
function autosize() {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 240)}px`;
}
el.input.addEventListener("input", () => { autosize(); updateSendEnabled(); });
for (const button of document.querySelectorAll("#suggestions button")) {
  button.addEventListener("click", () => {
    if (button.hasAttribute("data-attach")) { el.file.click(); return; }
    el.input.value = button.dataset.prompt;
    autosize();
    updateSendEnabled();
    el.composer.requestSubmit();
  });
}

// ---------- Routing and status --------------------------------------------------------

async function route() {
  if (state.busy) state.controller?.abort();
  const match = location.hash.match(/^#\/c\/([0-9a-f]{32})$/);
  closeSidebar();
  if (!match) {
    state.conversationId = null;
    state.conversation = null;
    renderConversation(null);
  } else {
    try {
      state.conversationId = match[1];
      state.conversation = await (await api(`/api/conversations/${match[1]}`)).json();
      renderConversation(state.conversation);
    } catch (error) {
      toast(error.status === 404 ? "That conversation no longer exists." : error.message);
      location.hash = "";
      return;
    }
  }
  await refreshHistory().catch((error) => toast(error.message));
  el.input.focus();
}
window.addEventListener("hashchange", route);

function setEngine(row, model, status) {
  const dot = row.querySelector(".dot");
  dot.className = "dot";
  if (status.loading === model) dot.classList.add("loading");
  else if (status.active_model === model && status.ready) dot.classList.add("loaded");
}

let statusTimer = 0;
async function checkStatus() {
  clearTimeout(statusTimer);
  let next = 30_000;
  try {
    const status = await (await api("/api/status")).json();
    state.status = status;
    state.presets = status.presets || state.presets;
    state.defaultSystemPrompt = status.system_prompt ?? state.defaultSystemPrompt;
    el.engineVision.hidden = !status.vision_available;
    setEngine(el.engineText, "text", status);
    setEngine(el.engineVision, "vision", status);
    if (status.loading) {
      el.statusText.textContent = `Loading the ${status.loading === "vision" ? "image" : "text"} model…`;
      next = 1_500;
    } else if (status.ready) {
      el.statusText.textContent = `${status.model_path} · ${status.context_length} ctx`;
    } else {
      el.statusText.textContent = status.error || "Model server not ready";
      next = 5_000;
    }
    el.statusText.title = status.identity ? JSON.stringify(status.identity, null, 1) : "";
    el.attach.hidden = !status.vision_available;
  } catch {
    el.statusText.textContent = "Chat server unreachable";
    for (const row of [el.engineText, el.engineVision]) row.querySelector(".dot").className = "dot bad";
    next = 5_000;
  }
  renderSettings();
  statusTimer = setTimeout(checkStatus, next);
}

loadPrefs();
applyTheme();
checkStatus();
checkDocuments();
route();
updateSendEnabled();
