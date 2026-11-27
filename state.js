import {
  DENSITIES,
  DEFAULT_CONFIG,
  DEFAULT_STATE,
  MARKDOWN_EXTENSIONS,
  PATTERNS,
  PREVIEW_MODES,
  SHAPES,
  STORAGE_CONFIG,
  STORAGE_STATE,
  STYLES,
  SURFACE_SETTINGS,
  TINTS,
} from './constants.js';

let randCounter = 0;

export function randomHex(byteLen = 8) {
  const bytes = new Uint8Array(byteLen);
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    let seed = (Date.now() ^ ((randCounter += 1) * 0x9e3779b1)) >>> 0;
    for (let i = 0; i < byteLen; i += 1) {
      seed ^= seed << 13;
      seed ^= seed >>> 17;
      seed ^= seed << 5;
      const r = Math.floor(Math.random() * 256);
      bytes[i] = (seed ^ r) & 0xff;
    }
  }
  let out = '';
  for (let i = 0; i < bytes.length; i += 1) {
    out += bytes[i].toString(16).padStart(2, '0');
  }
  return out;
}

function fallbackHexDigest16(text) {
  let h1 = 0x811c9dc5;
  let h2 = 0x9e3779b1;
  for (let i = 0; i < text.length; i += 1) {
    const c = text.charCodeAt(i);
    h1 ^= c;
    h1 = Math.imul(h1, 0x01000193) >>> 0;
    h2 ^= (c + i) & 0xff;
    h2 = Math.imul(h2, 0x85ebca6b) >>> 0;
  }
  return h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0');
}

export function normPath(p) {
  if (typeof p !== 'string' || !p) return '';
  const slash = p.replace(/\\/g, '/');
  const isAbs = slash.startsWith('/');
  const parts = [];
  for (const seg of slash.split('/')) {
    if (!seg || seg === '.') continue;
    if (seg === '..') {
      if (parts.length > 0 && parts[parts.length - 1] !== '..') {
        parts.pop();
      } else if (!isAbs) {
        parts.push('..');
      }
    } else {
      parts.push(seg);
    }
  }
  const joined = (isAbs ? '/' : '') + parts.join('/');
  return joined || (isAbs ? '/' : '.');
}

export function basename(p) {
  if (typeof p !== 'string' || !p) return '';
  const trimmed = p.replace(/[\\/]+$/, '');
  if (!trimmed) return p.startsWith('/') ? '/' : '';
  const idx = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
}

export function dirname(p) {
  if (typeof p !== 'string' || !p) return '';
  const idx = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
  if (idx < 0) return '';
  if (idx === 0) return p[0];
  return p.slice(0, idx);
}

export function extname(p) {
  const base = basename(p);
  const dot = base.lastIndexOf('.');
  if (dot <= 0) return '';
  return base.slice(dot);
}

export function stripExtension(p) {
  const ext = extname(p);
  if (!ext) return p;
  return p.slice(0, p.length - ext.length);
}

export function joinPath(dir, name) {
  if (!dir) return name;
  const sep = dir.includes('\\') && !dir.includes('/') ? '\\' : '/';
  const cleanDir = dir.replace(/[\\/]+$/, '');
  if (!cleanDir) return sep + name;
  return `${cleanDir}${sep}${name}`;
}

export function isMarkdownPath(p) {
  if (typeof p !== 'string' || !p) return false;
  return MARKDOWN_EXTENSIONS.has(extname(p).toLowerCase());
}

export function nowHHMM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function cloneDefaultConfig() {
  return {
    ...DEFAULT_CONFIG,
    selected_notebooks: [...DEFAULT_CONFIG.selected_notebooks],
  };
}

export function cloneDefaultState() {
  return {
    ...DEFAULT_STATE,
    note_counts_by_nb: {},
    logs: [],
  };
}

export function createPluginContext() {
  return {
    locale: 'zh',
    notebookRoot: '',
    downloadsDir: '',
    dataDir: '',
    hostVersion: '',
    hostTheme: 'system',
    tarotActive: false,
    capabilities: new Set(),
    config: cloneDefaultConfig(),
    state: cloneDefaultState(),
    openTargets: new Map(),
    pendingFlushToken: '',
    pendingFlushNb: '',
    lastRssBytes: 0,
  };
}

export function normalizeConfig(raw) {
  const cfg = cloneDefaultConfig();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return cfg;
  if (STYLES.includes(raw.style)) cfg.style = raw.style;
  if (SHAPES.includes(raw.shape)) cfg.shape = raw.shape;
  if (typeof raw.bg_enabled === 'boolean') cfg.bg_enabled = raw.bg_enabled;
  if (raw.bg_backdrop === 'poop-wallpaper' || raw.bg_backdrop === 'poop-watermark') {
    cfg.bg_backdrop = raw.bg_backdrop;
  }
  if (PATTERNS.includes(raw.bg_pattern)) cfg.bg_pattern = raw.bg_pattern;
  if (DENSITIES.includes(raw.bg_density)) cfg.bg_density = raw.bg_density;
  if (TINTS.includes(raw.bg_tint)) cfg.bg_tint = raw.bg_tint;
  if (typeof raw.bg_dark_glow === 'boolean') cfg.bg_dark_glow = raw.bg_dark_glow;
  if (typeof raw.caption === 'string') cfg.caption = raw.caption.slice(0, 60);
  if (typeof raw.flush_secret === 'string') cfg.flush_secret = raw.flush_secret.slice(0, 64);
  if (typeof raw.archive_dir === 'string') cfg.archive_dir = raw.archive_dir;
  if (PREVIEW_MODES.includes(raw.preview_mode)) cfg.preview_mode = raw.preview_mode;
  if (Array.isArray(raw.selected_notebooks)) {
    cfg.selected_notebooks = raw.selected_notebooks
      .filter((x) => typeof x === 'string' && x.trim())
      .map((x) => x);
  }
  if (typeof raw.notebooks_configured === 'boolean') {
    cfg.notebooks_configured = raw.notebooks_configured;
  }
  return cfg;
}

export function normalizeState(raw) {
  const st = cloneDefaultState();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return st;
  for (const key of ['total_dropped', 'total_flushed', 'bg_toggles', 'sidebar_hits', 'dialog_opens']) {
    const val = raw[key];
    if (typeof val === 'number' && Number.isInteger(val) && val >= 0) {
      st[key] = val;
    }
  }
  if (typeof raw.last_drop_at === 'string') {
    st.last_drop_at = raw.last_drop_at.slice(0, 32);
  }
  if (raw.note_counts_by_nb && typeof raw.note_counts_by_nb === 'object' && !Array.isArray(raw.note_counts_by_nb)) {
    const cleanedByNb = {};
    const entries = Object.entries(raw.note_counts_by_nb).slice(0, 64);
    for (const [nbK, nbMap] of entries) {
      if (typeof nbK !== 'string' || !nbK || !nbMap || typeof nbMap !== 'object' || Array.isArray(nbMap)) {
        continue;
      }
      const cleaned = {};
      for (const [k, v] of Object.entries(nbMap)) {
        if (typeof k === 'string' && k && typeof v === 'number' && Number.isInteger(v) && v > 0) {
          cleaned[k] = v;
        }
      }
      cleanedByNb[nbK] = cleaned;
    }
    st.note_counts_by_nb = cleanedByNb;
  }
  if (Array.isArray(raw.logs)) {
    const logs = [];
    for (const item of raw.logs.slice(0, 20)) {
      if (item && typeof item === 'object' && typeof item.event === 'string') {
        logs.push({
          event: item.event,
          note: String(item.note || ''),
          notebook_root: String(item.notebook_root || ''),
          count: Number.parseInt(item.count || 0, 10) || 0,
          time: String(item.time || ''),
          tone: String(item.tone || 'info'),
        });
      }
    }
    st.logs = logs;
  }
  return st;
}

export function nbKey(ctx) {
  return ctx.notebookRoot ? normPath(ctx.notebookRoot) : '__default__';
}

export function noteCounts(ctx) {
  if (!ctx.state.note_counts_by_nb || typeof ctx.state.note_counts_by_nb !== 'object') {
    ctx.state.note_counts_by_nb = {};
  }
  const key = nbKey(ctx);
  if (!ctx.state.note_counts_by_nb[key] || typeof ctx.state.note_counts_by_nb[key] !== 'object') {
    ctx.state.note_counts_by_nb[key] = {};
  }
  return ctx.state.note_counts_by_nb[key];
}

export function setNoteCounts(ctx, counts) {
  if (!ctx.state.note_counts_by_nb || typeof ctx.state.note_counts_by_nb !== 'object') {
    ctx.state.note_counts_by_nb = {};
  }
  ctx.state.note_counts_by_nb[nbKey(ctx)] = { ...counts };
}

export function activeCountsSummary(ctx) {
  const counts = noteCounts(ctx);
  let total = 0;
  let notes = 0;
  for (const val of Object.values(counts)) {
    if (typeof val === 'number' && val > 0) {
      total += val;
      notes += 1;
    }
  }
  return [total, notes];
}

export function safeCall(bridge, method, params = {}) {
  try {
    return bridge.callHost(method, params);
  } catch (err) {
    if (err && (err.code === -32601 || err.code === -32005)) {
      return null;
    }
    throw err;
  }
}

export function bestEffortCall(bridge, method, params = {}) {
  try {
    return bridge.callHost(method, params);
  } catch (_err) {
    return null;
  }
}

export function loadPersisted(ctx, bridge) {
  const resCfg = safeCall(bridge, 'host.storage.get', { key: STORAGE_CONFIG });
  if (resCfg && typeof resCfg === 'object' && resCfg.found) {
    ctx.config = normalizeConfig(resCfg.value);
  }
  const resSt = safeCall(bridge, 'host.storage.get', { key: STORAGE_STATE });
  if (resSt && typeof resSt === 'object' && resSt.found) {
    ctx.state = normalizeState(resSt.value);
  }
}

export function saveConfig(ctx, bridge) {
  safeCall(bridge, 'host.storage.set', { key: STORAGE_CONFIG, value: ctx.config });
}

export function saveState(ctx, bridge) {
  safeCall(bridge, 'host.storage.set', { key: STORAGE_STATE, value: ctx.state });
}

export function appendLog(ctx, { event, note = '', count = 0, tone = 'success', notebookRoot = null }) {
  const nb = notebookRoot === null ? ctx.notebookRoot : String(notebookRoot);
  ctx.state.logs.unshift({
    event,
    note,
    notebook_root: note ? nb : '',
    count: Number.parseInt(count, 10) || 0,
    time: nowHHMM(),
    tone,
  });
  ctx.state.logs = ctx.state.logs.slice(0, 20);
}

export function registerOpenTarget(ctx, bridge, notebookRoot, relPath) {
  if (!notebookRoot || !relPath || !isMarkdownPath(relPath)) {
    return '';
  }
  const text = `${notebookRoot}\0${relPath}`;
  let digest = '';
  const res = safeCall(bridge, 'host.crypto.hash', { algorithm: 'sha256', text });
  if (res && typeof res === 'object') {
    const raw = res.hex || res.hash || res.digest || '';
    if (typeof raw === 'string' && raw.trim()) {
      digest = raw.trim().slice(0, 16);
    }
  }
  if (!digest) {
    digest = fallbackHexDigest16(text);
  }
  const actionId = `open_target:${digest}`;
  if (ctx.openTargets.size >= 256 && !ctx.openTargets.has(actionId)) {
    const oldestKey = ctx.openTargets.keys().next().value;
    if (oldestKey !== undefined) {
      ctx.openTargets.delete(oldestKey);
    }
  }
  ctx.openTargets.set(actionId, [notebookRoot, relPath]);
  return actionId;
}

export function listNotebooks(ctx, bridge) {
  const res = safeCall(bridge, 'host.notebooks.list', {});
  if (res && typeof res === 'object' && Array.isArray(res.notebooks)) {
    return res.notebooks;
  }
  if (ctx.notebookRoot) {
    return [{
      path: ctx.notebookRoot,
      name: basename(ctx.notebookRoot) || ctx.notebookRoot,
      active: true,
    }];
  }
  return [];
}

export function ensureSelectedNotebooks(ctx, notebooks) {
  if (!ctx.config.notebooks_configured && ctx.config.selected_notebooks.length === 0 && notebooks.length > 0) {
    ctx.config.selected_notebooks = notebooks.map((nb) => nb && nb.path).filter(Boolean);
  }
}

export function isActiveNotebookAllowed(ctx) {
  if (!ctx.notebookRoot) return true;
  if (!ctx.config.notebooks_configured && ctx.config.selected_notebooks.length === 0) {
    return true;
  }
  return ctx.config.selected_notebooks.includes(ctx.notebookRoot);
}

export function pageValuesFor(surface, cfg) {
  if (surface === SURFACE_SETTINGS) {
    return {
      style: cfg.style,
      shape: cfg.shape,
      bg_enabled: cfg.bg_enabled,
      bg_backdrop: cfg.bg_backdrop,
      bg_pattern: cfg.bg_pattern,
      bg_density: cfg.bg_density,
      bg_tint: cfg.bg_tint,
      bg_dark_glow: cfg.bg_dark_glow,
      caption: cfg.caption,
      flush_secret: cfg.flush_secret,
      archive_dir: cfg.archive_dir,
      preview_mode: cfg.preview_mode,
      selected_notebooks: [...cfg.selected_notebooks],
    };
  }
  return {};
}
