/**
 * smartmat-card.js — Lovelace custom card for SmartMat Dashboard.
 *
 * Usage in any dashboard:
 *   type: custom:smartmat-card
 *   entity: sensor.smartmat_0328_inventory
 *   name: (optional — overrides the product name shown in header)
 */

const VERSION = "0.2.0";

const REL = (() => {
  try {
    return new Intl.RelativeTimeFormat(
      (navigator.language || "en").startsWith("zh") ? "zh-Hant" : navigator.language,
      { numeric: "auto" }
    );
  } catch (_) {
    return null;
  }
})();

function fmtRel(iso) {
  if (!iso || iso === "unknown" || iso === "unavailable" || iso === "none") return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return String(iso);
  const diffSec = (t - Date.now()) / 1000;
  const abs = Math.abs(diffSec);
  if (!REL) {
    const m = Math.round(abs / 60);
    return `${m} min ago`;
  }
  if (abs < 60) return REL.format(Math.round(diffSec), "second");
  if (abs < 3600) return REL.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return REL.format(Math.round(diffSec / 3600), "hour");
  return REL.format(Math.round(diffSec / 86400), "day");
}

function getStateStr(hass, eid, fallback) {
  if (!eid) return fallback;
  const s = hass.states[eid];
  return s ? s.state : fallback;
}

function getStateNum(hass, eid, fallback) {
  if (!eid) return fallback;
  const s = hass.states[eid];
  if (!s) return fallback;
  const v = parseFloat(s.state);
  return Number.isNaN(v) ? fallback : v;
}

class SmartMatCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("smartmat-card: 'entity' is required (a sensor.smartmat_*_inventory)");
    }
    this._config = config;
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  static getConfigElement() {
    return document.createElement("smartmat-card-editor");
  }

  static getStubConfig(hass) {
    // Find first inventory sensor, if any
    const first = hass && Object.keys(hass.states).find(
      (k) => k.startsWith("sensor.smartmat_") && k.endsWith("_inventory")
    );
    return { entity: first || "sensor.smartmat_XXXX_inventory" };
  }

  _build() {
    this.innerHTML = `
      <ha-card>
        <div class="smc">
          <div class="row hdr">
            <input class="product" type="text" placeholder="未設定" aria-label="商品名" />
          </div>
          <div class="gauge-wrap"></div>
          <div class="alrt-wrap"></div>
          <div class="row calib">
            <label class="fld">
              <span class="lbl">空盤</span>
              <input class="tare" type="number" step="1" min="0" />
              <span class="unit">g</span>
            </label>
            <label class="fld">
              <span class="lbl">滿庫</span>
              <input class="full" type="number" step="1" min="0" />
              <span class="unit">g</span>
            </label>
          </div>
          <div class="seen"></div>
        </div>
        <style>
          ha-card { overflow: hidden; }
          .smc { padding: 12px 14px 10px; }
          .smc .row { display:flex; gap:8px; align-items:center; }
          .smc .hdr { margin-bottom: 4px; }
          .smc .product {
            flex:1; padding:4px 6px; font-size:16px; font-weight:500;
            background:transparent; border:none;
            color:var(--primary-text-color);
            border-bottom: 1px dashed transparent;
            min-width: 0;
          }
          .smc .product:hover { border-bottom-color: var(--divider-color); }
          .smc .product:focus {
            outline:none;
            border-bottom-color: var(--primary-color);
          }
          .smc .gauge-wrap {
            display:flex; justify-content:center;
            padding: 4px 0 6px;
          }
          .smc ha-gauge { --gauge-color: var(--primary-color); }
          .smc .alrt-wrap { margin: 4px 0 8px; }
          .smc ha-alert { display:block; }
          .smc .calib { gap:10px; margin-top:6px; }
          .smc .fld {
            flex:1; display:flex; align-items:center; gap:4px;
            font-size:12px; color:var(--secondary-text-color);
            background: var(--secondary-background-color);
            border-radius: 6px;
            padding: 4px 8px;
          }
          .smc .fld .lbl { flex-shrink:0; }
          .smc .fld input {
            flex:1; min-width:0; padding:2px 4px;
            background: var(--card-background-color);
            border:1px solid var(--divider-color);
            border-radius:4px;
            color:var(--primary-text-color);
            font-size: 12px;
            text-align: right;
          }
          .smc .fld .unit { flex-shrink:0; opacity:0.7; }
          .smc .seen {
            font-size: 11px;
            color: var(--secondary-text-color);
            text-align: right;
            margin-top: 6px;
            opacity: 0.75;
          }
          .err {
            padding: 14px;
            color: var(--error-color, #b00020);
            font-size: 13px;
          }
        </style>
      </ha-card>
    `;
    this._el = {
      prod: this.querySelector(".product"),
      gaugeWrap: this.querySelector(".gauge-wrap"),
      alertWrap: this.querySelector(".alrt-wrap"),
      tare: this.querySelector(".tare"),
      full: this.querySelector(".full"),
      seen: this.querySelector(".seen"),
    };

    // Build ha-gauge once (if the element is registered)
    this._gauge = document.createElement("ha-gauge");
    this._gauge.setAttribute("min", "0");
    this._gauge.setAttribute("max", "100");
    this._gauge.setAttribute("needle", "");
    this._gauge.value = 0;
    this._el.gaugeWrap.appendChild(this._gauge);

    // ha-alert
    this._alert = document.createElement("ha-alert");
    this._el.alertWrap.appendChild(this._alert);

    // Event handlers (wire once)
    this._el.prod.addEventListener("change", () => {
      const eid = this._runtime && this._runtime.productEid;
      if (eid) {
        this._hass.callService("text", "set_value", {
          entity_id: eid,
          value: this._el.prod.value,
        });
      }
    });
    this._el.tare.addEventListener("change", () => {
      const eid = this._runtime && this._runtime.tareEid;
      if (eid) {
        this._hass.callService("number", "set_value", {
          entity_id: eid,
          value: parseFloat(this._el.tare.value),
        });
      }
    });
    this._el.full.addEventListener("change", () => {
      const eid = this._runtime && this._runtime.fullEid;
      if (eid) {
        this._hass.callService("number", "set_value", {
          entity_id: eid,
          value: parseFloat(this._el.full.value),
        });
      }
    });

    this._built = true;
  }

  _renderError(msg) {
    this.innerHTML = `<ha-card><div class="err">${msg}</div></ha-card>`;
    this._built = false;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const invEid = this._config.entity;
    const inv = this._hass.states[invEid];
    if (!inv) {
      this._renderError(`Entity <code>${invEid}</code> not found. Did you install the SmartMat Dashboard integration and add a mat?`);
      return;
    }
    const a = inv.attributes || {};
    const weightEid = a.weight_entity;
    const tareEid = a.tare_entity;
    const fullEid = a.full_entity;
    const productEid = a.product_entity;
    const lastSeenEid = a.last_seen_entity;
    const sid = a.short_id || "—";

    if (!this._built) this._build();
    this._runtime = { weightEid, tareEid, fullEid, productEid, lastSeenEid, sid };

    const pctRaw = parseFloat(inv.state);
    const hasPct = !Number.isNaN(pctRaw);
    const pct = hasPct ? pctRaw : 0;

    const critical = getStateNum(this._hass, "input_number.smartmat_threshold_critical", 10);
    const low = getStateNum(this._hass, "input_number.smartmat_threshold_low", 33);
    const mid = getStateNum(this._hass, "input_number.smartmat_threshold_mid", 66);

    const weightStr = getStateStr(this._hass, weightEid, "—");
    const productName = this._config.name || getStateStr(this._hass, productEid, `Mat ${sid}`);
    const tareVal = getStateStr(this._hass, tareEid, "0");
    const fullVal = getStateStr(this._hass, fullEid, "1000");
    const lastSeen = getStateStr(this._hass, lastSeenEid, null);

    let alertKind, emoji, levelLabel;
    if (!hasPct) { alertKind = "info"; emoji = "—"; levelLabel = ""; }
    else if (pct < critical) { alertKind = "error";   emoji = "🚨"; levelLabel = "快用完"; }
    else if (pct < low)      { alertKind = "warning"; emoji = "⚠️"; levelLabel = "低";     }
    else if (pct < mid)      { alertKind = "info";    emoji = "🟡"; levelLabel = "中";     }
    else                     { alertKind = "success"; emoji = "✅"; levelLabel = "充足";   }

    // Don't trample inputs the user is editing
    const ae = document.activeElement;
    if (ae !== this._el.prod) this._el.prod.value = productName || "";
    if (ae !== this._el.tare) this._el.tare.value = tareVal;
    if (ae !== this._el.full) this._el.full.value = fullVal;

    this._gauge.value = hasPct ? Math.max(0, Math.min(100, pct)) : 0;
    if (hasPct) {
      // Colour the gauge needle per level
      const color = alertKind === "error" ? "var(--error-color, #d32f2f)"
                  : alertKind === "warning" ? "var(--warning-color, #f57c00)"
                  : alertKind === "info"    ? "var(--info-color, #fbc02d)"
                  : "var(--success-color, #388e3c)";
      this._gauge.style.setProperty("--gauge-color", color);
    }

    this._alert.setAttribute("alert-type", alertKind);
    this._alert.innerHTML = hasPct
      ? `${emoji} ${levelLabel} · ${Math.round(pct)}% · ${weightStr} g`
      : `${emoji} 無資料`;

    this._el.seen.textContent = `上報: ${fmtRel(lastSeen)}`;
  }

  getCardSize() {
    return 4;
  }
}

// ---- Minimal GUI editor (just entity picker + optional name) ----
class SmartMatCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  _render() {
    if (!this._hass) return;
    if (this._built) return;

    this.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:12px; padding:8px 0;">
        <ha-entity-picker
          label="Inventory sensor (sensor.smartmat_*_inventory)"
          allow-custom-entity
        ></ha-entity-picker>
        <ha-textfield label="Name override (optional)"></ha-textfield>
      </div>
    `;
    this._picker = this.querySelector("ha-entity-picker");
    this._nameField = this.querySelector("ha-textfield");

    this._picker.hass = this._hass;
    this._picker.includeDomains = ["sensor"];
    this._picker.entityFilter = (s) =>
      s.entity_id.startsWith("sensor.smartmat_") &&
      s.entity_id.endsWith("_inventory");
    this._picker.value = this._config.entity || "";
    this._nameField.value = this._config.name || "";

    this._picker.addEventListener("value-changed", (e) => {
      this._config = { ...this._config, entity: e.detail.value };
      this._fire();
    });
    this._nameField.addEventListener("change", () => {
      const v = this._nameField.value;
      this._config = { ...this._config, name: v || undefined };
      this._fire();
    });
    this._built = true;
  }
  _fire() {
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: this._config } })
    );
  }
}

if (!customElements.get("smartmat-card")) {
  customElements.define("smartmat-card", SmartMatCard);
}
if (!customElements.get("smartmat-card-editor")) {
  customElements.define("smartmat-card-editor", SmartMatCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === "smartmat-card")) {
  window.customCards.push({
    type: "smartmat-card",
    name: "SmartMat Card",
    description: "SmartMat Lite per-mat inventory tile (gauge + alert + inline calibration)",
    preview: false,
    documentationURL: "https://github.com/dryob/smartmat-rescue",
  });
}

// eslint-disable-next-line no-console
console.info(
  `%c SMARTMAT-CARD %c v${VERSION} `,
  "color:white;background:#4caf50;padding:2px 4px;border-radius:3px 0 0 3px;font-weight:bold;",
  "color:#4caf50;background:white;padding:2px 4px;border-radius:0 3px 3px 0;border:1px solid #4caf50;"
);
