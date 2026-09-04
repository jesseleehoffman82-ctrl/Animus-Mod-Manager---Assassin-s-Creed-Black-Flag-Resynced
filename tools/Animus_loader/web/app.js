const fallbackState = {
  app_version: "",
  game_dir: "",
  game_found: false,
  nexus_metadata_available: true,
  mods: [],
  outfits: [], weapons: [], crew: [], sails: [],
};

const app = {
  state: fallbackState,
  tab: "mods",
  selected: null,
  menuTarget: null,
  bridgeReady: false,
  packBusy: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const hostPending = new Map();
let hostRequestId = 0;

function api() { return window.pywebview?.api; }

if (window.chrome?.webview) {
  window.chrome.webview.addEventListener("message", event => {
    const message = event.data || {};
    if (message.event === "install_progress") {
      const label = message.category === "weapon"
        ? "INSTALLING WEAPON…"
        : message.category === "crew" ? "INSTALLING CREW…"
        : message.category === "sail" ? "INSTALLING SAILS…" : "INSTALLING OUTFIT…";
      const installLabel = $("#install-label");
      if (installLabel) installLabel.textContent = label;
      return;
    }
    const pending = hostPending.get(message.id);
    if (!pending) return;
    hostPending.delete(message.id);
    try {
      (message.logs || []).forEach(addLog);
      if (message.state) window.animusSetState(message.state);
      if (message.error) addLog({ tag: "err", message: message.error });
    } catch (error) {
      console.error("Animus host response failed", error);
      addLog({ tag: "warn", message: "Display refresh issue; installation and deployed files were not affected. " + (error.message || error) });
    } finally {
      // Never leave a toolbar action stuck if display code rejects one row.
      pending.resolve(message.error ? null : (message.result ?? null));
    }
  });
}

function callNativeHost(method, args) {
  return new Promise(resolve => {
    const id = `host-${++hostRequestId}`;
    hostPending.set(id, { resolve });
    window.chrome.webview.postMessage({ id, method, args });
  });
}

async function call(method, ...args) {
  const bridge = api();
  try {
    if (bridge && typeof bridge[method] === "function") return await bridge[method](...args);
    if (window.chrome?.webview) return await callNativeHost(method, args);
    return null;
  }
  catch (error) { addLog({ tag: "err", message: `${method}: ${error}` }); return null; }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

function normalizeReplacementSlot(value) {
  return String(value || "")
    .toLocaleLowerCase()
    .replaceAll("’", "'")
    .replace(/\s*[-–—]\s*(edward|duncan|player|npc|male|female)\s*$/u, "")
    .replace(/\b([a-z0-9]+)'s\b/g, "$1")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function rowTooltip(row) {
  const lines = [row.name || row.id || ""];
  if (row.author) lines.push(`Author: ${row.author}`);
  if (row.version) lines.push(`Version: ${row.version}`);
  if (row.dll_compatibility) lines.push(`DLL: ${row.dll_compatibility.replaceAll("-", " ")}`);
  if (Array.isArray(row.replaces) && row.replaces.length) lines.push(`Replaces: ${row.replaces.join(", ")}`);
  if (row.description) lines.push(row.description);
  if (row.nexus?.url) lines.push(`Nexus: ${row.nexus.url}`);
  return escapeHtml(lines.join("\n"));
}

function currentRows() { return app.state[app.tab] || []; }
function selectedRow() { return currentRows().find(row => (row.name || row.id) === app.selected); }
function isTexturePackRow(row) { return row?.managed_type === "texture-pack"; }
function itemTypeForRow(row) {
  if (isTexturePackRow(row)) return row.pack_category || "general";
  return app.tab === "mods" ? "mod" : packCategory();
}
function isManagerState(value) {
  return Boolean(value && typeof value === "object" &&
    Object.prototype.hasOwnProperty.call(value, "game_found") &&
    Object.prototype.hasOwnProperty.call(value, "game_dir"));
}
function packCategory() {
  return app.tab === "outfits" ? "outfit"
    : app.tab === "weapons" ? "weapon"
    : app.tab === "crew" ? "crew" : "sail";
}
function packLabel() {
  return app.tab === "outfits" ? "OUTFIT PACK"
    : app.tab === "weapons" ? "WEAPON PACK"
    : app.tab === "crew" ? "CREW PACK" : "SAIL PACK";
}

function render() {
  const version = String(app.state.app_version || "").trim();
  $("#app-version").textContent = version
    ? `v${version.replace(/-beta$/i, " BETA")}`
    : "BETA";
  $("#game-path").value = app.state.game_dir || "";
  const status = $("#game-status");
  status.classList.toggle("missing", !app.state.game_found);
  status.querySelector("span").textContent = app.state.game_found ? "GAME FOUND" : "NOT FOUND";
  const proxy = app.state.proxy_status;
  const build = app.state.game_build ? `Steam build ${app.state.game_build}` : "Game build unavailable";
  const executable = app.state.game_executable || "game executable unavailable";
  const proxyText = proxy?.present
    ? `version.dll: ${String(proxy.kind || "unknown").replaceAll("-", " ")}${proxy.hook_present ? " + chained proxy" : ""}`
    : "No version.dll proxy detected";
  status.title = `${build} · ${executable}\n${proxyText}`;
  $("#launch-game-button").disabled = !app.state.game_found;
  $$(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.tab === app.tab));

  const isMods = app.tab === "mods";
  $(".workspace").classList.toggle("pack-mode", !isMods);
  const singular = packLabel();
  const installLabel = $("#install-label");
  const uninstallLabel = $("#uninstall-label");
  if (installLabel) installLabel.textContent = isMods ? "INSTALL MOD" : `INSTALL ${singular}`;
  if (uninstallLabel) uninstallLabel.textContent = isMods ? "UNINSTALL MOD" : "RESTORE VANILLA";
  $("#uninstall-button").disabled = isMods && !selectedRow();
  renderTable();
}

function renderTable() {
  const isMods = app.tab === "mods";
  const isOutfits = app.tab === "outfits";
  const isCrew = app.tab === "crew";
  const isSails = app.tab === "sails";
  const isVanillaReplacement = isOutfits || isCrew || isSails;
  const replacementKind = isSails ? "sail" : isCrew ? "crew texture" : "outfit";
  $("#table-head").innerHTML = isMods
    ? `<tr><th class="col-enabled">ENABLED</th><th>MOD</th><th class="col-version">VERSION</th><th class="col-author">AUTHOR</th><th class="col-targets">TARGETS</th><th class="col-menu"></th></tr>`
    : `<tr><th class="col-enabled">ENABLED</th><th>${isOutfits ? "OUTFIT MOD" : app.tab === "weapons" ? "WEAPON SKIN" : isCrew ? "CREW TEXTURE" : "SAIL DESIGN"}</th><th class="col-author">AUTHOR</th><th class="${isVanillaReplacement ? "col-replaces" : "col-targets"}">${isOutfits ? "REPLACES VANILLA OUTFIT" : isCrew ? "REPLACES VANILLA CREW" : isSails ? "REPLACES VANILLA SAIL" : "TEXTURE SLOTS"}</th><th class="col-menu"></th></tr>`;

  const rows = currentRows();
  const replacementOwners = new Map();
  if (isVanillaReplacement) {
    for (const pack of rows) {
      for (const replacement of Array.isArray(pack.replaces) ? pack.replaces : []) {
        const slot = String(replacement || "").trim();
        if (!slot) continue;
        const normalizedSlot = normalizeReplacementSlot(slot);
        if (!normalizedSlot) continue;
        if (!replacementOwners.has(normalizedSlot)) replacementOwners.set(normalizedSlot, []);
        replacementOwners.get(normalizedSlot).push(String(pack.name || pack.id || `Unnamed ${replacementKind} mod`));
      }
    }
  }
  $("#empty-state").hidden = rows.length > 0;
  $("#empty-state").textContent = `NO ${app.tab.toUpperCase()} INSTALLED`;
  $("#table-body").innerHTML = rows.map(row => {
    const key = row.name || row.id;
    const selected = key === app.selected ? "selected" : "";
    const enabled = row.enabled ? "on" : "";
    const glyph = `<img src="assets/resynced-insignia.png" alt="">`;
    if (isMods) return `<tr class="${selected}" data-key="${escapeHtml(key)}" title="${rowTooltip(row)}">
      <td class="col-enabled"><button class="toggle ${enabled}" data-toggle="${escapeHtml(key)}">${row.enabled ? "✓" : "−"}</button></td>
      <td><span class="mod-name"><span class="mod-glyph">${glyph}</span><span class="mod-title">${escapeHtml(row.name)}</span></span></td>
      <td class="col-version">${escapeHtml(row.version || "—")}</td>
      <td class="col-author">${escapeHtml(row.author || "—")}</td>
      <td class="col-targets">${escapeHtml(row.targets ?? 0)}</td>
      <td class="col-menu"><button class="menu-button" data-menu="${escapeHtml(key)}">•••</button></td>
    </tr>`;
    const replacements = isVanillaReplacement && Array.isArray(row.replaces)
      ? row.replaces.map(value => String(value || "").trim()).filter(Boolean)
      : [];
    const fallbackSharing = isVanillaReplacement
      ? [...new Set(replacements.flatMap(slot => replacementOwners.get(normalizeReplacementSlot(slot)) || []))]
          .filter(name => name !== String(row.name || row.id || ""))
      : [];
    const sharedWith = isVanillaReplacement && Array.isArray(row.shared_with) && row.shared_with.length
      ? row.shared_with
      : fallbackSharing.map(name => {
          const other = rows.find(item => String(item.name || item.id || "") === name);
          return { name, enabled: Boolean(other?.enabled) };
        });
    const sharedLabels = sharedWith.map(item =>
      `${item.name} (${item.enabled ? "Enabled" : "Disabled"})`);
    const replacementText = replacements.length ? replacements.join(", ") : "Unknown";
    const replacementTitle = sharedWith.length
      ? `Shared vanilla ${replacementKind} slot. Also used by:\n${sharedLabels.join("\n")}`
      : replacements.length
        ? `Vanilla ${replacementKind} replaced: ${replacementText}`
        : `Vanilla ${replacementKind} replacement could not be identified`;
    const replacementCell = isVanillaReplacement
      ? `<td class="col-replaces ${sharedWith.length ? "shared-replacement" : ""}" title="${escapeHtml(replacementTitle)}"><span>${escapeHtml(replacementText)}</span>${sharedWith.length ? `<span class="shared-marker" aria-label="Shared ${replacementKind} slot">⇄</span>` : ""}</td>`
      : `<td class="col-targets">${escapeHtml(row.slots ?? 0)}</td>`;
    return `<tr class="${selected}" data-key="${escapeHtml(key)}" title="${rowTooltip(row)}">
      <td class="col-enabled"><button class="toggle ${enabled}" data-toggle="${escapeHtml(key)}" ${app.packBusy ? "disabled" : ""}>${row.enabled ? "✓" : "−"}</button></td>
      <td><span class="mod-name"><span class="mod-glyph">${glyph}</span><span class="mod-title">${escapeHtml(row.name)}</span></span></td>
      <td class="col-author">${escapeHtml(row.author || "—")}</td>
      ${replacementCell}
      <td class="col-menu"><button class="menu-button" data-menu="${escapeHtml(key)}">•••</button></td>
    </tr>`;
  }).join("");
}

function addLog(entry) {
  const log = $("#activity-log");
  const tag = String(entry.tag || "info").toLowerCase();
  const now = new Date().toLocaleTimeString("en-CA", { hour12: false });
  const el = document.createElement("div");
  el.className = `log-entry ${tag}`;
  el.innerHTML = `<span class="time">[${escapeHtml(entry.time || now)}]</span><span class="tag">${escapeHtml(tag)}:</span><span>${escapeHtml(entry.message || "")}</span>`;
  log.append(el);
  log.scrollTop = log.scrollHeight;
}

function normalizeState(state) {
  const normalized = { ...fallbackState, ...(state || {}) };
  normalized.mods = Array.isArray(normalized.mods) ? normalized.mods.map(row => ({
    ...row,
    name: String(row?.name || "Unnamed Mod"),
    version: String(row?.version || ""),
    author: String(row?.author || ""),
    category: String(row?.category || ""),
    targets: Number(row?.targets || 0),
    enabled: Boolean(row?.enabled),
    description: String(row?.description || ""),
    dll_compatibility: row?.dll_compatibility ? String(row.dll_compatibility) : null,
  })) : [];
  for (const category of ["outfits", "weapons", "crew", "sails"]) {
    normalized[category] = Array.isArray(normalized[category]) ? normalized[category].map(row => ({
      ...row,
      name: String(row?.name || "Unnamed Pack"),
      author: String(row?.author || ""),
      slots: Number(row?.slots || 0),
      enabled: Boolean(row?.enabled),
      shared_with: Array.isArray(row?.shared_with) ? row.shared_with.map(item => ({
        id: String(item?.id || ""),
        name: String(item?.name || "Unnamed Outfit Mod"),
        enabled: Boolean(item?.enabled),
      })) : [],
    })) : [];
  }
  return normalized;
}

window.animusLog = addLog;
window.animusSetState = state => {
  app.state = normalizeState(state);
  try {
    render();
  } catch (error) {
    console.error("Animus render failed", error);
    addLog({ tag: "warn", message: "Display refresh issue; installation and deployed files were not affected. " + (error.message || error) });
    // The table is the critical surface; attempt it independently so a
    // failure in unrelated header/status rendering cannot hide installed mods.
    renderTable();
  }
};

async function refresh() {
  const state = await call("get_state");
  if (state) window.animusSetState(state);
  else render();
}

function setTab(tab) {
  app.tab = tab; app.selected = null; hideMenu(); render();
}

async function toggleRow(key) {
  const row = currentRows().find(item => (item.name || item.id) === key);
  if (!row) return;
  if (app.tab === "mods" && !isTexturePackRow(row)) await call("toggle_mod", row.id || row.name);
  else {
    if (app.packBusy) return;
    const previousEnabled = row.enabled;
    const requestedEnabled = !previousEnabled;
    // Reflect the user's choice immediately. Rebuilding the FORGE can take a
    // moment, but the interface should never feel as though the click failed.
    row.enabled = requestedEnabled;
    app.packBusy = true;
    render();
    try {
      const state = await call("toggle_pack", itemTypeForRow(row), row.id, requestedEnabled);
      if (isManagerState(state)) window.animusSetState(state);
      else {
        row.enabled = previousEnabled;
        await refresh();
      }
    } finally {
      app.packBusy = false;
      render();
    }
  }
}

function showMenu(button, key) {
  app.menuTarget = key;
  const row = currentRows().find(item => (item.name || item.id) === key);
  const menu = $("#context-menu");
  const itemLabel = isTexturePackRow(row) ? "Texture Mod" : app.tab === "mods" ? "Mod" : app.tab === "outfits" ? "Outfit" : app.tab === "weapons" ? "Weapon" : app.tab === "crew" ? "Crew Pack" : "Sail Pack";
  $("#update-menu-action span").textContent = `Update ${itemLabel}`;
  $("#open-menu-action span").textContent = `Open ${itemLabel} Folder`;
  $("#uninstall-menu-action span").textContent = `Uninstall ${itemLabel}`;
  $("#nexus-menu-action span").textContent = row?.nexus?.url ? "Visit on Nexus" : "Link Nexus Page";
  menu.hidden = false;
  const rect = button.getBoundingClientRect();
  const width = 225, height = menu.offsetHeight;
  menu.style.left = `${Math.min(rect.right - width, innerWidth - width - 14)}px`;
  menu.style.top = `${Math.min(rect.bottom + 5, innerHeight - height - 14)}px`;
}
function hideMenu() { $("#context-menu").hidden = true; app.menuTarget = null; }

async function showDetails(name) {
  const row = currentRows().find(item => (item.name || item.id) === name);
  const data = await call(app.tab === "mods" && !isTexturePackRow(row) ? "get_mod_details" : "get_pack_details", row?.id || name)
    || row;
  if (!data) return;
  const targets = Array.isArray(data.targets) ? data.targets : [];
  const replaces = Array.isArray(data.replaces) && data.replaces.length ? data.replaces.join(", ") : "—";
  const nexus = data.nexus?.url
    ? `<a class="nexus-link" href="${escapeHtml(data.nexus.url)}" target="_blank" rel="noopener">Visit on Nexus ↗</a>`
    : "Not linked";
  const compatibility = data.dll_compatibility
    ? escapeHtml(data.dll_compatibility.replaceAll("-", " "))
    : "Not required";
  $("#details-content").innerHTML = `<dl class="details-grid">
    <dt>Name</dt><dd>${escapeHtml(data.name)}</dd><dt>Version</dt><dd>${escapeHtml(data.version || "—")}</dd>
    <dt>Author</dt><dd>${escapeHtml(data.author || "—")}</dd><dt>Category</dt><dd>${escapeHtml(data.category || "—")}</dd>
    <dt>Replaces</dt><dd>${escapeHtml(replaces)}</dd><dt>Texture slots</dt><dd>${escapeHtml(data.slots ?? data.targets?.length ?? "—")}</dd>
    <dt>Nexus</dt><dd>${nexus}</dd>
    <dt>DLL compatibility</dt><dd>${compatibility}</dd>
    <dt>Description</dt><dd>${escapeHtml(data.description || "—")}</dd>
    <dt>Package</dt><dd>${escapeHtml(data.path || "—")}</dd></dl>
    <ul class="target-list">${targets.map(t => `<li>${escapeHtml(t.forge)} · ${escapeHtml(t.resource_id)} · ${escapeHtml(t.mode)}</li>`).join("")}</ul>`;
  $("#details-dialog").showModal();
}

function requestRename(currentName) {
  const dialog = $("#rename-dialog");
  const form = $("#rename-form");
  const input = $("#rename-input");
  const error = $("#rename-error");
  input.value = currentName || "";
  error.textContent = "";
  dialog.returnValue = "";
  for (const property of ["position", "left", "top", "right", "bottom", "margin"])
    dialog.style.removeProperty(property);

  return new Promise(resolve => {
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    form.onsubmit = event => {
      event.preventDefault();
      const value = input.value.trim();
      if (!value) {
        error.textContent = "Enter a name before saving.";
        input.focus();
        return;
      }
      dialog.close("save");
    };
    $("#rename-cancel").onclick = () => dialog.close("cancel");
    $("#rename-close").onclick = () => dialog.close("cancel");
    dialog.oncancel = event => {
      event.preventDefault();
      dialog.close("cancel");
    };
    dialog.onclose = () => finish(dialog.returnValue === "save" ? input.value.trim() : null);
    dialog.showModal();
    requestAnimationFrame(() => { input.focus(); input.select(); });
  });
}

function makeDialogDraggable(dialog, handle) {
  handle.addEventListener("pointerdown", event => {
    if (event.button !== 0 || event.target.closest("button")) return;
    const rect = dialog.getBoundingClientRect();
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;
    dialog.style.position = "fixed";
    dialog.style.margin = "0";
    dialog.style.right = "auto";
    dialog.style.bottom = "auto";
    dialog.style.left = `${rect.left}px`;
    dialog.style.top = `${rect.top}px`;
    handle.setPointerCapture(event.pointerId);

    const move = moveEvent => {
      const maxLeft = Math.max(0, innerWidth - dialog.offsetWidth);
      const maxTop = Math.max(0, innerHeight - dialog.offsetHeight);
      dialog.style.left = `${Math.max(0, Math.min(moveEvent.clientX - offsetX, maxLeft))}px`;
      dialog.style.top = `${Math.max(0, Math.min(moveEvent.clientY - offsetY, maxTop))}px`;
    };
    const stop = stopEvent => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      handle.removeEventListener("pointercancel", stop);
      if (handle.hasPointerCapture(stopEvent.pointerId)) handle.releasePointerCapture(stopEvent.pointerId);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  });
}

makeDialogDraggable($("#rename-dialog"), $("#rename-dialog .dialog-head"));

document.addEventListener("click", async event => {
  const tab = event.target.closest("[data-tab]"); if (tab) return setTab(tab.dataset.tab);
  const row = event.target.closest("tr[data-key]"); if (row && !event.target.closest("button")) { app.selected = row.dataset.key; render(); return; }
  const toggle = event.target.closest("[data-toggle]"); if (toggle) return toggleRow(toggle.dataset.toggle);
  const menu = event.target.closest("[data-menu]"); if (menu) { event.stopPropagation(); return showMenu(menu, menu.dataset.menu); }
  if (!event.target.closest("#context-menu")) hideMenu();
});

$("#browse-button").onclick = async event => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "SELECTING…";
  try {
    const state = await call("browse_game_dir");
    if (state) window.animusSetState(state);
  } finally {
    button.disabled = false;
    button.textContent = "BROWSE";
  }
};
$("#detect-button").onclick = async () => { const state = await call("detect_game_dir"); if (state) window.animusSetState(state); };
$("#refresh-button").onclick = refresh;
$("#nexus-page-button").onclick = () => call("open_nexus_page");
$("#launch-game-button").onclick = async event => {
  const button = event.currentTarget;
  const label = $("#launch-game-label");
  button.disabled = true;
  label.textContent = "LAUNCHING…";
  try {
    await call("launch_game");
  } finally {
    label.textContent = "LAUNCH GAME";
    button.disabled = !app.state.game_found;
  }
};
$("#install-button").onclick = async event => {
  const button = event.currentTarget;
  const label = $("#install-label");
  const original = label?.textContent || "INSTALL";
  button.disabled = true;
  if (label) label.textContent = "SELECTING…";
  try {
    if (app.tab === "mods") {
      const result = await call("install_mod");
      // Always ask for a fresh library after the native file dialog and
      // installer complete. This avoids a stale table if a host state push is
      // delayed or was delivered while the dialog still owned the window.
      await refresh();
      if (result?.name) app.selected = result.name;
      render();
    } else {
      await call("install_pack", packCategory());
      await refresh();
    }
  } finally {
    button.disabled = false;
    if (label) label.textContent = original;
    render();
  }
};
$("#uninstall-button").onclick = async () => {
  if (app.tab !== "mods") {
    await call("revert_all");
    app.selected = null;
    await refresh();
    return;
  }
  const row = selectedRow();
  if (!row) return;
  if (isTexturePackRow(row)) await call("remove_pack", row.id);
  else await call("uninstall_mod", row.name);
  app.selected = null;
  await refresh();
};
$("#clear-log-button").onclick = () => { $("#activity-log").innerHTML = ""; };
$("#dialog-close").onclick = () => $("#details-dialog").close();

$("#context-menu").onclick = async event => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  const name = app.menuTarget; hideMenu(); if (!action || !name) return;
  if (action === "update") {
    const row = currentRows().find(item => (item.name || item.id) === name);
    const itemType = itemTypeForRow(row);
    const itemId = row?.id || name;
    if (itemId) await call("update_item", itemType, itemId);
    await refresh();
  }
  if (action === "rename") {
    const row = currentRows().find(item => (item.name || item.id) === name);
    const value = await requestRename(row?.name || name);
    const newName = value?.trim();
    if (row && newName && newName !== row.name) {
      const itemType = itemTypeForRow(row);
      const state = await call("rename_item", itemType, row.id || row.name, newName);
      if (state?.game_dir) window.animusSetState(state);
      app.selected = newName;
      await refresh();
    }
  }
  if (action === "uninstall") {
    const row = currentRows().find(item => (item.name || item.id) === name);
    if (app.tab === "mods" && !isTexturePackRow(row)) {
      await call("uninstall_mod", row?.id || name);
    } else {
      if (row) await call("remove_pack", row.id);
    }
    app.selected = null;
    await refresh();
  }
  if (action === "open") {
    const row = currentRows().find(item => (item.name || item.id) === name);
    if (app.tab === "mods" && !isTexturePackRow(row)) {
      await call("open_mod_folder", row?.id || name);
    }
    else {
      if (row) await call("open_pack_folder", row.id);
    }
  }
  if (action === "nexus") {
    const row = currentRows().find(item => (item.name || item.id) === name);
    if (row?.nexus?.url) {
      window.open(row.nexus.url, "_blank", "noopener");
    } else {
      const value = window.prompt("Paste the Nexus mod page URL:", "https://www.nexusmods.com/assassinscreedblackflagresynced/mods/");
      if (value) {
        try {
          const url = new URL(value.trim());
          const match = url.pathname.match(/^\/assassinscreedblackflagresynced\/mods\/(\d+)/i);
          if (!url.hostname.endsWith("nexusmods.com") || !match) throw new Error("not a Black Flag Resynced mod URL");
          const state = await call("set_nexus_link", itemTypeForRow(row), row?.id || name, Number(match[1]));
          if (state) window.animusSetState(state);
        } catch (error) {
          addLog({ tag: "err", message: `Invalid Nexus page: ${error.message}` });
        }
      }
    }
  }
  if (action === "details") await showDetails(name);
};

$$("[data-window]").forEach(button => button.onclick = () => call({ minimize: "win_minimize", maximize: "win_toggle_maximize", close: "win_close" }[button.dataset.window]));

function windowResizeEdge(event) {
  const edge = 9;
  const left = event.clientX <= edge;
  const right = event.clientX >= innerWidth - edge;
  const top = event.clientY <= edge;
  const bottom = event.clientY >= innerHeight - edge;
  if (top && left) return "top_left";
  if (top && right) return "top_right";
  if (bottom && left) return "bottom_left";
  if (bottom && right) return "bottom_right";
  if (left) return "left";
  if (right) return "right";
  if (top) return "top";
  if (bottom) return "bottom";
  return "";
}

document.addEventListener("pointermove", event => {
  if (!window.chrome?.webview) return;
  const cursors = {
    left: "ew-resize", right: "ew-resize", top: "ns-resize", bottom: "ns-resize",
    top_left: "nwse-resize", bottom_right: "nwse-resize",
    top_right: "nesw-resize", bottom_left: "nesw-resize",
  };
  document.body.style.cursor = cursors[windowResizeEdge(event)] || "";
});

document.addEventListener("pointerdown", event => {
  if (event.button !== 0 || !window.chrome?.webview) return;
  const edge = windowResizeEdge(event);
  if (!edge) return;
  event.preventDefault();
  event.stopPropagation();
  call(`win_resize_${edge}`);
}, true);

$(".titlebar").addEventListener("pointerdown", event => {
  if (event.button === 0 && !event.target.closest("button") && window.chrome?.webview) call("win_drag");
});

window.addEventListener("pywebviewready", async () => {
  app.bridgeReady = true;
  await refresh();
  addLog({ tag: "info", message: "Animus Mod & Outfit Manager started" });
});

render();
if (window.chrome?.webview) {
  app.bridgeReady = true;
  refresh().then(() => addLog({ tag: "info", message: "Animus Mod & Outfit Manager started" }));
} else if (!window.pywebview) {
  addLog({ tag: "info", message: "UI preview mode — backend bridge is not connected" });
}
