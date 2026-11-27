import {
  ALL_SURFACES,
  DENSITIES,
  DENSITY_OPACITY,
  MAX_SIDEBAR_BADGES,
  PATTERNS,
  PREVIEW_MODES,
  SHAPES,
  STYLES,
  SURFACE_DIALOG,
  SURFACE_PANEL,
  SURFACE_SETTINGS,
  SURFACE_SIDEBAR,
  TINTS,
} from './constants.js';
import { formatMessage, getStrings, isEn } from './i18n.js';
import { buildDropBlock } from './markdown.js';
import {
  activeCountsSummary,
  appendLog,
  basename,
  bestEffortCall,
  dirname,
  isMarkdownPath,
  noteCounts,
  registerOpenTarget,
  saveConfig,
  saveState,
  stripExtension,
} from './state.js';

export function syncHostUI(ctx, bridge) {
  const t = getStrings(ctx.locale);
  const [total, noteN] = activeCountsSummary(ctx);

  bestEffortCall(bridge, 'host.ui.set_backdrop', {
    id: ctx.config.bg_backdrop,
    enabled: Boolean(ctx.config.bg_enabled),
    pattern: ctx.config.bg_pattern,
    density: ctx.config.bg_density,
    opacity: DENSITY_OPACITY[ctx.config.bg_density] ?? 0.1,
    tint: ctx.config.bg_tint,
    dark_glow: Boolean(ctx.config.bg_dark_glow),
  });

  const badgeStr = total > 0 ? String(Math.min(total, 999)) : '';
  bestEffortCall(bridge, 'host.titlebar.set_button', {
    id: 'poop-panel',
    badge: badgeStr,
  });

  const stText = total > 0 ? formatMessage(t.status_count, { n: total }) : t.status_clean;
  const stTip = total > 0
    ? formatMessage(t.status_tip_count, { n: total, notes: noteN })
    : t.status_tip_clean;
  bestEffortCall(bridge, 'host.status.set', {
    id: 'poop-counter',
    text: stText,
    tooltip: stTip,
    show_plugin_icon: true,
  });

  if (ctx.notebookRoot) {
    const entries = {};
    const ranked = Object.entries(noteCounts(ctx))
      .filter(([, cnt]) => cnt > 0)
      .sort((a, b) => (b[1] - a[1]) || (a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : 0)))
      .slice(0, MAX_SIDEBAR_BADGES);
    for (const [rel, cnt] of ranked) {
      entries[rel] = {
        text: String(Math.min(cnt, 999)),
        tooltip: formatMessage(t.badge_tip_note, { n: cnt }),
        tone: cnt >= 5 ? 'warning' : 'accent',
      };
    }
    bestEffortCall(bridge, 'host.sidebar.set_badges', {
      badge_id: 'poop-mark',
      entries,
      clear: ranked.length === 0,
    });
  }
}

export function refreshOtherSurfaces(bridge, currentSurface = '') {
  for (const surf of ALL_SURFACES) {
    if (surf === currentSurface) continue;
    bestEffortCall(bridge, 'host.ui.refresh', { surface: surf });
  }
}

export function showToast(bridge, message, tone = 'info') {
  bestEffortCall(bridge, 'host.ui.toast', { message, tone });
}

export function reportProgress(ctx, bridge, done, total, label = '') {
  if (!ctx.capabilities.has('action_progress')) return;
  const payload = { done: Number.parseInt(done, 10) || 0, total: Number.parseInt(total, 10) || 0 };
  if (label) payload.label = label;
  bridge.notifyHost('host.action.progress', payload);
}

export function renderLogEntry(ctx, bridge, entry) {
  const t = getStrings(ctx.locale);
  const ev = entry.event || '';
  const note = entry.note || '';
  const cnt = Number.parseInt(entry.count || 0, 10) || 0;
  const tm = entry.time || '';
  const tone = entry.tone || 'info';

  let title;
  let status;
  if (ev === 'drop') {
    title = formatMessage(t.log_drop, { note, n: cnt });
    status = t.log_status_ok;
  } else if (ev === 'wrap') {
    title = formatMessage(t.log_wrap, { note });
    status = t.log_status_ok;
  } else if (ev === 'flush_note') {
    title = formatMessage(t.log_flush_note, { note, n: cnt });
    status = t.log_status_clean;
  } else if (ev === 'flush_all') {
    title = formatMessage(t.log_flush_all, { n: cnt });
    status = t.log_status_clean;
  } else if (ev === 'bg_on') {
    title = t.log_bg_on;
    status = t.log_status_info;
  } else if (ev === 'bg_off') {
    title = t.log_bg_off;
    status = t.log_status_info;
  } else if (ev === 'blocked') {
    title = formatMessage(t.log_blocked, { note });
    status = t.log_status_warn;
  } else if (ev === 'saved') {
    title = t.log_saved;
    status = t.log_status_ok;
  } else if (ev === 'theme') {
    title = t.log_theme;
    status = t.log_status_info;
  } else if (ev === 'note_saved') {
    title = formatMessage(t.log_note_saved, { note, n: cnt });
    status = t.log_status_info;
  } else {
    title = ev || 'event';
    status = t.log_status_info;
  }

  const out = { title, time: tm, status, tone };
  const entryNb = String(entry.notebook_root || '');
  if (entryNb && note && isMarkdownPath(note) && ctx.capabilities.has('log_actions')) {
    const actId = registerOpenTarget(ctx, bridge, entryNb, note);
    if (actId) {
      out.action_id = actId;
      out.tooltip = formatMessage(t.click_to_open, { note });
    }
  }
  return out;
}

export function buildPreviewItem(ctx) {
  const t = getStrings(ctx.locale);
  const mode = ctx.config.preview_mode || 'article';
  const [total, notes] = activeCountsSummary(ctx);
  const sampleBlock = buildDropBlock({
    caption: ctx.config.caption,
    style: ctx.config.style,
    shape: ctx.config.shape,
    locale: ctx.locale,
  });
  const palette = ctx.config.bg_tint === 'warm' ? 'warm' : (ctx.config.bg_dark_glow ? 'ink' : 'paper');

  if (mode === 'diff') {
    return {
      kind: 'preview',
      preview: {
        variant: 'diff',
        palette,
        title: t.pv_diff_title,
        badge: t.pv_badge,
        before: `# Sample Note\n${sampleBlock}\nUser paragraph remains intact.`,
        after: '# Sample Note\nUser paragraph remains intact.',
      },
    };
  }
  if (mode === 'cards') {
    const cards = isEn(ctx.locale)
      ? [
          { badge: 'Titlebar', title: '3 Buttons + Badges', body: 'Panel toggle, instant drop, and flush modal' },
          { badge: 'Sidebar', title: 'Section + File Badges', body: 'Collapsible card, row counters, and tree menu' },
          { badge: 'Backdrop', title: 'Vector Motifs', body: `${ctx.config.bg_pattern} / ${ctx.config.bg_density} / safe opacity` },
        ]
      : [
          { badge: '顶栏', title: '3 按钮 + 动态角标', body: '面板开关、快捷拉一坨与确认冲水' },
          { badge: '侧栏', title: '侧栏分区 + 文件树角标', body: '可折叠战报、行尾数字与右键菜单' },
          { badge: '背景', title: '自定义矢量水印', body: `${t.patterns[ctx.config.bg_pattern]} · ${t.densities[ctx.config.bg_density]}` },
        ];
    return {
      kind: 'preview',
      preview: {
        variant: 'cards',
        palette: 'ocean',
        title: t.pv_cards_title,
        badge: t.card_map_badge,
        cards,
      },
    };
  }
  if (mode === 'plan') {
    const body = isEn(ctx.locale)
      ? (
          `1. Scan ${Math.max(notes, 1)} note(s) via host.notes.read\n` +
          `2. Strip ${total} signed drop line(s) using expected_revision\n` +
          '3. Clear sidebar badges, titlebar badge, and backdrop\n' +
          '4. Sync status bar and notify with icon toast'
        )
      : (
          `1. 通过 host.notes.read 扫描 ${Math.max(notes, 1)} 篇笔记\n` +
          `2. 携带 expected_revision 精确移除 ${total} 条专属标记行\n` +
          '3. 清空文件树角标、顶栏角标与编辑区背景\n' +
          '4. 同步状态栏并弹出带图标 Toast'
        );
    return {
      kind: 'preview',
      preview: {
        variant: 'plan',
        palette: 'ocean',
        title: t.pv_plan_title,
        badge: t.pv_badge,
        body,
      },
    };
  }
  return {
    kind: 'preview',
    preview: {
      variant: 'article',
      palette,
      title: t.pv_title,
      badge: t.pv_badge,
      subtitle: `${t.styles[ctx.config.style]} / ${t.shapes[ctx.config.shape]}`,
      body: `# ${t.title}\n## ${t.shapes[ctx.config.shape]}\n${sampleBlock}`,
    },
  };
}

export function mergeFormValues(ctx, bridge, values, surface) {
  if (!values || typeof values !== 'object' || Array.isArray(values) || Object.keys(values).length === 0) {
    return false;
  }
  let changed = false;
  let bgChanged = false;
  const isSettings = surface === SURFACE_SETTINGS;
  const prevBgEnabled = ctx.config.bg_enabled;

  const stringFields = [
    ['style', STYLES],
    ['shape', SHAPES],
    ['bg_backdrop', ['poop-wallpaper', 'poop-watermark']],
    ['bg_pattern', PATTERNS],
    ['bg_density', DENSITIES],
    ['bg_tint', TINTS],
    ['preview_mode', PREVIEW_MODES],
  ];
  for (const [key, allowed] of stringFields) {
    const isBackground = key.startsWith('bg_');
    if (isBackground && !isSettings) continue;
    const val = values[key];
    if (typeof val === 'string' && allowed.includes(val) && ctx.config[key] !== val) {
      ctx.config[key] = val;
      changed = true;
      bgChanged = bgChanged || isBackground;
    }
  }

  if (isSettings) {
    for (const key of ['bg_enabled', 'bg_dark_glow']) {
      const val = values[key];
      if (typeof val === 'boolean' && ctx.config[key] !== val) {
        ctx.config[key] = val;
        changed = true;
        bgChanged = true;
      }
    }
  }

  if (typeof values.caption === 'string' && values.caption.slice(0, 60) !== ctx.config.caption) {
    ctx.config.caption = values.caption.slice(0, 60);
    changed = true;
  }
  if (typeof values.flush_secret === 'string' && values.flush_secret.slice(0, 64) !== ctx.config.flush_secret) {
    ctx.config.flush_secret = values.flush_secret.slice(0, 64);
    changed = true;
  }
  if (typeof values.archive_dir === 'string' && values.archive_dir !== ctx.config.archive_dir) {
    ctx.config.archive_dir = values.archive_dir;
    changed = true;
  }
  if (Array.isArray(values.selected_notebooks)) {
    const nextNbs = values.selected_notebooks.filter((x) => typeof x === 'string' && x.trim());
    const sameLen = nextNbs.length === ctx.config.selected_notebooks.length;
    const sameItems = sameLen && nextNbs.every((x, i) => x === ctx.config.selected_notebooks[i]);
    if (!sameItems || !ctx.config.notebooks_configured) {
      ctx.config.selected_notebooks = nextNbs;
      ctx.config.notebooks_configured = true;
      changed = true;
    }
  }

  if (changed) {
    saveConfig(ctx, bridge);
  }
  if (bgChanged) {
    if (ctx.config.bg_enabled !== prevBgEnabled) {
      ctx.state.bg_toggles += 1;
      appendLog(ctx, { event: ctx.config.bg_enabled ? 'bg_on' : 'bg_off', tone: 'info' });
      saveState(ctx, bridge);
    }
    syncHostUI(ctx, bridge);
    refreshOtherSurfaces(bridge, surface);
  }
  return changed;
}

export function renderSettingsPage(ctx) {
  const t = getStrings(ctx.locale);
  return {
    title: t.title,
    status: '',
    cards: [
      {
        id: 'how-card',
        title: t.card_how,
        items: [
          {
            kind: 'segmented',
            id: 'style',
            label: t.lbl_style,
            value: ctx.config.style,
            options: STYLES.map((v) => ({ value: v, label: t.styles[v] })),
          },
          {
            kind: 'switch',
            id: 'bg_enabled',
            label: t.lbl_bg_enabled,
            value: ctx.config.bg_enabled,
          },
          {
            kind: 'input',
            id: 'caption',
            label: t.lbl_caption,
            value: ctx.config.caption,
            placeholder: t.ph_caption,
          },
          {
            kind: 'actions',
            buttons: [
              { id: 'save_prefs', label: t.act_save, variant: 'primary' },
              { id: 'open_flush', label: t.act_flush_all, variant: 'danger' },
            ],
          },
        ],
      },
    ],
  };
}

export function renderPanel(ctx, bridge) {
  const t = getStrings(ctx.locale);
  const [total, notes] = activeCountsSummary(ctx);
  const counts = noteCounts(ctx);
  const ranked = Object.entries(counts)
    .filter(([, cnt]) => cnt > 0)
    .sort((a, b) => (b[1] - a[1]) || (a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : 0)))
    .slice(0, 8);
  const maxCnt = ranked.reduce((mx, [, cnt]) => Math.max(mx, cnt), 1);
  const noteRows = [];
  for (const [rel, cnt] of ranked) {
    const row = {
      title: basename(rel),
      sub_text: dirname(rel),
      status: formatMessage(t.m_unit_drop, { n: cnt }),
      tone: cnt >= 5 ? 'ai_sessions' : 'notes',
      ratio: Math.min(1.0, Math.max(0.08, cnt / maxCnt)),
      tooltip: formatMessage(t.click_to_open, { note: rel }),
    };
    if (ctx.capabilities.has('log_actions') && ctx.notebookRoot) {
      const actId = registerOpenTarget(ctx, bridge, ctx.notebookRoot, rel);
      if (actId) row.action_id = actId;
    }
    noteRows.push(row);
  }

  return {
    title: t.panel_title,
    cards: [
      {
        id: 'panel-stats',
        title: t.card_panel_stats,
        items: [
          {
            kind: 'metrics',
            metrics: [
              { label: t.m_active, value: formatMessage(t.m_unit_drop, { n: total }), tone: 'ai_sessions' },
              { label: t.m_notes, value: formatMessage(t.m_unit_note, { n: notes }), tone: 'notes' },
            ],
          },
        ],
      },
      {
        id: 'panel-drops',
        title: t.card_panel_recent,
        items: [
          {
            kind: 'log_list',
            id: 'panel-note-list',
            empty_text: t.lbl_logs_empty,
            entries: noteRows,
          },
          {
            kind: 'actions',
            buttons: [
              { id: 'panel_drop', label: t.act_drop_cursor, variant: 'primary' },
              { id: 'panel_flush_page', label: t.act_flush_page, variant: 'secondary' },
              { id: 'panel_open_flush', label: t.act_flush_all, variant: 'danger' },
            ],
          },
        ],
      },
    ],
  };
}

export function renderSidebarSection(ctx, bridge) {
  const t = getStrings(ctx.locale);
  const ranked = Object.entries(noteCounts(ctx))
    .filter(([, cnt]) => cnt > 0)
    .sort((a, b) => (b[1] - a[1]) || (a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : 0)))
    .slice(0, 5);
  const entries = [];
  for (const [rel, cnt] of ranked) {
    const item = {
      title: stripExtension(basename(rel)),
      time: formatMessage(t.m_unit_drop, { n: cnt }),
      tone: cnt >= 5 ? 'warning' : 'accent',
      tooltip: formatMessage(t.click_to_open, { note: rel }),
    };
    if (ctx.capabilities.has('log_actions') && ctx.notebookRoot) {
      const actId = registerOpenTarget(ctx, bridge, ctx.notebookRoot, rel);
      if (actId) item.action_id = actId;
    }
    entries.push(item);
  }
  return {
    title: t.sidebar_title,
    cards: [
      {
        id: 'sidebar-drops',
        title: t.sidebar_title,
        items: [
          {
            kind: 'log_list',
            id: 'sidebar-drop-list',
            empty_text: t.lbl_sidebar_empty,
            entries,
          },
          {
            kind: 'actions',
            buttons: [
              { id: 'sidebar_drop', label: t.act_drop_now, variant: 'primary' },
            ],
          },
        ],
      },
    ],
  };
}

export function renderFlushDialog(ctx) {
  const t = getStrings(ctx.locale);
  const [total, notes] = activeCountsSummary(ctx);
  const items = [
    {
      kind: 'metrics',
      metrics: [
        { label: t.m_active, value: formatMessage(t.m_unit_drop, { n: total }), tone: 'ai_sessions' },
        { label: t.m_notes, value: formatMessage(t.m_unit_note, { n: notes }), tone: 'notes' },
      ],
    },
    {
      kind: 'preview',
      preview: {
        variant: 'diff',
        palette: 'warm',
        title: t.pv_diff_title,
        badge: t.pv_badge,
        before: formatMessage(t.dialog_desc_before, { n: total, notes }),
        after: t.dialog_desc_after,
      },
    },
  ];
  if (ctx.config.flush_secret) {
    items.push({
      kind: 'secret',
      id: 'confirm_secret',
      label: t.lbl_confirm_secret,
      value: '',
      placeholder: t.ph_confirm_secret,
    });
  }
  items.push({
    kind: 'actions',
    buttons: [
      { id: 'dialog_keep', label: t.act_keep, variant: 'secondary' },
      { id: 'dialog_flush_confirm', label: t.act_confirm_flush, variant: 'danger' },
    ],
  });
  return {
    title: t.dialog_title,
    cards: [
      {
        id: 'flush-confirm-card',
        title: t.card_dialog,
        items,
      },
    ],
  };
}

export function renderSurface(ctx, bridge, surface) {
  if (surface === SURFACE_SETTINGS) return renderSettingsPage(ctx);
  if (surface === SURFACE_PANEL) return renderPanel(ctx, bridge);
  if (surface === SURFACE_SIDEBAR) return renderSidebarSection(ctx, bridge);
  if (surface === SURFACE_DIALOG) return renderFlushDialog(ctx);
  throw new Error(formatMessage(getStrings(ctx.locale).err_unknown_surface, { surface }));
}
