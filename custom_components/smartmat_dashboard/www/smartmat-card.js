/**
 * smartmat-card.js — Lovelace custom card for SmartMat Dashboard.
 *
 * Usage:
 *   type: custom:smartmat-card
 *   entity: sensor.smartmat_0328_inventory
 *   variant: ring | tile | liquid | minimal   # default: ring
 *   name: 貓飼料                               # optional — display override
 *   icon: mdi:package-variant-closed          # optional
 *   controls: true                            # optional — inline tare/full/rename
 *   tap_action: { action: none }              # optional — default more-info
 */

const VERSION = "0.3.1";
const RING_R = 42;                          // ring radius inside a 100-unit viewBox
const RING_C = 2 * Math.PI * RING_R;        // ~ 263.894

const DEFAULT_ICON = "mdi:package-variant-closed";
const VARIANTS = new Set(["ring", "tile", "liquid", "minimal"]);

/* ---------- utilities ---------- */

const REL = (() => {
  try {
    const lang = (navigator.language || "en").toLowerCase();
    const use = lang.startsWith("zh") ? "zh-Hant" : navigator.language;
    return new Intl.RelativeTimeFormat(use, { numeric: "auto" });
  } catch (_) {
    return null;
  }
})();

function fmtRel(iso) {
  if (!iso || ["unknown", "unavailable", "none", ""].includes(iso)) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return String(iso);
  const diff = (t - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (!REL) return `${Math.round(abs / 60)} min ago`;
  if (abs < 60) return REL.format(Math.round(diff), "second");
  if (abs < 3600) return REL.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return REL.format(Math.round(diff / 3600), "hour");
  return REL.format(Math.round(diff / 86400), "day");
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

function isUsable(s) {
  return s != null && !["unknown", "unavailable", "none", ""].includes(s);
}

function fireMoreInfo(host, entityId) {
  host.dispatchEvent(
    new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    })
  );
}

/* ---------- level / colour ---------- */

function levelFor(pct, critical, low, mid, hasPct) {
  if (!hasPct) {
    return { key: "unknown", emoji: "—", label: "無資料", color: "var(--disabled-color, #9e9e9e)" };
  }
  if (pct < critical) {
    return { key: "critical", emoji: "🚨", label: "快用完", color: "var(--error-color, #d32f2f)" };
  }
  if (pct < low) {
    return { key: "low", emoji: "⚠️", label: "低", color: "var(--warning-color, #ef6c00)" };
  }
  if (pct < mid) {
    return { key: "mid", emoji: "🟡", label: "中", color: "#f9a825" };
  }
  return { key: "full", emoji: "✅", label: "充足", color: "var(--success-color, #2e7d32)" };
}

/* ---------- styles (identical across all variants, scoped per-card) ---------- */

const CARD_CSS = `
:host {
  display: block;
}
ha-card {
  overflow: hidden;
  height: 100%;
}
.smc {
  --smc-color: var(--primary-color);
  --smc-soft: color-mix(in srgb, var(--smc-color) 14%, transparent);
  --smc-softer: color-mix(in srgb, var(--smc-color) 8%, transparent);
  position: relative;
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  color: var(--primary-text-color);
}
.smc.no-tap { cursor: default; }

/* ---------- shared typography ---------- */
.title {
  font-size: 15px;
  font-weight: 500;
  color: var(--primary-text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  margin: 0;
  padding: 0;
  background: transparent;
  border: none;
  border-bottom: 1px dashed transparent;
  font-family: inherit;
}
input.title:hover { border-bottom-color: var(--divider-color); }
input.title:focus { outline: none; border-bottom-color: var(--smc-color); }

.icon {
  --mdc-icon-size: 20px;
  color: var(--smc-color);
  flex-shrink: 0;
  transition: color .25s ease;
}

.header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.bar {
  height: 4px;
  border-radius: 999px;
  background: var(--divider-color);
  opacity: 0.5;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  width: 0%;
  background: var(--smc-color);
  border-radius: 999px;
  transition: width .8s cubic-bezier(.4,0,.2,1), background .25s ease;
}

.dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.4;
  flex-shrink: 0;
}

/* ===================================================== */
/* RING variant                                          */
/* ===================================================== */
.smc.ring { padding: 14px 16px 12px; }
.smc.ring .header { margin-bottom: 6px; }

.ring-wrap {
  position: relative;
  width: 140px; height: 140px;
  margin: 2px auto 8px;
}
.ring-svg {
  width: 100%; height: 100%;
  transform: rotate(-90deg);
  overflow: visible;
}
.ring-track {
  fill: none;
  stroke: var(--divider-color);
  stroke-width: 9;
  opacity: 0.35;
}
.ring-fill {
  fill: none;
  stroke: var(--smc-color);
  stroke-width: 9;
  stroke-linecap: round;
  stroke-dasharray: ${RING_C.toFixed(3)};
  stroke-dashoffset: ${RING_C.toFixed(3)};
  transition: stroke-dashoffset .8s cubic-bezier(.4,0,.2,1), stroke .25s ease;
}
.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  line-height: 1;
}
.ring-pct {
  font-size: 36px;
  font-weight: 700;
  letter-spacing: -1.5px;
  color: var(--primary-text-color);
}
.ring-pct-unit {
  font-size: 11px;
  color: var(--secondary-text-color);
  margin-top: 4px;
  letter-spacing: 1px;
}

.pill {
  display: flex;
  justify-content: center;
}
.pill-inner {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 500;
  background: var(--smc-soft);
  color: var(--smc-color);
  max-width: 100%;
  transition: background .25s ease, color .25s ease;
}
.pill-inner .sep { opacity: 0.45; }

.foot {
  text-align: center;
  font-size: 11px;
  color: var(--secondary-text-color);
  opacity: 0.8;
  margin-top: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===================================================== */
/* TILE variant                                          */
/* ===================================================== */
.smc.tile { padding: 12px 14px; }
.tile-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.tile-icon {
  width: 40px; height: 40px;
  border-radius: 50%;
  background: var(--smc-soft);
  color: var(--smc-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background .25s ease, color .25s ease;
}
.tile-icon .icon {
  --mdc-icon-size: 22px;
}
.tile-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tile-info .title {
  padding: 0;
  font-size: 14px;
}
.tile-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--secondary-text-color);
  min-width: 0;
}
.tile-sub .pct-inline {
  color: var(--smc-color);
  font-weight: 600;
  font-size: 13px;
  transition: color .25s ease;
}
.tile-sub .sep { opacity: 0.45; }
.tile-sub .seen {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tile-status {
  font-size: 20px;
  flex-shrink: 0;
  line-height: 1;
}
.tile-bar {
  margin-top: 8px;
}

/* ===================================================== */
/* LIQUID variant                                        */
/* ===================================================== */
.smc.liquid {
  padding: 0;
  min-height: 170px;
  display: flex;
}
.liquid-wrap {
  position: relative;
  flex: 1;
  padding: 14px 16px 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.liquid-fill {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 0%;
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--smc-color) 45%, transparent),
    color-mix(in srgb, var(--smc-color) 18%, transparent) 70%,
    color-mix(in srgb, var(--smc-color) 10%, transparent)
  );
  transition: height .9s cubic-bezier(.4,0,.2,1), background .25s ease;
  pointer-events: none;
  z-index: 0;
}
.liquid-fill::before {
  /* waterline glow */
  content: "";
  position: absolute;
  top: -2px; left: 0; right: 0; height: 2px;
  background: color-mix(in srgb, var(--smc-color) 65%, transparent);
  opacity: 0.8;
}
.liquid-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}
.liquid-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.liquid-pct {
  font-size: 44px;
  font-weight: 700;
  letter-spacing: -2px;
  color: var(--primary-text-color);
  line-height: 1;
}
.liquid-pct-unit {
  font-size: 16px;
  color: var(--secondary-text-color);
  font-weight: 500;
  margin-left: 2px;
}
.liquid-emoji {
  font-size: 26px;
  line-height: 1;
}
.liquid-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  color: var(--secondary-text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.liquid-foot .sep { opacity: 0.45; }

/* ===================================================== */
/* MINIMAL variant                                       */
/* ===================================================== */
.smc.minimal { padding: 14px 16px 12px; }
.minimal-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.minimal-head .emoji {
  font-size: 16px;
  margin-left: auto;
  flex-shrink: 0;
  line-height: 1;
}
.minimal-big {
  display: flex;
  align-items: baseline;
  justify-content: flex-start;
  gap: 2px;
  color: var(--smc-color);
  transition: color .25s ease;
  line-height: 1;
  margin-bottom: 10px;
}
.minimal-pct {
  font-size: 44px;
  font-weight: 700;
  letter-spacing: -2px;
}
.minimal-pct-unit {
  font-size: 18px;
  color: var(--secondary-text-color);
  font-weight: 500;
  margin-left: 4px;
}
.minimal-bar { margin-bottom: 8px; }
.minimal-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--secondary-text-color);
  white-space: nowrap;
  overflow: hidden;
}
.minimal-foot .sep { opacity: 0.45; }

/* ===================================================== */
/* shared: inline calibration controls                   */
/* ===================================================== */
.calib {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.calib .fld {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--secondary-text-color);
  background: var(--secondary-background-color);
  border-radius: 8px;
  padding: 4px 8px;
}
.calib .fld input {
  flex: 1;
  min-width: 0;
  padding: 2px 4px;
  background: var(--card-background-color);
  border: 1px solid var(--divider-color);
  border-radius: 4px;
  color: var(--primary-text-color);
  font-size: 12px;
  text-align: right;
  font-family: inherit;
}
.calib .fld .unit {
  opacity: 0.7;
  flex-shrink: 0;
}

.err {
  padding: 14px;
  font-size: 13px;
  color: var(--error-color, #b00020);
  line-height: 1.4;
}
.err code {
  background: var(--secondary-background-color);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
}
`;

/* ---------- the card ---------- */

class SmartMatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._built = false;
    this._variant = "ring";
    this._runtime = {};
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error(
        "smartmat-card: 'entity' is required (a sensor.smartmat_*_inventory)"
      );
    }
    const variant = VARIANTS.has(config.variant) ? config.variant : "ring";
    const prev = this._config || {};
    const structural =
      prev.variant !== variant ||
      !!prev.controls !== !!config.controls ||
      (prev.icon || DEFAULT_ICON) !== (config.icon || DEFAULT_ICON);

    this._config = { ...config };
    this._variant = variant;
    if (structural) this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  static getConfigElement() {
    return document.createElement("smartmat-card-editor");
  }

  static getStubConfig(hass) {
    const first =
      hass &&
      Object.keys(hass.states || {}).find(
        (k) => k.startsWith("sensor.smartmat_") && k.endsWith("_inventory")
      );
    return {
      entity: first || "sensor.smartmat_XXXX_inventory",
      variant: "ring",
    };
  }

  getCardSize() {
    const pad = this._config && this._config.controls ? 1 : 0;
    const base = { ring: 4, tile: 1, liquid: 3, minimal: 2 }[this._variant] || 3;
    return base + pad;
  }

  /* ---------- variant HTML ---------- */

  _titleHtml() {
    return this._config.controls
      ? `<input class="title" type="text" placeholder="未設定" aria-label="商品名" />`
      : `<div class="title"></div>`;
  }

  _calibHtml() {
    if (!this._config.controls) return "";
    return `
      <div class="calib">
        <label class="fld">
          <span>空盤</span>
          <input class="tare" type="number" step="1" min="0" />
          <span class="unit">g</span>
        </label>
        <label class="fld">
          <span>滿庫</span>
          <input class="full" type="number" step="1" min="0" />
          <span class="unit">g</span>
        </label>
      </div>
    `;
  }

  _variantHtml(variant, icon) {
    switch (variant) {
      case "tile":
        return `
          <div class="tile-row">
            <div class="tile-icon"><ha-icon class="icon" icon="${icon}"></ha-icon></div>
            <div class="tile-info">
              ${this._titleHtml()}
              <div class="tile-sub">
                <span class="pct-inline">—</span>
                <span class="sep">·</span>
                <span class="weight">—</span>
                <span class="sep">·</span>
                <span class="seen">—</span>
              </div>
            </div>
            <div class="tile-status"><span class="emoji">—</span></div>
          </div>
          <div class="bar tile-bar"><div class="bar-fill"></div></div>
        `;

      case "liquid":
        return `
          <div class="liquid-wrap">
            <div class="liquid-fill"></div>
            <div class="liquid-content">
              <div class="header">
                <ha-icon class="icon" icon="${icon}"></ha-icon>
                ${this._titleHtml()}
              </div>
              <div class="liquid-center">
                <div>
                  <span class="liquid-pct">—</span><span class="liquid-pct-unit">%</span>
                </div>
                <span class="liquid-emoji emoji">—</span>
              </div>
              <div class="liquid-foot">
                <span class="weight">—</span>
                <span class="sep">·</span>
                <span class="label">—</span>
                <span class="sep">·</span>
                <span class="seen">—</span>
              </div>
            </div>
          </div>
        `;

      case "minimal":
        return `
          <div class="minimal-head">
            <ha-icon class="icon" icon="${icon}"></ha-icon>
            ${this._titleHtml()}
            <span class="emoji">—</span>
          </div>
          <div class="minimal-big">
            <span class="minimal-pct">—</span><span class="minimal-pct-unit">%</span>
          </div>
          <div class="bar minimal-bar"><div class="bar-fill"></div></div>
          <div class="minimal-foot">
            <span class="weight">—</span>
            <span class="sep">·</span>
            <span class="seen">—</span>
          </div>
        `;

      default: // ring
        return `
          <div class="header">
            <ha-icon class="icon" icon="${icon}"></ha-icon>
            ${this._titleHtml()}
          </div>
          <div class="ring-wrap">
            <svg viewBox="0 0 100 100" class="ring-svg" aria-hidden="true">
              <circle class="ring-track" cx="50" cy="50" r="${RING_R}" fill="none"></circle>
              <circle class="ring-fill"  cx="50" cy="50" r="${RING_R}" fill="none"></circle>
            </svg>
            <div class="ring-center">
              <div class="ring-pct">—</div>
              <div class="ring-pct-unit">%</div>
            </div>
          </div>
          <div class="pill">
            <span class="pill-inner">
              <span class="emoji">—</span>
              <span class="label">—</span>
              <span class="sep">·</span>
              <span class="weight">—</span>
            </span>
          </div>
          <div class="foot">—</div>
        `;
    }
  }

  _build() {
    const variant = this._variant;
    const icon = this._config.icon || DEFAULT_ICON;
    const hasTap = this._hasTapAction();

    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <ha-card>
        <div class="smc ${variant} ${hasTap ? "" : "no-tap"}">
          ${this._variantHtml(variant, icon)}
          ${this._calibHtml()}
        </div>
      </ha-card>
    `;

    const q = (sel) => this.shadowRoot.querySelector(sel);
    const qa = (sel) => this.shadowRoot.querySelectorAll(sel);

    this._el = {
      smc: q(".smc"),
      title: q(".title"),
      icon: q(".icon"),
      // ring
      ringFill: q(".ring-fill"),
      ringPct: q(".ring-pct"),
      // tile
      pctInline: q(".pct-inline"),
      tileEmoji: q(".tile-status .emoji"),
      barFill: q(".bar-fill"),
      // liquid
      liquidFill: q(".liquid-fill"),
      liquidPct: q(".liquid-pct"),
      // minimal
      minimalPct: q(".minimal-pct"),
      // shared text targets
      emoji: q(".emoji"),
      label: q(".label"),
      weightList: qa(".weight"),
      seenList: qa(".seen"),
      foot: q(".foot"),
      // controls
      tare: q(".tare"),
      full: q(".full"),
    };

    this._wireControls();
    this._wireTap();
    this._built = true;
  }

  _wireControls() {
    if (!this._config.controls) return;
    const call = (domain, eid, raw) => {
      if (!eid) return;
      const value = domain === "number" ? parseFloat(raw) : raw;
      if (domain === "number" && (raw === "" || Number.isNaN(value))) return;
      this._hass.callService(domain, "set_value", { entity_id: eid, value });
    };
    if (this._el.title && this._el.title.tagName === "INPUT") {
      this._el.title.addEventListener("change", () => {
        call("text", this._runtime.productEid, this._el.title.value);
      });
    }
    if (this._el.tare) {
      this._el.tare.addEventListener("change", () => {
        call("number", this._runtime.tareEid, this._el.tare.value);
      });
    }
    if (this._el.full) {
      this._el.full.addEventListener("change", () => {
        call("number", this._runtime.fullEid, this._el.full.value);
      });
    }
  }

  _wireTap() {
    if (!this._hasTapAction()) return;
    this._el.smc.addEventListener("click", (e) => {
      if (e.target.closest("input, button, ha-textfield")) return;
      const entity = this._config.entity;
      if (entity) fireMoreInfo(this, entity);
    });
  }

  _hasTapAction() {
    const t = this._config && this._config.tap_action;
    if (!t) return true;
    return t.action !== "none";
  }

  _renderError(msg) {
    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <ha-card><div class="err">${msg}</div></ha-card>
    `;
    this._built = false;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const invEid = this._config.entity;
    const inv = this._hass.states[invEid];
    if (!inv) {
      this._renderError(
        `Entity <code>${invEid}</code> not found. Add a mat via 設定 → 裝置與服務 → SmartMat Dashboard first.`
      );
      return;
    }

    const a = inv.attributes || {};
    const productEid = a.product_entity;
    const weightEid = a.weight_entity;
    const tareEid = a.tare_entity;
    const fullEid = a.full_entity;
    const lastSeenEid = a.last_seen_entity;
    const sid = a.short_id || "—";

    if (!this._built) this._build();
    this._runtime = { weightEid, tareEid, fullEid, productEid, lastSeenEid, sid };

    const pctRaw = parseFloat(inv.state);
    const hasPct = !Number.isNaN(pctRaw);
    const pct = hasPct ? Math.max(0, Math.min(100, pctRaw)) : 0;
    const pctRound = Math.round(pct);

    const critical = getStateNum(this._hass, "input_number.smartmat_threshold_critical", 10);
    const low = getStateNum(this._hass, "input_number.smartmat_threshold_low", 33);
    const mid = getStateNum(this._hass, "input_number.smartmat_threshold_mid", 66);
    const lv = levelFor(pct, critical, low, mid, hasPct);

    // Weight
    const rawW = getStateStr(this._hass, weightEid, null);
    let weightStr;
    if (isUsable(rawW)) {
      const f = parseFloat(rawW);
      weightStr = Number.isNaN(f) ? `${rawW} g` : `${Math.round(f)} g`;
    } else {
      weightStr = "— g";
    }

    const productName =
      this._config.name ||
      getStateStr(this._hass, productEid, `Mat ${sid}`) ||
      `Mat ${sid}`;

    const lastSeenStr = fmtRel(getStateStr(this._hass, lastSeenEid, null));

    // Accent colour
    this._el.smc.style.setProperty("--smc-color", lv.color);

    // Title
    const ae = this.shadowRoot.activeElement;
    if (this._el.title && this._el.title.tagName === "INPUT") {
      if (ae !== this._el.title) this._el.title.value = productName;
    } else if (this._el.title) {
      this._el.title.textContent = productName;
    }

    // Controls
    if (this._el.tare && ae !== this._el.tare) {
      this._el.tare.value = getStateStr(this._hass, tareEid, "0");
    }
    if (this._el.full && ae !== this._el.full) {
      this._el.full.value = getStateStr(this._hass, fullEid, "1000");
    }

    // Shared: emoji + label + weight + seen (across variants)
    if (this._el.emoji) this._el.emoji.textContent = lv.emoji;
    if (this._el.label) this._el.label.textContent = lv.label;
    this._el.weightList.forEach((n) => (n.textContent = weightStr));
    this._el.seenList.forEach((n) => (n.textContent = lastSeenStr));

    // Per-variant specifics
    switch (this._variant) {
      case "tile":
        if (this._el.pctInline) this._el.pctInline.textContent = hasPct ? `${pctRound}%` : "—";
        if (this._el.tileEmoji) this._el.tileEmoji.textContent = lv.emoji;
        if (this._el.barFill) this._el.barFill.style.width = hasPct ? `${pct}%` : "0%";
        break;

      case "liquid":
        if (this._el.liquidFill) this._el.liquidFill.style.height = hasPct ? `${pct}%` : "0%";
        if (this._el.liquidPct) this._el.liquidPct.textContent = hasPct ? String(pctRound) : "—";
        break;

      case "minimal":
        if (this._el.minimalPct) this._el.minimalPct.textContent = hasPct ? String(pctRound) : "—";
        if (this._el.barFill) this._el.barFill.style.width = hasPct ? `${pct}%` : "0%";
        break;

      default: // ring
        if (this._el.ringPct) this._el.ringPct.textContent = hasPct ? String(pctRound) : "—";
        if (this._el.ringFill) {
          const offset = RING_C * (1 - pct / 100);
          this._el.ringFill.style.strokeDashoffset = String(offset);
        }
        if (this._el.foot) this._el.foot.textContent = `上報 ${lastSeenStr}`;
        break;
    }
  }
}

/* ---------- editor ---------- */

const EDITOR_SCHEMA = [
  {
    name: "entity",
    required: true,
    selector: {
      entity: { filter: { domain: "sensor", integration: "smartmat_dashboard" } },
    },
  },
  {
    name: "variant",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { label: "Ring (圓環儀表)", value: "ring" },
          { label: "Tile (緊湊橫式)", value: "tile" },
          { label: "Liquid (瓶罐水位)", value: "liquid" },
          { label: "Minimal (極簡)", value: "minimal" },
        ],
      },
    },
  },
  { name: "name", selector: { text: {} } },
  { name: "icon", selector: { icon: {} } },
  { name: "controls", selector: { boolean: {} } },
];

const EDITOR_LABELS = {
  entity: "Inventory sensor",
  variant: "外觀",
  name: "商品名覆蓋 (選填)",
  icon: "Icon (選填)",
  controls: "Card 上內嵌編輯 (空盤/滿庫/改商品名)",
};

class SmartMatCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
  }
  setConfig(config) {
    this._config = config || {};
    this._update();
  }
  set hass(hass) {
    this._hass = hass;
    this._update();
  }
  connectedCallback() {
    this._update();
  }
  _update() {
    if (!this._hass) return;
    const cfg = this._config || {};
    try {
      if (!this._form) {
        this._form = document.createElement("ha-form");
        this._form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
        this._form.addEventListener("value-changed", (ev) => this._onChange(ev));

        const hint = document.createElement("div");
        hint.style.cssText =
          "font-size:12px; color:var(--secondary-text-color); line-height:1.45; padding:10px 0 4px;";
        hint.innerHTML =
          "預設 <b>Card 上內嵌編輯</b> 關:card 只顯示狀態,想改設定去 " +
          "<b>設定 → 裝置與服務 → SmartMat Dashboard</b> 點秤改。";

        this.appendChild(this._form);
        this.appendChild(hint);
      }
      this._form.hass = this._hass;
      this._form.schema = EDITOR_SCHEMA;
      this._form.data = {
        entity: cfg.entity || "",
        variant: cfg.variant || "ring",
        name: cfg.name || "",
        icon: cfg.icon || "",
        controls: !!cfg.controls,
      };
    } catch (e) {
      console.error("smartmat-card editor failed:", e);
      this.innerHTML = `
        <div style="padding:12px; color:var(--error-color, #b00020); font-size:13px;">
          SmartMat card editor failed (${String((e && e.message) || e)}).
          Edit the YAML directly — the card itself works fine.
        </div>
      `;
    }
  }
  _onChange(ev) {
    const v = (ev && ev.detail && ev.detail.value) || {};
    const newConfig = { type: "custom:smartmat-card", entity: v.entity || "" };
    if (v.variant && v.variant !== "ring") newConfig.variant = v.variant;
    if (v.name) newConfig.name = v.name;
    if (v.icon) newConfig.icon = v.icon;
    if (v.controls) newConfig.controls = true;
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }
}

/* ---------- registration ---------- */

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
    description:
      "SmartMat Lite per-mat inventory card — ring / tile / liquid / minimal.",
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
