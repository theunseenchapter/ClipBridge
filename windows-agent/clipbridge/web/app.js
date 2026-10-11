const api = "/api";
const $ = (id) => document.getElementById(id);
let historyQuery = "";

async function request(path, options) {
  const response = await fetch(api + path, {
    headers: {"Content-Type": "application/json"},
    ...options,
  });
  if (!response.ok) throw new Error(`ClipBridge request failed (${response.status})`);
  return response.json();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, {hour: "numeric", minute: "2-digit", month: "short", day: "numeric"})
    .format(new Date(timestamp * 1000));
}

function renderState(state) {
  const connected = state.connected > 0;
  $("heroTitle").textContent = connected ? state.devices.find((d) => d.connected)?.name || "Phone connected" : "No phone connected";
  $("heroText").textContent = connected ? "Clipboard sync is active." : "Connect your Android phone to sync your clipboard.";
  $("statusPill").className = `statusText ${connected ? "connected" : "waiting"}`;
  $("statusPill").innerHTML = `<span></span><strong>${connected ? "Connected" : "Waiting for phone"}</strong>`;
  $("pause").textContent = state.paused ? "Resume sync" : "Pause sync";
  $("count").textContent = `${state.devices.length} ${state.devices.length === 1 ? "device" : "devices"}`;
  $("devices").innerHTML = state.devices.length ? state.devices.map((device) => `
    <div class="device">
      <div><div class="deviceName">${escapeHtml(device.name)}</div><div class="deviceMeta">${device.connected ? "Connected now" : "Not connected"}</div></div>
      <button class="disconnect" data-device="${escapeHtml(device.id)}">Disconnect</button>
    </div>`).join("") : '<p class="empty">No paired phones.</p>';
  document.querySelectorAll("[data-device]").forEach((button) => {
    button.onclick = () => action("/disconnect", {device_id: button.dataset.device});
  });
}

function renderHistory(items) {
  $("history").innerHTML = items.length ? items.map((item) => `
    <article class="historyRow">
      <div>
        <div class="historyPreview">${escapeHtml(item.text)}</div>
        <div class="historyMeta">${escapeHtml(item.source)} · ${formatTime(item.created)}${item.pinned ? " · Pinned" : ""}</div>
      </div>
      <div class="rowActions">
        <button class="rowButton" title="Copy to clipboard" data-action="restore" data-item="${escapeHtml(item.id)}">Copy</button>
        <button class="rowButton" title="${item.pinned ? "Unpin" : "Pin"}" data-action="pin" data-item="${escapeHtml(item.id)}">${item.pinned ? "Unpin" : "Pin"}</button>
        <button class="rowButton" title="Delete item" data-action="delete" data-item="${escapeHtml(item.id)}">Delete</button>
      </div>
    </article>`).join("") : '<p class="empty">No clipboard activity yet.</p>';
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.onclick = () => action(`/${button.dataset.action}`, {item_id: button.dataset.item});
  });
}

async function refresh() {
  try {
    const [state, history] = await Promise.all([
      request("/state"),
      request(`/history?q=${encodeURIComponent(historyQuery)}`),
    ]);
    renderState(state);
    renderHistory(history.items);
    $("error").classList.add("hidden");
  } catch (error) {
    $("error").textContent = error.message;
    $("error").classList.remove("hidden");
  }
}

async function action(path, body) {
  try { await request(path, {method: "POST", body: JSON.stringify(body || {})}); await refresh(); }
  catch (error) { $("error").textContent = error.message; $("error").classList.remove("hidden"); }
}

$("pair").onclick = () => action("/pair");
$("pause").onclick = () => action("/pause");
$("settings").onclick = () => action("/history");
$("viewAll").onclick = (event) => {
  event.preventDefault();
  historyQuery = "";
  $("search").value = "";
  refresh();
};
$("search").oninput = (event) => { historyQuery = event.target.value; refresh(); };
refresh();
setInterval(refresh, 1500);
