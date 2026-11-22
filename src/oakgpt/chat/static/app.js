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
  newChat: $("new-chat"), title: $("title"), messages: $("messages"), empty: $("empty"),
  conversation: $("conversation"), composer: $("composer"), input: $("input"), send: $("send"),
  statusDot: $("status-dot"), statusText: $("status-text"), toast: $("toast"),
  settingsButton: $("settings-button"), settings: $("settings"), systemPrompt: $("system-prompt"),
  temperature: $("temperature"), temperatureValue: $("temperature-value"),
  maxTokens: $("max-tokens"), resetSettings: $("reset-settings"),
};
const ICONS = {
  copy: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
  retry: '<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
};

const state = {
  presets: {}, defaultSystemPrompt: "", conversationId: null, conversation: null,
  busy: false, controller: null,
  prefs: { preset: "chat", temperature: null, maxTokens: null, systemPrompt: null },
};

function loadPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem("oakgpt.prefs") || "{}");
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

// ---------- Settings ------------------------------------------------------------------

function preset() { return state.presets[state.prefs.preset] || state.presets.chat || {}; }

function renderSettings() {
  for (const button of document.querySelectorAll(".mode button")) {
    button.setAttribute("aria-checked", String(button.dataset.preset === state.prefs.preset));
  }
  const temperature = state.prefs.temperature ?? preset().temperature ?? 0.7;
  el.temperature.value = temperature;
  el.temperatureValue.textContent = Number(temperature).toFixed(2);
  el.maxTokens.value = state.prefs.maxTokens ?? preset().max_new_tokens ?? 1024;
  el.systemPrompt.value = state.prefs.systemPrompt ?? state.defaultSystemPrompt;
}

function requestSettings() {
  const settings = { preset: state.prefs.preset };
  if (state.prefs.temperature !== null) settings.temperature = Number(state.prefs.temperature);
  if (state.prefs.maxTokens !== null) settings.max_new_tokens = Number(state.prefs.maxTokens);
  return settings;
}

for (const button of document.querySelectorAll(".mode button")) {
  button.addEventListener("click", () => {
    state.prefs.preset = button.dataset.preset;
    state.prefs.temperature = null;
    state.prefs.maxTokens = null;
    savePrefs();
    renderSettings();
  });
}
el.settingsButton.addEventListener("click", () => {
  el.settings.hidden = !el.settings.hidden;
  el.settingsButton.setAttribute("aria-expanded", String(!el.settings.hidden));
});
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

// ---------- Sidebar -------------------------------------------------------------------

function group(updated) {
  const days = (Date.now() - Date.parse(updated)) / 86_400_000;
  if (days < 1 && new Date(updated).toDateString() === new Date().toDateString()) return "Today";
  if (days < 2) return "Yesterday";
  if (days < 7) return "Previous 7 days";
  return "Older";
}

async function refreshHistory() {
  const list = await (await api("/api/conversations")).json();
  el.history.replaceChildren();
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
    link.textContent = item.title;
    link.title = item.title;
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

function closeSidebar() { el.sidebar.classList.remove("open"); el.scrim.hidden = true; }
el.menu.addEventListener("click", () => { el.sidebar.classList.add("open"); el.scrim.hidden = false; });
el.scrim.addEventListener("click", closeSidebar);
el.newChat.addEventListener("click", () => { location.hash = ""; closeSidebar(); el.input.focus(); });

// ---------- Messages ------------------------------------------------------------------

function formatStats(stats) {
  if (!stats) return "";
  const parts = [`${stats.generated_tokens} tokens`];
  if (stats.server_decode_tokens_per_second) parts.push(`${stats.server_decode_tokens_per_second.toFixed(1)} tok/s`);
  if (stats.ttft_s !== null && stats.ttft_s !== undefined) parts.push(`first token ${stats.ttft_s.toFixed(2)} s`);
  if (stats.stop_type === "limit") parts.push("stopped at token limit");
  return parts.join(" · ");
}

function addUser(text) {
  const node = document.createElement("div");
  node.className = "message user";
  node.textContent = text;
  el.messages.append(node);
  return node;
}

function addAssistant(message = {}) {
  const node = document.createElement("div");
  node.className = "message assistant";
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
  const footer = document.createElement("div");
  footer.className = "message-footer";
  node.append(notice, details, answer, footer);
  el.messages.append(node);
  const view = { node, notice, details, summary, reasoningBody, answer, footer, text: message.content || "", reasoning: message.reasoning || "" };
  setNotice(view, message.meta);
  if (message.content !== undefined) answer.innerHTML = renderMarkdown(view.text);
  return view;
}

function setNotice(view, meta) {
  if (meta && meta.dropped_exchanges > 0) {
    const n = meta.dropped_exchanges;
    view.notice.textContent = `${n} earlier exchange${n === 1 ? " was" : "s were"} left out so the conversation fits the ${meta.context_length}-token context.`;
    view.notice.hidden = false;
  }
}

function finishAssistant(view, message, isLast) {
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
  el.title.textContent = conversation ? conversation.title : "New chat";
  document.title = conversation ? `${conversation.title} · OakGPT` : "OakGPT";
  const messages = conversation ? conversation.messages : [];
  el.empty.hidden = messages.length > 0;
  messages.forEach((message, index) => {
    if (message.role === "user") addUser(message.content);
    else finishAssistant(addAssistant(message), message, index === messages.length - 1);
  });
  scrollToBottom();
}

// ---------- Streaming -----------------------------------------------------------------

function setBusy(busy) {
  state.busy = busy;
  el.send.classList.toggle("busy", busy);
  el.send.setAttribute("aria-label", busy ? "Stop generating" : "Send");
  updateSendEnabled();
}
function updateSendEnabled() { el.send.disabled = !state.busy && !el.input.value.trim(); }

async function streamReply(body, view) {
  state.controller = new AbortController();
  setBusy(true);
  let rendered = false;
  const cursor = '<span class="cursor"></span>';
  const paint = () => {
    rendered = false;
    const stick = nearBottom();
    view.answer.innerHTML = renderMarkdown(view.text) + (state.busy ? cursor : "");
    if (stick) scrollToBottom();
  };
  const schedule = () => { if (!rendered) { rendered = true; requestAnimationFrame(paint); } };
  view.answer.innerHTML = cursor;
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
        if (name === "meta") setNotice(view, data);
        else if (name === "reasoning") {
          view.reasoning += data.text;
          view.details.hidden = false;
          view.details.open = true;
          view.summary.textContent = "Thinking";
          view.summary.classList.add("thinking-label");
          view.reasoningBody.textContent = view.reasoning;
          if (nearBottom()) scrollToBottom();
        } else if (name === "answer") {
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
        return;
      }
    }
  } finally {
    setBusy(false);
    state.controller = null;
    view.summary.classList.remove("thinking-label");
    if (view.summary.textContent === "Thinking") view.summary.textContent = "Thought process";
    paint();
  }
  finishAssistant(view, finalMessage || { interrupted: true }, true);
  // The server stores interrupted replies once it notices the closed stream.
  setTimeout(() => syncConversation().catch(() => {}), finalMessage ? 0 : 400);
}

async function syncConversation() {
  if (!state.conversationId) return;
  state.conversation = await (await api(`/api/conversations/${state.conversationId}`)).json();
  if (!state.busy) renderConversation(state.conversation);
  await refreshHistory();
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
  el.empty.hidden = true;
  for (const button of el.messages.querySelectorAll('[aria-label="Regenerate reply"]')) button.remove();
  addUser(text);
  const view = addAssistant();
  scrollToBottom();
  await streamReply({ content: text, settings: requestSettings() }, view);
}

async function regenerate(view) {
  if (state.busy) return;
  const fresh = addAssistant();
  view.node.replaceWith(fresh.node);
  await streamReply({ regenerate: true, settings: requestSettings() }, fresh);
}

el.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy) { state.controller?.abort(); return; }
  const text = el.input.value.trim();
  if (!text) return;
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
  el.input.style.height = `${Math.min(el.input.scrollHeight, 220)}px`;
}
el.input.addEventListener("input", () => { autosize(); updateSendEnabled(); });
for (const button of document.querySelectorAll("#suggestions button")) {
  button.addEventListener("click", () => {
    el.input.value = button.textContent;
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

async function checkStatus() {
  try {
    const status = await (await api("/api/status")).json();
    state.presets = status.presets || state.presets;
    state.defaultSystemPrompt = status.system_prompt ?? state.defaultSystemPrompt;
    el.statusDot.className = "dot " + (status.ready ? "ok" : "bad");
    el.statusText.textContent = status.ready
      ? `${status.model_path || "model"} · ${status.context_length} ctx`
      : status.error || "Model server not ready";
    el.statusText.title = status.identity ? JSON.stringify(status.identity, null, 1) : "";
  } catch (error) {
    el.statusDot.className = "dot bad";
    el.statusText.textContent = "Chat server unreachable";
  }
  renderSettings();
}

loadPrefs();
checkStatus();
setInterval(checkStatus, 30_000);
route();
updateSendEnabled();
