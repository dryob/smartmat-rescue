/**
 * smartmat-card.js — Lovelace custom card for SmartMat Dashboard.
 *
 * Usage:
 *   type: custom:smartmat-card
 *   entity: sensor.smartmat_0328_inventory
 *   variant: ring | tile | liquid | minimal   # default: ring
 *   name: 貓飼料                               # optional — display override
 *   icon: mdi:cat                             # optional — default mdi:package-variant-closed
 *   controls: true                            # optional — reveal inline tare/full/rename
 *   tap_action:                               # optional — default more-info on entity
 *     action: more-info                       #   (same schema HA cards use)
 */

const VERSION = "0.3.0";
const RING_CIRCUMFERENCE = 2 * Math.PI * 42; // r=42 in a 100-box viewBox

const DEFAULT_ICON = "mdi:package-variant-closed";
const VARIANTS = new Set(["ring", "tile", "liquid", "minimal"]);

/* ---------- utilities ---------- */

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
  if (!iso || ["unknown", "unavailable", "none", ""].includes(iso)) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return String(iso);
  const diffSec = (t - Date.now()) / 1000;
  const abs = Math.abs(diffSec);
  if (!REL) return `${Math.round(abs / 60)} min ago`;
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

function isUsableState(s) {
  return s != null && !["unknown", "unavailable", "none", ""].includes(s);
}

function fireMoreInfo(el, entityId) {
  el.dispatchEvent(
    new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    })
  );
}

/* ---------- shared CSS (injected once) ---------- */

const STYLE_ID = "smartmat-card-styles";

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement("style");
  s.id = STYLE_ID;
  s.textContent = `
  .smc {
    --smc-color: var(--primary-color);
    --smc-color-soft: color-mix(in srgb, var(--smc-color) 14%, transparent);
    padding: 14px 16px 12px;
    position: relative;
    cursor: pointer;
    user-select: none;
  }
  .smc.no-tap { cursor: default; }
  .smc .header {
    display: flex; align-items: center; gap: 8px;
    min-width: 0;
  }
  .smc .icon {
    --mdc-icon-size: 22px;
    color: var(--smc-color);
    flex-shrink: 0;
    transition: color 0.25s ease;
  }
  .smc .title {
    flex: 1; min-width: 0;
    font-size: 15px; font-weight: 500;
    color: var(--primary-text-color);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    padding: 2px 0;
    margin: 0;
    background: transparent;
    border: none;
  }
  .smc input.title {
    border-bottom: 1px dashed transparent;
  }
  .smc input.title:hover { border-bottom-color: var(--divider-color); }
  .smc input.title:focus { outline: none; border-bottom-color: var(--smc-color); }

  /* =============== RING variant =============== */
  .smc-v-ring .ring-wrap {
    position: relative;
    width: 150px; height: 150px;
    margin: 6px auto 2px;
  }
  .smc-v-ring .ring {
    width: 100%; height: 100%;
    transform: rotate(-90deg);
  }
  .smc-v-ring .ring circle {
    fill: none;
    stroke-width: 10;
    stroke-linecap: round;
  }
  .smc-v-ring .ring .track {
    stroke: var(--divider-color);
    opacity: 0.35;
  }
  .smc-v-ring .ring .fill {
    stroke: var(--smc-color);
    stroke-dasharray: ${RING_CIRCUMFERENCE};
    stroke-dashoffset: ${RING_CIRCUMFERENCE};
    transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1),
                stroke 0.25s ease;
  }
  .smc-v-ring .center {
    position: absolute; inset: 0;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    pointer-events: none;
  }
  .smc-v-ring .pct {
    font-size: 36px; font-weight: 700;
    line-height: 1;
    color: var(--primary-text-color);
    letter-spacing: -1px;
  }
  .smc-v-ring .pct-unit {
    font-size: 12px;
    color: var(--secondary-text-color);
    margin-top: 4px;
    letter-spacing: 1px;
  }
  .smc-v-ring .pill {
    display: flex; justify-content: center;
    margin: 8px 0 4px;
  }
  .smc-v-ring .pill-inner {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 13px; font-weight: 500;
    background: var(--smc-color-soft);
    color: var(--smc-color);
    transition: background 0.25s ease, color 0.25s ease;
  }
  .smc-v-ring .pill-inner .sep { opacity: 0.5; }
  .smc-v-ring .pill-inner .emoji { font-size: 14px; }
  .smc-v-ring .foot {
    text-align: center;
    font-size: 11px;
    color: var(--secondary-text-color);
    opacity: 0.75;
    margin-top: 2px;
  }

  /* =============== TILE variant =============== */
  .smc-v-tile { padding: 12px 14px 8px; }
  .smc-v-tile .tile-row {
    display: flex; align-items: center; gap: 12px;
    min-width: 0;
  }
  .smc-v-tile .tile-icon {
    width: 40px; height: 40px;
    border-radius: 50%;
    background: var(--smc-color-soft);
    color: var(--smc-color);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: background 0.25s ease, color 0.25s ease;
  }
  .smc-v-tile .tile-icon ha-icon { --mdc-icon-size: 22px; }
  .smc-v-tile .tile-info { flex: 1; min-width: 0; }
  .smc-v-tile .tile-info .title { padding: 0; }
  .smc-v-tile .subline {
    display: flex; align-items: baseline; gap: 6px;
    font-size: 12px;
    color: var(--secondary-text-color);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    margin-top: 2px;
  }
  .smc-v-tile .subline .pct-inline {
    font-weight: 600;
    color: var(--smc-color);
    font-size: 13px;
    transition: color 0.25s ease;
  }
  .smc-v-tile .subline .sep { opacity: 0.5; }
  .smc-v-tile .tile-status { font-size: 18px; flex-shrink: 0; }
  .smc-v-tile .bar {
    height: 4px; border-radius: 2px;
    background: color-mix(in srgb, var(--divider-color) 60%, transparent);
    margin-top: 10px;
    overflow: hidden;
  }
  .smc-v-tile .bar-fill {
    height: 100%; width: 0;
    background: var(--smc-color);
    border-radius: 2px;
    transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1),
                background 0.25s ease;
  }

  /* =============== LIQUID variant =============== */
  .smc-v-liquid { padding: 0; overflow: hidden; }
  .smc-v-liquid .liquid-wrap {
    position: relative;
    padding: 14px 16px 12px;
    overflow: hidden;
  }
  .smc-v-liquid .liquid-fill {
    position: absolute;
    left: 0; right: 0; bottom: 0;
    height: 0%;
    background: linear-gradient(
      to top,
      color-mix(in srgb, var(--smc-color) 40%, transparent) 0%,
      color-mix(in srgb, var(--smc-color) 18%, transparent) 100%
    );
    transition: height 0.9s cubic-bezier(0.4, 0, 0.2, 1),
                background 0.25s ease;
    pointer-events: none;
  }
  .smc-v-liquid .liquid-content {
    position: relative; z-index: 1;
    display: flex; flex-direction: column; gap: 8px;
  }
  .smc-v-liquid .big-row {
    display: flex; align-items: baseline; justify-content: center;
    gap: 4px;
    margin-top: 6px;
  }
  .smc-v-liquid .pct-big {
    font-size: 48px; font-weight: 700;
    line-height: 1;
    color: var(--primary-text-color);
    letter-spacing: -2px;
  }
  .smc-v-liquid .pct-unit {
    font-size: 16px;
    color: var(--secondary-text-color);
    margin-right: 6px;
  }
  .smc-v-liquid .emoji-big { font-size: 24px; }
  .smc-v-liquid .meta {
    display: flex; align-items: center; justify-content: center;
    gap: 6px;
    font-size: 12px;
    color: var(--secondary-text-color);
    flex-wrap: wrap;
  }
  .smc-v-liquid .meta .sep { opacity: 0.5; }

  /* =============== MINIMAL variant =============== */
  .smc-v-minimal .header .emoji-tl { font-size: 18px; margin-left: 4px; }
  .smc-v-minimal .pct-huge {
    font-size: 56px; font-weight: 700;
    line-height: 1;
    color: var(--primary-text-color);
    letter-spacing: -2px;
    text-align: center;
    margin: 10px 0 4px;
  }
  .smc-v-minimal .pct-huge .pct-unit-mini {
    font-size: 20px;
    color: var(--secondary-text-color);
    font-weight: 500;
    letter-spacing: 0;
    margin-left: 4px;
  }
  .smc-v-minimal .bar {
    height: 3px; border-radius: 2px;
    background: color-mix(in srgb, var(--divider-color) 60%, transparent);
    overflow: hidden;
    margin: 6px 0 8px;
  }
  .smc-v-minimal .bar-fill {
    height: 100%; width: 0;
    background: var(--smc-color);
    border-radius: 2px;
    transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1),
                background 0.25s ease;
  }
  .smc-v-minimal .foot-min {
    display: flex; align-items: center; justify-content: center;
    gap: 6px;
    font-size: 12px;
    color: var(--secondary-text-color);
  }
  .smc-v-minimal .foot-min .sep { opacity: 0.5; }

  /* =============== Controls (shared across variants) =============== */
  .smc .calib {
    display: flex; gap: 8px;
    margin-top: 10px;
  }
  .smc .calib .fld {
    flex:1; display:flex; align-items:center; gap:4px;
    font-size:12px; color:var(--secondary-text-color);
    background: var(--secondary-background-color);
    border-radius: 8px;
    padding: 4px 8px;
  }
  .smc .calib .fld .lbl { flex-shrink:0; }
  .smc .calib .fld input {
    flex:1; min-width:0; padding:2px 4px;
    background: var(--card-background-color);
    border:1px solid var(--divider-color);
    border-radius:4px;
    color:var(--primary-text-color);
    font-size: 12px;
    text-align: right;
  }
  .smc .calib .fld .unit { flex-shrink:0; opacity:0.7; }

  /* Error state */
  .smc-error {
    padding: 14px;
    color: var(--error-color, #b00020);
    font-size: 13px;
  }
  `;
  document.head.appendChild(s);
}

/* ---------- colour / level helpers ---------- */

function levelFor(pct, critical, low, mid, hasPct) {
  if (!hasPct) {
    return {
      key: "unknown",
      emoji: "—",
      label: "無資料",
      color: "var(--disabled-color, #9e9e9e)",
    };
  }
  if (pct < critical) {
    return {
      key: "critical",
      emoji: "🚨",
      label: "快用完",
      color: "var(--error-color, #d32f2f)",
    };
  }
  if (pct < low) {
    return {
      key: "low",
      emoji: "⚠️",
      label: "低",
      color: "var(--warning-color, #ef6c00)",
    };
  }
  if (pct < mid) {
    return {
      key: "mid",
      emoji: "🟡",
      label: "中",
      color: "#f9a825",
    };
  }
  return {
    key: "full",
    emoji: "✅",
    label: "充足",
    color: "var(--success-color, #2e7d32)",
  };
}

/* ---------- the card ---------- */

class SmartMatCard extends HTMLElement {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._built = false;
    this._variant = "ring";
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error(
        "smartmat-card: 'entity' is required (a sensor.smartmat_*_inventory)"
      );
    }
    const variant = VARIANTS.has(config.variant) ? config.variant : "ring";
    // Re-build if variant / controls / icon changed
    const prev = this._config || {};
    const structuralChanged =
      prev.variant !== variant ||
      !!prev.controls !== !!config.controls ||
      (prev.icon || DEFAULT_ICON) !== (config.icon || DEFAULT_ICON);

    this._config = { ...config };
    this._variant = variant;
    if (structuralChanged) this._built = false;
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
      Object.keys(hass.states).find(
        (k) => k.startsWith("sensor.smartmat_") && k.endsWith("_inventory")
      );
    return {
      entity: first || "sensor.smartmat_XXXX_inventory",
      variant: "ring",
    };
  }

  getCardSize() {
    const controlsPad = this._config && this._config.controls ? 1 : 0;
    const base = { ring: 4, tile: 2, liquid: 4, minimal: 3 }[this._variant] || 3;
    return base + controlsPad;
  }

  /* ---------- build / render ---------- */

  _buildVariantHtml(variant, icon) {
    switch (variant) {
      case "tile":
        return `
          <div class="tile-row">
            <div class="tile-icon">
              <ha-icon class="icon" icon="${icon}"></ha-icon>
            </div>
            <div class="tile-info">
              ${this._titleHtml()}
              <div class="subline">
                <span class="pct-inline">—</span>
                <span class="sep">·</span>
                <span class="weight">—</span>
                <span class="sep">·</span>
                <span class="seen-inline">—</span>
              </div>
            </div>
            <div class="tile-status">
              <span class="emoji">—</span>
            </div>
          </div>
          <div class="bar"><div class="bar-fill"></div></div>
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
              <div class="big-row">
                <span class="pct-big">—</span>
                <span class="pct-unit">%</span>
                <span class="emoji-big">—</span>
              </div>
              <div class="meta">
                <span class="weight">—</span>
                <span class="sep">·</span>
                <span class="label">—</span>
                <span class="sep">·</span>
                <span class="seen-inline">—</span>
              </div>
            </div>
          </div>
        `;

      case "minimal":
        return `
          <div class="header">
            ${this._titleHtml()}
            <span class="emoji-tl">—</span>
          </div>
          <div class="pct-huge">
            <span class="pct">—</span><span class="pct-unit-mini">%</span>
          </div>
          <div class="bar"><div class="bar-fill"></div></div>
          <div class="foot-min">
            <span class="weight">—</span>
            <span class="sep">·</span>
            <span class="seen-inline">—</span>
          </div>
        `;

      default: // ring
        return `
          <div class="header">
            <ha-icon class="icon" icon="${icon}"></ha-icon>
            ${this._titleHtml()}
          </div>
          <div class="ring-wrap">
            <svg viewBox="0 0 100 100" class="ring" aria-hidden="true">
              <circle class="track" cx="50" cy="50" r="42"></circle>
              <circle class="fill"  cx="50" cy="50" r="42"></circle>
            </svg>
            <div class="center">
              <div class="pct">—</div>
              <div class="pct-unit">%</div>
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

  _titleHtml() {
    const controls = !!this._config.controls;
    return controls
      ? `<input class="title" type="text" placeholder="未設定" aria-label="商品名" />`
      : `<div class="title"></div>`;
  }

  _calibHtml() {
    if (!this._config.controls) return "";
    return `
      <div class="calib">
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
    `;
  }

  _build() {
    ensureStyles();
    const variant = this._variant;
    const icon = this._config.icon || DEFAULT_ICON;
    const hasTap = this._hasTapAction();

    this.innerHTML = `
      <ha-card>
        <div class="smc smc-v-${variant} ${hasTap ? "" : "no-tap"}">
          ${this._buildVariantHtml(variant, icon)}
          ${this._calibHtml()}
        </div>
      </ha-card>
    `;

    const q = (sel) => this.querySelector(sel);
    this._el = {
      smc: q(".smc"),
      title: q(".title"),
      icon: q(".icon"),
      // ring
      ringFill: q(".ring .fill"),
      pctRing: q(".smc-v-ring .pct"),
      pillInner: q(".pill-inner"),
      // tile
      pctInline: q(".pct-inline"),
      tileStatusEmoji: q(".tile-status .emoji"),
      barFill: q(".bar-fill"),
      // liquid
      liquidFill: q(".liquid-fill"),
      pctBig: q(".pct-big"),
      emojiBig: q(".emoji-big"),
      // minimal
      emojiTl: q(".emoji-tl"),
      pctHuge: q(".pct-huge .pct"),
      // shared text targets (some variants)
      emoji: this.querySelector(".pill-inner .emoji") || this.querySelector(".liquid-content .label")?.previousElementSibling,
      label: q(".pill-inner .label") || q(".liquid-content .label"),
      weight: this.querySelectorAll(".weight"),
      seenInline: this.querySelectorAll(".seen-inline"),
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
    this._el.title.addEventListener("change", () => {
      const eid = this._runtime && this._runtime.productEid;
      call("text", eid, this._el.title.value);
    });
    this._el.tare.addEventListener("change", () => {
      const eid = this._runtime && this._runtime.tareEid;
      call("number", eid, this._el.tare.value);
    });
    this._el.full.addEventListener("change", () => {
      const eid = this._runtime && this._runtime.fullEid;
      call("number", eid, this._el.full.value);
    });
  }

  _wireTap() {
    if (!this._hasTapAction()) return;
    this._el.smc.addEventListener("click", (e) => {
      // Don't trigger on interactive descendants
      if (e.target.closest("input, button, ha-textfield")) return;
      const entity = this._config.entity;
      if (entity) fireMoreInfo(this, entity);
    });
  }

  _hasTapAction() {
    // Default: more-info. User can set tap_action.action = "none" to disable.
    const t = this._config && this._config.tap_action;
    if (!t) return true;
    return t.action !== "none";
  }

  _renderError(msg) {
    this.innerHTML = `<ha-card><div class="smc-error">${msg}</div></ha-card>`;
    this._built = false;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const invEid = this._config.entity;
    const inv = this._hass.states[invEid];
    if (!inv) {
      this._renderError(
        `Entity <code>${invEid}</code> not found. Add a mat via the SmartMat Dashboard integration first.`
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

    // Weight display
    const rawW = getStateStr(this._hass, weightEid, null);
    let weightDisplay;
    if (isUsableState(rawW)) {
      const f = parseFloat(rawW);
      weightDisplay = Number.isNaN(f) ? `${rawW} g` : `${Math.round(f)} g`;
    } else {
      weightDisplay = "— g";
    }

    const productName =
      this._config.name ||
      getStateStr(this._hass, productEid, `Mat ${sid}`) ||
      `Mat ${sid}`;

    const lastSeenStr = fmtRel(getStateStr(this._hass, lastSeenEid, null));

    // Apply accent colour
    this._el.smc.style.setProperty("--smc-color", lv.color);

    // Product title (input vs div)
    const ae = document.activeElement;
    if (this._el.title.tagName === "INPUT") {
      if (ae !== this._el.title) this._el.title.value = productName;
    } else {
      this._el.title.textContent = productName;
    }

    // Tare / Full — only when controls are enabled
    if (this._el.tare) {
      const v = getStateStr(this._hass, tareEid, "0");
      if (ae !== this._el.tare) this._el.tare.value = v;
    }
    if (this._el.full) {
      const v = getStateStr(this._hass, fullEid, "1000");
      if (ae !== this._el.full) this._el.full.value = v;
    }

    // Per-variant paint
    switch (this._variant) {
      case "tile":
        this._el.pctInline.textContent = hasPct ? `${pctRound}%` : "—";
        this._el.tileStatusEmoji.textContent = lv.emoji;
        this._el.barFill.style.width = hasPct ? `${pct}%` : "0%";
        this._paintWeightSeen(weightDisplay, lastSeenStr);
        break;

      case "liquid":
        this._el.liquidFill.style.height = hasPct ? `${pct}%` : "0%";
        this._el.pctBig.textContent = hasPct ? String(pctRound) : "—";
        this._el.emojiBig.textContent = lv.emoji;
        if (this._el.label) this._el.label.textContent = lv.label;
        this._paintWeightSeen(weightDisplay, lastSeenStr);
        break;

      case "minimal":
        this._el.emojiTl.textContent = lv.emoji;
        this._el.pctHuge.textContent = hasPct ? String(pctRound) : "—";
        this._el.barFill.style.width = hasPct ? `${pct}%` : "0%";
        this._paintWeightSeen(weightDisplay, lastSeenStr);
        break;

      default: // ring
        this._el.pctRing.textContent = hasPct ? String(pctRound) : "—";
        if (this._el.emoji) this._el.emoji.textContent = lv.emoji;
        if (this._el.label) this._el.label.textContent = lv.label;
        if (this._el.ringFill) {
          const offset = RING_CIRCUMFERENCE * (1 - pct / 100);
          this._el.ringFill.style.strokeDashoffset = String(offset);
        }
        if (this._el.foot) {
          this._el.foot.textContent = `上報 ${lastSeenStr}`;
        }
        this._paintWeightSeen(weightDisplay, lastSeenStr);
        break;
    }
  }

  _paintWeightSeen(weightDisplay, lastSeenStr) {
    this._el.weight.forEach((el) => (el.textContent = weightDisplay));
    this._el.seenInline.forEach((el) => (el.textContent = lastSeenStr));
  }
}

/* ---------- editor ---------- */

const EDITOR_SCHEMA = [
  {
    name: "entity",
    required: true,
    selector: {
      entity: {
        filter: { domain: "sensor", integration: "smartmat_dashboard" },
      },
    },
  },
  {
    name: "variant",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { label: "Ring + Pill (預設)", value: "ring" },
          { label: "Tile (緊湊橫式)", value: "tile" },
          { label: "Liquid Fill (瓶罐填充)", value: "liquid" },
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
          "預設 <b>Show inline controls</b> 關:card 只顯示狀態,設定在 " +
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
          SmartMat card editor failed (${String(e && e.message || e)}).
          Edit the YAML directly — the card itself works fine.
        </div>
      `;
    }
  }

  _onChange(ev) {
    const v = (ev && ev.detail && ev.detail.value) || {};
    const newConfig = {
      type: "custom:smartmat-card",
      entity: v.entity || "",
    };
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
      "SmartMat Lite per-mat inventory tile — choose ring / tile / liquid / minimal layout.",
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
