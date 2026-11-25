/*
 * JaeDrive for Home Assistant: custom cards and a dashboard strategy.
 *
 * Served by the integration itself (see __init__.py), so it updates together with it and
 * nothing has to be installed or pasted:
 *   - Settings > Dashboards > Add dashboard > "JaeDrive" creates a dashboard that builds itself
 *     from the JaeDrive entities (one view per car).
 *   - The cards ("JaeDrive ...") are in the card picker of any dashboard.
 *
 * Entities are found through the entity registry (platform "jaedrive", grouped by device), not by
 * entity_id, so renamed entities and second cars keep working.
 */

const ASSET_QUERY = new URL(import.meta.url).search;
const asset = (name) => new URL(name, import.meta.url).pathname + ASSET_QUERY;
const DOCS = "https://github.com/Phabryc/jaedrive-ha";
const ACCENT = "#03a3ee";

// ---------------------------------------------------------------- strings

const STRINGS = {
  en: {
    car: "Car",
    updated: "Updated",
    never: "no data yet",
    battery: "Battery",
    fuel: "Fuel",
    range: "range",
    ev_range: "Electric range",
    odometer: "Odometer",
    service: "Service",
    service_in: "in",
    subscription_problem: "JaeDrive cloud subscription not active: data is not updated.",
    last_trip: "Last trip",
    ended: "ended",
    distance: "Distance",
    duration: "Duration",
    avg_speed: "Avg speed",
    consumption: "Consumption",
    fuel_used: "Fuel used",
    electric: "Electric",
    hybrid: "Hybrid",
    energy: "Energy",
    electric_consumption: "kWh/100 km",
    battery_trip: "Battery",
    peak_power: "Peak power",
    peak_regen: "Peak regen",
    recovered: "Recovered",
    no_trip: "No trip recorded yet.",
    trips: "Trip A / B",
    not_running: "Not running",
    since: "since",
    last_30d: "Last 30 days",
    trip_count: "Trips",
    ev_share: "Electric share",
    parking: "Parking",
    parked: "Parked",
    no_location: "Parking location not shared with Home Assistant.",
    no_car: "No JaeDrive car found. Add the JaeDrive integration first.",
    km_per_day: "Distance per day",
    pick_car: "Car (empty = first one)",
    unknown_place: "Unknown place",
  },
  it: {
    car: "Auto",
    updated: "Aggiornata",
    never: "ancora nessun dato",
    battery: "Batteria",
    fuel: "Carburante",
    range: "di autonomia",
    ev_range: "Autonomia elettrica",
    odometer: "Contachilometri",
    service: "Tagliando",
    service_in: "tra",
    subscription_problem: "Abbonamento cloud JaeDrive non attivo: i dati non si aggiornano.",
    last_trip: "Ultimo viaggio",
    ended: "finito",
    distance: "Distanza",
    duration: "Durata",
    avg_speed: "Vel. media",
    consumption: "Consumo",
    fuel_used: "Carburante",
    electric: "Elettrico",
    hybrid: "Ibrido",
    energy: "Energia",
    electric_consumption: "kWh/100 km",
    battery_trip: "Batteria",
    peak_power: "Potenza max",
    peak_regen: "Ricarica max",
    recovered: "Recuperata",
    no_trip: "Ancora nessun viaggio.",
    trips: "Trip A / B",
    not_running: "Non attivo",
    since: "dal",
    last_30d: "Ultimi 30 giorni",
    trip_count: "Viaggi",
    ev_share: "Quota elettrica",
    parking: "Parcheggio",
    parked: "Parcheggiata",
    no_location: "Posizione del parcheggio non condivisa con Home Assistant.",
    no_car: "Nessuna auto JaeDrive trovata. Aggiungi prima l'integrazione JaeDrive.",
    km_per_day: "Distanza al giorno",
    pick_car: "Auto (vuoto = la prima)",
    unknown_place: "Luogo sconosciuto",
  },
};

const lang = (hass) => (hass?.locale?.language || hass?.language || "en").split("-")[0];
const t = (hass, key) => (STRINGS[lang(hass)] || STRINGS.en)[key] ?? STRINGS.en[key] ?? key;

// ---------------------------------------------------------------- entities

function entityKey(hass, entry) {
  if (entry.translation_key) return entry.translation_key;
  // The traction battery uses the device-class name, so it has no translation key.
  const st = hass.states[entry.entity_id];
  if (entry.entity_id.startsWith("sensor.") && st?.attributes?.device_class === "battery") return "battery";
  return null;
}

/** JaeDrive devices: cars (they have an odometer) plus the account device(s). */
function jaedriveDevices(hass) {
  const byDevice = new Map();
  for (const entry of Object.values(hass?.entities || {})) {
    if (entry.platform !== "jaedrive" || !entry.device_id) continue;
    const key = entityKey(hass, entry);
    if (!key) continue;
    if (!byDevice.has(entry.device_id)) byDevice.set(entry.device_id, {});
    byDevice.get(entry.device_id)[key] = entry.entity_id;
  }
  const cars = [];
  const account = {};
  for (const [deviceId, entities] of byDevice) {
    if (!entities.odometer) {
      Object.assign(account, entities);
      continue;
    }
    const dev = hass.devices?.[deviceId] || {};
    cars.push({ deviceId, entities, name: dev.name_by_user || dev.name || "JaeDrive", model: dev.model || "" });
  }
  cars.sort((a, b) => a.name.localeCompare(b.name));
  return { cars, account };
}

function findCar(hass, deviceId) {
  const { cars, account } = jaedriveDevices(hass);
  const car = (deviceId && cars.find((c) => c.deviceId === deviceId)) || cars[0];
  return car ? { ...car, account } : null;
}

const stateObj = (hass, id) => {
  const s = id && hass.states[id];
  return s && s.state !== "unknown" && s.state !== "unavailable" ? s : null;
};

// Unit of an entity, e.g. "kWh/100 km" or "kWh/100 mi" from the units of the JaeDrive profile.
const unitOf = (hass, id) => (id && hass.states[id]?.attributes?.unit_of_measurement) || "";

const num = (hass, id) => {
  const n = parseFloat(stateObj(hass, id)?.state);
  return Number.isFinite(n) ? n : null;
};

/** Localized value and unit, as Home Assistant shows them. */
function parts(hass, id) {
  const s = stateObj(hass, id);
  if (!s) return null;
  if (hass.formatEntityStateToParts) {
    const p = hass.formatEntityStateToParts(s);
    const unit = p.filter((x) => x.type === "unit").map((x) => x.value).join("").trim();
    const value = p.filter((x) => x.type !== "unit").map((x) => x.value).join("").trim();
    return { value, unit };
  }
  const unit = s.attributes.unit_of_measurement || "";
  const full = hass.formatEntityState ? hass.formatEntityState(s) : `${s.state} ${unit}`;
  return { value: unit ? full.replace(unit, "").trim() : full, unit };
}

const text = (hass, id) => {
  const p = parts(hass, id);
  return p ? `${p.value}${p.unit ? ` ${p.unit}` : ""}` : null;
};

function relative(hass, iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || isNaN(d)) return null;
  const sec = (d.getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(lang(hass), { numeric: "auto" });
  const abs = Math.abs(sec);
  if (abs < 60) return rtf.format(Math.round(sec), "second");
  if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(sec / 86400), "day");
  return d.toLocaleDateString(lang(hass), { day: "numeric", month: "short", year: "numeric" });
}

function shortDate(hass, iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || isNaN(d)) return null;
  return d.toLocaleString(lang(hass), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// ---------------------------------------------------------------- shared styles

const STYLES = `
  :host { --jd-accent: ${ACCENT}; --jd-ev: #2fb36d; --jd-hev: #f0a030; display: block; }
  ha-card { padding: 16px; overflow: hidden; height: 100%; box-sizing: border-box; }
  .head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .head img { width: 40px; height: 40px; border-radius: 10px; flex: none; }
  .head .icon { width: 40px; height: 40px; border-radius: 10px; flex: none; display: grid; place-items: center;
    background: color-mix(in srgb, var(--jd-accent) 14%, transparent); color: var(--jd-accent); }
  .head .titles { flex: 1; min-width: 0; }
  .head .title { font-size: 1.15em; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .head .sub { color: var(--secondary-text-color); font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .head .right { color: var(--secondary-text-color); font-size: 0.8em; text-align: right; }
  .click { cursor: pointer; }
  .click:hover { opacity: 0.8; }
  .label { color: var(--secondary-text-color); font-size: 0.8em; }
  .value { font-size: 1.35em; font-weight: 600; line-height: 1.2; }
  .value small { font-size: 0.6em; font-weight: 500; color: var(--secondary-text-color); margin-left: 2px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(92px, 1fr)); gap: 12px 10px; }
  .stat { min-width: 0; }
  .stat .value { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .divider { height: 1px; background: var(--divider-color); margin: 14px 0; }
  .bar { height: 8px; border-radius: 4px; background: var(--divider-color); overflow: hidden; display: flex; }
  .bar > span { display: block; height: 100%; }
  .split { display: flex; justify-content: space-between; font-size: 0.8em; margin-top: 4px; color: var(--secondary-text-color); }
  .muted { color: var(--secondary-text-color); }
  .warn { display: flex; gap: 8px; align-items: center; margin-top: 14px; padding: 8px 10px; border-radius: 8px;
    color: var(--error-color); background: color-mix(in srgb, var(--error-color) 12%, transparent); font-size: 0.85em; }
`;

function head(hass, { title, sub, right, icon }) {
  const logo = icon
    ? `<div class="icon"><ha-icon icon="${icon}"></ha-icon></div>`
    : `<img src="${asset("icon.png")}" alt="JaeDrive">`;
  return `<div class="head">${logo}<div class="titles"><div class="title">${esc(title)}</div>${
    sub ? `<div class="sub">${esc(sub)}</div>` : ""
  }</div>${right ? `<div class="right">${right}</div>` : ""}</div>`;
}

function stat(hass, id, label, { unit = true } = {}) {
  const p = parts(hass, id);
  if (!p) return "";
  if (!unit) p.unit = "";
  return `<div class="stat click" data-entity="${id}"><div class="label">${esc(label)}</div><div class="value">${esc(
    p.value,
  )}${p.unit ? `<small>${esc(p.unit)}</small>` : ""}</div></div>`;
}

function evBar(hass, pct) {
  if (pct == null) return "";
  const ev = Math.max(0, Math.min(100, pct));
  return `<div class="bar"><span style="width:${ev}%;background:var(--jd-ev)"></span><span style="width:${
    100 - ev
  }%;background:var(--jd-hev)"></span></div><div class="split"><span>${t(hass, "electric")} ${Math.round(
    ev,
  )}%</span><span>${t(hass, "hybrid")} ${Math.round(100 - ev)}%</span></div>`;
}

// ---------------------------------------------------------------- base card

class JaeDriveCard extends HTMLElement {
  static getConfigForm() {
    return {
      // Every car has the trip event; the account device has not.
      schema: [{ name: "device_id", selector: { device: { entity: [{ integration: "jaedrive", domain: "event" }] } } }],
      computeLabel: () => t(document.querySelector("home-assistant")?.hass, "pick_car"),
    };
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._sig = null;
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    // Relative times ("5 minutes ago") need a refresh even without state changes.
    this._timer = setInterval(() => {
      this._sig = null;
      this._update();
    }, 60000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _update() {
    if (!this._hass || !this._config) return;
    const car = findCar(this._hass, this._config.device_id);
    const ids = car ? (this.watched?.(car) ?? [...Object.values(car.entities), ...Object.values(car.account)]) : [];
    const sig =
      lang(this._hass) +
      (this._hass.themes?.darkMode ? "d" : "l") +
      ids.map((id) => this._hass.states[id]?.last_updated || "").join("|") +
      (car?.name || "");
    if (sig === this._sig) return;
    this._sig = sig;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => {
        const el = ev.composedPath().find((n) => n.dataset?.entity);
        if (!el) return;
        this.dispatchEvent(
          new CustomEvent("hass-more-info", { detail: { entityId: el.dataset.entity }, bubbles: true, composed: true }),
        );
      });
    }
    const body = car ? this.renderCar(this._hass, car) : `<div class="muted">${t(this._hass, "no_car")}</div>`;
    this.shadowRoot.innerHTML = `<style>${STYLES}${this.constructor.styles || ""}</style><ha-card>${body}</ha-card>`;
    this.afterRender?.(this._hass, car);
  }
}

// ---------------------------------------------------------------- car card

class JaeDriveCarCard extends JaeDriveCard {
  static styles = `
    .gauges { display: grid; grid-template-columns: auto 1fr; gap: 18px; align-items: center; }
    .ring { position: relative; width: 92px; height: 92px; }
    .ring svg { transform: rotate(-90deg); }
    .ring .in { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; }
    .ring .in .value { font-size: 1.4em; }
    .fuel .row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
    .fuel + .fuel { margin-top: 12px; }
  `;

  renderCar(hass, car) {
    const e = car.entities;
    const updated = stateObj(hass, e.status_updated)?.state;
    const right = `<span class="click" data-entity="${e.status_updated || ""}">${t(hass, "updated")}<br>${esc(
      relative(hass, updated) || t(hass, "never"),
    )}</span>`;
    let html = head(hass, { title: car.name, sub: car.model, right });

    const battery = num(hass, e.battery);
    const r = 40;
    const c = 2 * Math.PI * r;
    const ring =
      e.battery != null
        ? `<div class="ring click" data-entity="${e.battery}">
            <svg width="92" height="92" viewBox="0 0 92 92">
              <circle cx="46" cy="46" r="${r}" fill="none" stroke="var(--divider-color)" stroke-width="8"/>
              <circle cx="46" cy="46" r="${r}" fill="none" stroke="var(--jd-accent)" stroke-width="8" stroke-linecap="round"
                stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - (battery ?? 0) / 100)}"/>
            </svg>
            <div class="in"><div><div class="value">${battery != null ? Math.round(battery) : "–"}<small>%</small></div>
            <div class="label">${t(hass, "battery")}</div></div></div>
          </div>`
        : "";

    const fuel = num(hass, e.fuel_level);
    const fuelRange = text(hass, e.fuel_range);
    const evRange = text(hass, e.ev_range);
    let right2 = "";
    if (e.fuel_level) {
      right2 += `<div class="fuel click" data-entity="${e.fuel_level}">
        <div class="row"><span class="label">${t(hass, "fuel")}</span><span class="value">${
          fuel != null ? Math.round(fuel) : "–"
        }<small>%</small></span></div>
        <div class="bar"><span style="width:${fuel ?? 0}%;background:var(--jd-hev)"></span></div>
        ${fuelRange ? `<div class="split"><span>${esc(fuelRange)} ${t(hass, "range")}</span></div>` : ""}
      </div>`;
    }
    if (evRange) {
      right2 += `<div class="fuel click" data-entity="${e.ev_range}">
        <div class="row"><span class="label">${t(hass, "ev_range")}</span><span class="value">${esc(evRange)}</span></div>
      </div>`;
    }
    html += `<div class="gauges">${ring}<div>${right2}</div></div>`;

    const service = [];
    const dueKm = text(hass, e.service_due_distance);
    const dueDate = stateObj(hass, e.service_due_date)?.state;
    if (dueKm) service.push(`${t(hass, "service_in")} ${dueKm}`);
    if (dueDate)
      service.push(new Date(dueDate).toLocaleDateString(lang(hass), { day: "numeric", month: "short", year: "numeric" }));
    html += `<div class="divider"></div><div class="stats">${stat(hass, e.odometer, t(hass, "odometer"))}${
      service.length
        ? `<div class="stat click" data-entity="${e.service_due_date || e.service_due_distance}"><div class="label">${t(
            hass,
            "service",
          )}</div><div class="value" style="font-size:1.05em">${esc(service.join(" · "))}</div></div>`
        : ""
    }</div>`;

    if (hass.states[car.account.subscription_problem]?.state === "on") {
      html += `<div class="warn click" data-entity="${car.account.subscription_problem}"><ha-icon icon="mdi:cloud-alert"></ha-icon>${t(
        hass,
        "subscription_problem",
      )}</div>`;
    }
    return html;
  }
}

// ---------------------------------------------------------------- last trip card

class JaeDriveLastTripCard extends JaeDriveCard {
  static styles = `
    .route { display: grid; grid-template-columns: 14px 1fr; column-gap: 10px; margin-bottom: 16px; }
    .dot { width: 12px; height: 12px; border-radius: 50%; border: 3px solid var(--jd-accent); box-sizing: border-box; margin-top: 4px; }
    .dot.end { background: var(--jd-accent); }
    .line { width: 2px; background: var(--jd-accent); opacity: 0.4; margin: 2px auto; min-height: 14px; }
    .place { font-weight: 500; line-height: 1.4; }
    .section { margin-top: 16px; }
  `;

  renderCar(hass, car) {
    const e = car.entities;
    const ended = stateObj(hass, e.last_trip_ended_at)?.state;
    const right = ended
      ? `<span class="click" data-entity="${e.last_trip_ended_at}">${esc(relative(hass, ended))}<br>${esc(
          shortDate(hass, ended) || "",
        )}</span>`
      : "";
    let html = head(hass, { title: t(hass, "last_trip"), sub: car.name, right, icon: "mdi:map-marker-path" });
    if (!stateObj(hass, e.last_trip_distance)) return html + `<div class="muted">${t(hass, "no_trip")}</div>`;

    const from = stateObj(hass, e.last_trip_start)?.state || t(hass, "unknown_place");
    const to = stateObj(hass, e.last_trip_end)?.state || t(hass, "unknown_place");
    html += `<div class="route">
      <div class="dot"></div><div class="place click" data-entity="${e.last_trip_start}">${esc(from)}</div>
      <div class="line"></div><div></div>
      <div class="dot end"></div><div class="place click" data-entity="${e.last_trip_end}">${esc(to)}</div>
    </div>`;

    html += `<div class="stats">${stat(hass, e.last_trip_distance, t(hass, "distance"))}${stat(
      hass,
      e.last_trip_duration,
      t(hass, "duration"),
    )}${stat(hass, e.last_trip_avg_speed, t(hass, "avg_speed"))}${stat(
      hass,
      e.last_trip_consumption,
      t(hass, "consumption"),
    )}${stat(hass, e.last_trip_fuel_used, t(hass, "fuel_used"))}</div>`;

    const evShare = num(hass, e.last_trip_ev_share);
    if (evShare != null) html += `<div class="section">${evBar(hass, evShare)}</div>`;

    const plugin = [
      stat(hass, e.last_trip_ev_distance, t(hass, "electric")),
      stat(hass, e.last_trip_hev_distance, t(hass, "hybrid")),
      stat(hass, e.last_trip_energy, t(hass, "energy")),
      stat(hass, e.last_trip_electric_consumption, unitOf(hass, e.last_trip_electric_consumption) || t(hass, "electric_consumption"), {
        unit: false,
      }),
      this._soc(hass, e),
      stat(hass, e.last_trip_power_max, t(hass, "peak_power")),
      stat(hass, e.last_trip_regen_max, t(hass, "peak_regen")),
      stat(hass, e.last_trip_regen_energy, t(hass, "recovered")),
    ].join("");
    if (plugin) html += `<div class="divider"></div><div class="stats">${plugin}</div>`;
    return html;
  }

  _soc(hass, e) {
    const a = num(hass, e.last_trip_battery_start);
    const b = num(hass, e.last_trip_battery_end);
    if (a == null || b == null) return "";
    return `<div class="stat click" data-entity="${e.last_trip_battery_end}"><div class="label">${t(
      hass,
      "battery_trip",
    )}</div><div class="value">${Math.round(a)}→${Math.round(b)}<small>%</small></div></div>`;
  }
}

// ---------------------------------------------------------------- trip A/B card

class JaeDriveTripsCard extends JaeDriveCard {
  static styles = `
    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .col { padding: 12px; border-radius: 12px; background: color-mix(in srgb, var(--jd-accent) 7%, transparent); min-width: 0; }
    .slot { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .badge { width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center; font-weight: 700;
      color: #fff; background: var(--jd-accent); flex: none; }
    .name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .big { font-size: 1.7em; font-weight: 600; margin: 4px 0 8px; }
    .big small { font-size: 0.5em; color: var(--secondary-text-color); margin-left: 3px; }
    .line { display: flex; justify-content: space-between; gap: 8px; font-size: 0.9em; padding: 2px 0; }
    .line > span:last-child { white-space: nowrap; }
  `;

  renderCar(hass, car) {
    const html = head(hass, { title: t(hass, "trips"), sub: car.name, icon: "mdi:counter" });
    return html + `<div class="cols">${this._slot(hass, car.entities, "a")}${this._slot(hass, car.entities, "b")}</div>`;
  }

  _slot(hass, e, s) {
    const dist = e[`trip_${s}_distance`];
    const label = hass.states[dist]?.attributes?.label || `Trip ${s.toUpperCase()}`;
    const p = parts(hass, dist);
    const top = `<div class="slot"><div class="badge">${s.toUpperCase()}</div><div class="name">${esc(label)}</div></div>`;
    if (!p) return `<div class="col">${top}<div class="muted">${t(hass, "not_running")}</div></div>`;
    const since = stateObj(hass, e[`trip_${s}_since`])?.state;
    const line = (key, label) => {
      const v = text(hass, e[`trip_${s}_${key}`]);
      return v
        ? `<div class="line click" data-entity="${e[`trip_${s}_${key}`]}"><span class="muted">${esc(label)}</span><span>${esc(
            v,
          )}</span></div>`
        : "";
    };
    return `<div class="col">${top}
      <div class="big click" data-entity="${dist}">${esc(p.value)}<small>${esc(p.unit)}</small></div>
      ${line("consumption", t(hass, "consumption"))}${line("fuel_used", t(hass, "fuel_used"))}
      ${line("ev_distance", t(hass, "electric"))}${line("energy", t(hass, "energy"))}
      ${
        since
          ? `<div class="line click" data-entity="${e[`trip_${s}_since`]}"><span class="muted">${t(
              hass,
              "since",
            )}</span><span>${esc(shortDate(hass, since))}</span></div>`
          : ""
      }
    </div>`;
  }
}

// ---------------------------------------------------------------- last 30 days card

class JaeDriveStatsCard extends JaeDriveCard {
  renderCar(hass, car) {
    const e = car.entities;
    let html = head(hass, { title: t(hass, "last_30d"), sub: car.name, icon: "mdi:calendar-month" });
    const trips = hass.states[e.distance_30d]?.attributes?.trips;
    html += `<div class="stats">${stat(hass, e.distance_30d, t(hass, "distance"))}${
      trips != null
        ? `<div class="stat click" data-entity="${e.distance_30d}"><div class="label">${t(
            hass,
            "trip_count",
          )}</div><div class="value">${esc(trips)}</div></div>`
        : ""
    }${stat(hass, e.consumption_30d, t(hass, "consumption"))}${stat(
      hass,
      e.electric_consumption_30d,
      unitOf(hass, e.electric_consumption_30d) || t(hass, "electric_consumption"),
      { unit: false },
    )}</div>`;
    const ev = num(hass, e.ev_share_30d);
    if (ev != null) html += `<div class="divider"></div><div class="label" style="margin-bottom:6px">${t(hass, "ev_share")}</div>${evBar(hass, ev)}`;
    return html;
  }
}

// ---------------------------------------------------------------- parking card

class JaeDriveParkingCard extends JaeDriveCard {
  static styles = `
    ha-card { padding: 0; }
    .top { padding: 16px 16px 0; }
    .head { margin-bottom: 12px; }
    .map > * { --ha-card-border-radius: 0; --ha-card-border-width: 0; }
    .empty { padding: 0 16px 16px; }
  `;

  renderCar(hass, car) {
    const e = car.entities;
    if (!e.park) {
      return `<div class="top">${head(hass, { title: t(hass, "parking"), sub: car.name, icon: "mdi:parking" })}</div><div class="empty muted">${t(
        hass,
        "no_location",
      )}</div>`;
    }
    const st = hass.states[e.park];
    const at = st?.attributes?.parked_at;
    const right = at ? `${t(hass, "parked")}<br>${esc(relative(hass, at))}` : "";
    return `<div class="top click" data-entity="${e.park}">${head(hass, {
      title: st?.attributes?.address || t(hass, "parking"),
      sub: car.name,
      right,
      icon: "mdi:parking",
    })}</div><div class="map"></div>`;
  }

  // Only the tracker: other changes would rebuild the map for nothing.
  watched(car) {
    return [car.entities.park];
  }

  async afterRender(hass, car) {
    const holder = this.shadowRoot.querySelector(".map");
    if (!holder || !car?.entities.park) return;
    const entity = car.entities.park;
    // Renders can follow each other while the map is being created: create it once per
    // entity, then put it in whatever holder is current at that moment.
    if (this._mapEntity !== entity) {
      this._mapEntity = entity;
      this._mapPromise = (async () => {
        const helpers = await window.loadCardHelpers?.();
        return helpers?.createCardElement({
          type: "map",
          entities: [{ entity, label_mode: "icon" }],
          default_zoom: 16,
          hours_to_show: 0,
          theme_mode: "auto",
          aspect_ratio: "16:10",
        });
      })();
    }
    const map = await this._mapPromise;
    if (!map || this._mapEntity !== entity) return;
    this._map = map;
    // Attach first: the map fits the marker only when it has a size.
    const current = this.shadowRoot.querySelector(".map");
    if (current && map.parentNode !== current) current.replaceChildren(map);
    map.hass = this._hass;
  }

  set hass(hass) {
    super.hass = hass;
    if (this._map) this._map.hass = hass;
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 6;
  }
}

// ---------------------------------------------------------------- dashboard strategy

class JaeDriveDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    const { cars } = jaedriveDevices(hass);
    if (!cars.length) {
      return {
        title: "JaeDrive",
        views: [{ title: "JaeDrive", cards: [{ type: "markdown", content: t(hass, "no_car") }] }],
      };
    }
    return {
      title: "JaeDrive",
      views: cars.map((car, i) => {
        const id = car.deviceId;
        const card = (type) => ({ type: `custom:jaedrive-${type}-card`, device_id: id });
        const graph = car.entities.odometer
          ? [
              {
                type: "statistics-graph",
                title: t(hass, "km_per_day"),
                entities: [car.entities.odometer],
                stat_types: ["change"],
                chart_type: "bar",
                period: "day",
                days_to_show: 30,
                grid_options: { columns: 12 },
              },
            ]
          : [];
        return {
          title: car.name,
          path: i ? `car-${i + 1}` : "car",
          icon: "mdi:car",
          type: "sections",
          max_columns: 3,
          sections: [
            { type: "grid", cards: [card("car"), ...(car.entities.park ? [card("parking")] : [])] },
            { type: "grid", cards: [card("last-trip"), card("trips")] },
            { type: "grid", cards: [card("stats"), ...graph] },
          ],
        };
      }),
    };
  }
}

// ---------------------------------------------------------------- registration

const CARDS = [
  ["jaedrive-car-card", JaeDriveCarCard, "JaeDrive car", "Battery, fuel, ranges, odometer and service."],
  ["jaedrive-last-trip-card", JaeDriveLastTripCard, "JaeDrive last trip", "Route, distance, consumption and electric share of the last trip."],
  ["jaedrive-trips-card", JaeDriveTripsCard, "JaeDrive Trip A / B", "The two manual trip counters."],
  ["jaedrive-stats-card", JaeDriveStatsCard, "JaeDrive last 30 days", "Distance, trips and consumption of the last 30 days."],
  ["jaedrive-parking-card", JaeDriveParkingCard, "JaeDrive parking", "Where the car is parked, on a map."],
];

window.customCards = window.customCards || [];
for (const [tag, cls, name, description] of CARDS) {
  if (!customElements.get(tag)) customElements.define(tag, cls);
  if (!window.customCards.some((c) => c.type === tag)) {
    window.customCards.push({ type: tag, name, description, preview: true, documentationURL: DOCS });
  }
}

if (!customElements.get("ll-strategy-dashboard-jaedrive")) {
  customElements.define("ll-strategy-dashboard-jaedrive", JaeDriveDashboardStrategy);
}
window.customStrategies = window.customStrategies || [];
if (!window.customStrategies.some((s) => s.type === "jaedrive")) {
  window.customStrategies.push({
    type: "jaedrive",
    strategyType: "dashboard",
    name: "JaeDrive",
    description: "Your car from JaeDrive: status, parking, last trip, Trip A/B and statistics. Updates by itself.",
    documentationURL: DOCS,
  });
}
