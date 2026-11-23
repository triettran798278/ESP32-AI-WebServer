const byId = (id) => document.getElementById(id);
const statusNames = { connected: "Connected", unreachable: "Unreachable", connecting: "Connecting", paused: "Paused" };
const clock = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
let devices = [];
let selected = "";
let busy = false;
let draft = {};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function notify(text, error = false) {
  const notice = byId("notice");
  notice.textContent = text;
  notice.classList.toggle("error", error);
  notice.hidden = !text;
}

function renderNav() {
  const query = byId("search").value.trim().toLowerCase();
  const nav = byId("devices");
  const fragment = document.createDocumentFragment();
  let group;
  for (const device of devices) {
    if (!(device.label + device.name).toLowerCase().includes(query)) continue;
    if (device.group !== group) {
      group = device.group;
      fragment.append(element("p", group, "nav-group"));
    }
    const button = element("button", undefined, "nav-device " + device.status);
    button.type = "button";
    button.dataset.device = device.name;
    button.setAttribute("aria-current", String(device.name === selected));
    button.append(element("span", "", "dot"), element("span", device.name));
    button.addEventListener("click", () => {
      if (selected === device.name) return;
      selected = device.name;
      draft = {};
      notify("");
      renderNav();
      renderDetail();
    });
    fragment.append(button);
  }
  if (!fragment.childNodes.length) fragment.append(element("p", "No matching devices", "nav-group"));
  const focused = document.activeElement?.dataset.device;
  nav.replaceChildren(fragment);
  if (focused) [...nav.querySelectorAll("button")].find((button) => button.dataset.device === focused)?.focus();
  byId("count").textContent = devices.length;
}

function renderActivity(device) {
  const rows = device.events.map((event) => {
    const row = element("li");
    const head = element("div", undefined, "event-head");
    head.append(element("span", event.kind), element("time", clock.format(event.time * 1000)));
    row.append(head, element("div", event.detail, "event-detail"));
    return row;
  });
  byId("activity").replaceChildren(...(rows.length ? rows : [element("li", "No activity yet", "muted")]));
}

function renderConnection(device) {
  const status = byId("status");
  status.className = device.status;
  status.replaceChildren(element("span", "", "dot"), document.createTextNode(statusNames[device.status]));
  byId("last-sent").textContent = device.lastSent ? clock.format(device.lastSent * 1000) : "Pending";
  byId("pause").textContent = device.enabled ? "Pause device" : "Resume device";
  byId("pause").disabled = busy;
  byId("telemetry").querySelector("button").disabled = busy || !device.enabled;
  renderActivity(device);
}

function preview(device) {
  const payload = { ...device.values, ...draft };
  if (payload.autoLightEnabled) payload.lightOn = payload.motionDetected;
  byId("payload").textContent = JSON.stringify(payload, null, 2);
}

function renderFields(device, preserveSensors = false) {
  const actuators = [];
  const sensors = [];
  for (const [key, field] of Object.entries(device.fields)) {
    if (field.method) {
      const row = element("div", undefined, "field");
      const value = device.values[key];
      const label = key === "locked" ? (value ? "Locked" : "Unlocked") : (value ? "On" : "Off");
      const button = element("button", label, "button toggle");
      button.type = "button";
      button.setAttribute("aria-pressed", String(value));
      button.setAttribute("aria-label", field.label);
      button.disabled = busy || !device.enabled || (key === "lightOn" && device.values.autoLightEnabled === true);
      button.addEventListener("click", () => send({ values: { [key]: !value } }, false));
      row.append(element("span", field.label), button);
      actuators.push(row);
      continue;
    }
    if (preserveSensors) continue;
    const label = element("label", undefined, "field");
    const input = element("input");
    const value = draft[key] ?? device.values[key];
    const control = element("span", undefined, "field-value");
    input.disabled = busy || !device.enabled;
    if (typeof field.default === "boolean") {
      input.type = "checkbox";
      input.checked = value;
    } else {
      input.type = "number";
      input.required = true;
      input.min = field.min;
      input.max = field.max;
      input.step = "any";
      input.value = value;
    }
    input.addEventListener("input", () => {
      draft[key] = input.type === "checkbox" ? input.checked : (input.value === "" ? null : input.valueAsNumber);
      preview(device);
    });
    control.append(input);
    if (field.unit) control.append(element("span", field.unit, "unit"));
    label.append(element("span", field.label), control);
    sensors.push(label);
  }
  byId("actuator-panel").hidden = !actuators.length;
  byId("actuators").replaceChildren(...actuators);
  if (!preserveSensors) byId("sensors").replaceChildren(...sensors);
}

function renderDetail() {
  const device = devices.find((entry) => entry.name === selected);
  if (!device) return;
  byId("detail").hidden = false;
  byId("loading").hidden = true;
  byId("title").textContent = device.label;
  byId("group").textContent = device.group;
  byId("device-id").textContent = device.name;
  renderConnection(device);
  renderFields(device);
  preview(device);
}

async function refresh() {
  try {
    const response = await fetch("/api/devices", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load devices");
    const updated = await response.json();
    if (busy) return;
    const previous = devices.find((entry) => entry.name === selected);
    const navChanged = JSON.stringify(devices.map((d) => [d.name, d.status])) !== JSON.stringify(updated.map((d) => [d.name, d.status]));
    devices = updated;
    if (!devices.some((entry) => entry.name === selected)) {
      selected = devices[0]?.name || "";
      draft = {};
    }
    if (navChanged) renderNav();
    const device = devices.find((entry) => entry.name === selected);
    if (!device) return;
    if (!previous || previous.enabled !== device.enabled ||
        JSON.stringify(previous.values) !== JSON.stringify(device.values)) {
      if (byId("sensors").contains(document.activeElement)) {
        renderConnection(device);
        renderFields(device, true);
        preview(device);
        return;
      }
      renderDetail();
    } else {
      renderConnection(device);
    }
  } catch {
    notify("Could not reach the device workbench. Retrying…", true);
  }
}

async function send(update, clearDraft) {
  if (busy) return;
  busy = true;
  const name = selected;
  renderDetail();
  try {
    const response = await fetch("/api/devices/" + encodeURIComponent(name), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Invalid device update");
    devices = devices.map((device) => device.name === name ? result.device : device);
    if (name === selected) {
      if (clearDraft) draft = {};
      if (update.enabled === false) notify("Device paused");
      else if (result.accepted) notify("Telemetry accepted by ThingsBoard");
      else notify("State saved locally. ThingsBoard did not accept telemetry yet.", true);
    }
  } catch (error) {
    if (name === selected) notify(error.message, true);
  } finally {
    busy = false;
    renderNav();
    renderDetail();
  }
}

byId("search").addEventListener("input", renderNav);
byId("pause").addEventListener("click", () => send({ enabled: !devices.find((device) => device.name === selected).enabled }, false));
byId("telemetry").addEventListener("submit", (event) => {
  event.preventDefault();
  send({ values: draft }, true);
});
await refresh();
setInterval(refresh, 3000);
