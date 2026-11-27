import { HostRPCError, callHost, notifyHost, serve } from '/runtime/block-sdk.js';
import {
  EXTENSION_MAP,
  PLUGIN_ID,
  PLUGIN_VERSION,
  SURFACE_DIALOG,
  SURFACE_SETTINGS,
} from './constants.js';
import { formatMessage, getStrings, isEn, localizeError } from './i18n.js';
import {
  buildDropBlock,
  countMarkers,
  isEditorWrapSafe,
  splitMdLines,
  stripMarkers,
} from './markdown.js';
import {
  activeCountsSummary,
  appendLog,
  basename,
  bestEffortCall,
  createPluginContext,
  isActiveNotebookAllowed,
  joinPath,
  loadPersisted,
  normPath,
  noteCounts,
  nowHHMM,
  pageValuesFor,
  randomHex,
  safeCall,
  saveConfig,
  saveState,
  setNoteCounts,
} from './state.js';
import {
  mergeFormValues,
  refreshOtherSurfaces,
  renderFlushDialog,
  renderSurface,
  reportProgress,
  showToast,
  syncHostUI,
} from './ui.js';

const bridge = {
  callHost,
  notifyHost,
  HostRPCError,
};

const ctx = createPluginContext();

function scanNotebookMarkers() {
  let res;
  try {
    res = callHost('host.notes.list', {});
  } catch (err) {
    if (err && typeof err.code === 'number') {
      return [noteCounts(ctx), new Set(), false];
    }
    throw err;
  }
  if (!res || typeof res !== 'object' || !Array.isArray(res.notes)) {
    return [noteCounts(ctx), new Set(), false];
  }
  const prevCounts = noteCounts(ctx);
  const counts = {};
  const failedPaths = new Set();
  for (const item of res.notes) {
    const rel = item && item.path;
    if (typeof rel !== 'string' || !rel) continue;
    try {
      const note = callHost('host.notes.read', { path: rel });
      const n = countMarkers((note && note.content) || '');
      if (n > 0) {
        counts[rel] = n;
      }
    } catch (_err) {
      failedPaths.add(rel);
      if (Object.prototype.hasOwnProperty.call(prevCounts, rel)) {
        counts[rel] = prevCounts[rel];
      }
    }
  }
  setNoteCounts(ctx, counts);
  return [counts, failedPaths, true];
}

function resolveActiveNote() {
  const res = safeCall(bridge, 'host.notes.active', {});
  if (res && typeof res === 'object' && typeof res.path === 'string' && res.path !== '') {
    return res.path;
  }
  return '';
}

function resolveTargetNote(explicitNote = '', strict = false, activeOnly = false) {
  if (typeof explicitNote === 'string' && explicitNote !== '') {
    return explicitNote;
  }
  if (strict) return '';
  const active = resolveActiveNote();
  if (active) return active;
  if (activeOnly) return '';
  const listed = safeCall(bridge, 'host.notes.list', {});
  if (listed && typeof listed === 'object' && Array.isArray(listed.notes) && listed.notes.length > 0) {
    return String((listed.notes[0] && listed.notes[0].path) || '');
  }
  return '';
}

function dropIntoNoteFile(noteRel, wrappedText = '') {
  const t = getStrings(ctx.locale);
  if (!noteRel) {
    return [false, 'warning', t.toast_no_note];
  }
  let readRes;
  try {
    readRes = callHost('host.notes.read', { path: noteRel });
  } catch (err) {
    return [false, 'error', localizeError(err && err.message, ctx.locale)];
  }
  const content = String((readRes && readRes.content) || '');
  const rev = readRes ? readRes.revision : undefined;
  const origLines = splitMdLines(content);

  let sep;
  let eol;
  let firstMeta;
  if (origLines.length === 0) {
    sep = '';
    eol = '\n';
    firstMeta = 'keepblank';
  } else {
    const lastLine = origLines[origLines.length - 1];
    if (lastLine === '\r\n' || lastLine === '\n' || lastLine === '\r') {
      sep = '';
      eol = lastLine;
      firstMeta = 'keepblank';
    } else if (lastLine.endsWith('\r\n')) {
      sep = '\r\n';
      eol = '\r\n';
      firstMeta = 'sep1';
    } else if (lastLine.endsWith('\n')) {
      sep = '\n';
      eol = '\n';
      firstMeta = 'sep1';
    } else if (lastLine.endsWith('\r')) {
      sep = '\r';
      eol = '\r';
      firstMeta = 'sep1';
    } else {
      sep = '\n\n';
      eol = '\n';
      firstMeta = 'noeol';
    }
  }

  const block = buildDropBlock({
    caption: ctx.config.caption,
    style: ctx.config.style,
    shape: ctx.config.shape,
    locale: ctx.locale,
    wrappedText,
    firstMeta: wrappedText ? '' : firstMeta,
  });

  if (wrappedText) {
    const rt = stripMarkers(block);
    if (rt.removed !== 2 || rt.content !== wrappedText) {
      return [false, 'warning', t.toast_unsafe_wrap];
    }
  }

  const nextContent = content + sep + block + eol;
  const prevCnt = countMarkers(content);
  const expectedAdded = countMarkers(block);
  const newCnt = countMarkers(nextContent);
  if (expectedAdded <= 0 || newCnt !== prevCnt + expectedAdded) {
    return [false, 'warning', t.toast_unsafe_container];
  }
  if (!wrappedText) {
    const baseClean = stripMarkers(content).content;
    const nextClean = stripMarkers(nextContent);
    if (nextClean.removed !== prevCnt + expectedAdded || nextClean.content !== baseClean) {
      return [false, 'warning', t.toast_unsafe_container];
    }
  }

  const writeParams = { path: noteRel, content: nextContent };
  if (typeof rev === 'string') {
    writeParams.expected_revision = rev;
  }
  try {
    callHost('host.notes.write', writeParams);
  } catch (err) {
    if (err && err.code === -32006) {
      return [false, 'warning', formatMessage(t.toast_conflict, { note: noteRel })];
    }
    return [false, 'error', localizeError(err && err.message, ctx.locale)];
  }

  noteCounts(ctx)[noteRel] = newCnt;
  ctx.state.total_dropped += expectedAdded;
  ctx.state.last_drop_at = nowHHMM();
  appendLog(ctx, { event: 'drop', note: noteRel, count: expectedAdded, tone: 'success' });
  saveState(ctx, bridge);
  syncHostUI(ctx, bridge);

  if (newCnt >= 5) {
    return [true, 'warning', formatMessage(t.toast_heavy_warn, { note: noteRel, n: newCnt })];
  }
  return [true, 'success', formatMessage(t.toast_dropped_note, { note: noteRel, n: expectedAdded })];
}

function dropAtEditorOrNote({ noteRel = '', selection = '', wrapSelection = false, source = '' } = {}) {
  const t = getStrings(ctx.locale);
  let target = resolveTargetNote(noteRel);
  if (!isActiveNotebookAllowed(ctx)) {
    appendLog(ctx, { event: 'blocked', note: target || 'notebook', tone: 'danger' });
    saveState(ctx, bridge);
    return [false, 'error', t.toast_blocked_nb];
  }
  if (source === 'sidebar_menu') {
    ctx.state.sidebar_hits += 1;
    return dropIntoNoteFile(target);
  }

  let selText = selection;
  if (wrapSelection && !selText) {
    const selRes = safeCall(bridge, 'host.editor.selection', {});
    if (selRes && typeof selRes === 'object') {
      selText = String(selRes.text || '');
      if (!target && selRes.note) {
        target = String(selRes.note);
      }
    }
  }

  const isWrapping = Boolean(wrapSelection && selText);
  const block = buildDropBlock({
    caption: ctx.config.caption,
    style: ctx.config.style,
    shape: ctx.config.shape,
    locale: ctx.locale,
    wrappedText: isWrapping ? selText : '',
  });

  if (isWrapping) {
    if (!isEditorWrapSafe(selText)) {
      return [false, 'warning', t.toast_unsafe_wrap];
    }
    const rt = stripMarkers(block);
    if (rt.removed !== 2 || rt.content !== selText) {
      return [false, 'warning', t.toast_unsafe_wrap];
    }
  }

  let inserted = null;
  if (isWrapping) {
    const insertParams = { text: block, mode: 'replace' };
    if (target) insertParams.note = target;
    try {
      inserted = safeCall(bridge, 'host.editor.insert', insertParams);
    } catch (err) {
      if (err && err.code === -32006) {
        return [false, 'warning', formatMessage(t.toast_conflict, { note: target || 'note' })];
      }
      return [false, 'warning', t.toast_unsafe_wrap];
    }
    if (!(inserted && typeof inserted === 'object' && inserted.ok)) {
      return [false, 'warning', t.toast_unsafe_wrap];
    }
  } else if (ctx.capabilities.has('editor_insert_mode')) {
    const insertParams = { text: `\n${block}\n`, mode: 'insert' };
    if (target) insertParams.note = target;
    try {
      inserted = safeCall(bridge, 'host.editor.insert', insertParams);
    } catch (err) {
      if (err && err.code === -32006) {
        return [false, 'warning', formatMessage(t.toast_conflict, { note: target || 'note' })];
      }
      inserted = null;
    }
  }

  if (inserted && typeof inserted === 'object' && inserted.ok) {
    const added = countMarkers(block);
    if (target) {
      const counts = noteCounts(ctx);
      counts[target] = (counts[target] || 0) + added;
    }
    ctx.state.total_dropped += added;
    ctx.state.last_drop_at = nowHHMM();
    let msg;
    if (isWrapping) {
      appendLog(ctx, { event: 'wrap', note: target || 'note', count: added, tone: 'success' });
      msg = t.toast_wrapped_sel;
    } else {
      appendLog(ctx, { event: 'drop', note: target || 'note', count: added, tone: 'success' });
      msg = wrapSelection ? t.toast_no_selection : formatMessage(t.toast_dropped_editor, { n: added });
    }
    saveState(ctx, bridge);
    syncHostUI(ctx, bridge);
    return [true, 'success', msg];
  }

  return dropIntoNoteFile(target);
}

function flushSingleNote(noteRel, strict = false) {
  const t = getStrings(ctx.locale);
  const target = resolveTargetNote(noteRel, strict, true);
  if (!target) {
    return [false, 'warning', t.toast_no_note];
  }
  let readRes;
  try {
    readRes = callHost('host.notes.read', { path: target });
  } catch (err) {
    return [false, 'error', localizeError(err && err.message, ctx.locale)];
  }
  const content = String((readRes && readRes.content) || '');
  const rev = readRes ? readRes.revision : undefined;
  const { content: cleaned, removed } = stripMarkers(content);
  if (removed === 0) {
    delete noteCounts(ctx)[target];
    saveState(ctx, bridge);
    syncHostUI(ctx, bridge);
    return [true, 'info', formatMessage(t.toast_note_clean, { note: target })];
  }

  const writeParams = { path: target, content: cleaned };
  if (typeof rev === 'string') {
    writeParams.expected_revision = rev;
  }
  try {
    callHost('host.notes.write', writeParams);
  } catch (err) {
    if (err && err.code === -32006) {
      return [false, 'warning', formatMessage(t.toast_conflict, { note: target })];
    }
    return [false, 'error', localizeError(err && err.message, ctx.locale)];
  }

  delete noteCounts(ctx)[target];
  ctx.state.total_flushed += removed;
  appendLog(ctx, { event: 'flush_note', note: target, count: removed, tone: 'info' });
  saveState(ctx, bridge);
  syncHostUI(ctx, bridge);
  return [true, 'success', formatMessage(t.toast_flushed_note, { note: target, n: removed })];
}

function flushAllNotes() {
  const t = getStrings(ctx.locale);
  const [, scanFailedPaths, listOk] = scanNotebookMarkers();
  if (!listOk) {
    return [false, 'error', t.toast_list_failed];
  }
  const counts = noteCounts(ctx);
  const targets = Object.keys(counts).sort();
  let totalRemoved = 0;
  let touchedNotes = 0;
  const conflictPaths = new Set();
  const failedPaths = new Set(scanFailedPaths);
  const totalSteps = Math.max(targets.length, 1);

  for (let i = 0; i < targets.length; i += 1) {
    const rel = targets[i];
    reportProgress(ctx, bridge, i, totalSteps, t.progress_flush);
    let readRes;
    try {
      readRes = callHost('host.notes.read', { path: rel });
    } catch (_err) {
      failedPaths.add(rel);
      continue;
    }
    const { content: cleaned, removed } = stripMarkers(String((readRes && readRes.content) || ''));
    if (removed <= 0) {
      delete counts[rel];
      failedPaths.delete(rel);
      continue;
    }
    const writeParams = { path: rel, content: cleaned };
    if (readRes && typeof readRes.revision === 'string') {
      writeParams.expected_revision = readRes.revision;
    }
    try {
      callHost('host.notes.write', writeParams);
      delete counts[rel];
      failedPaths.delete(rel);
      totalRemoved += removed;
      touchedNotes += 1;
    } catch (err) {
      if (err && err.code === -32006) {
        conflictPaths.add(rel);
        failedPaths.delete(rel);
      } else {
        failedPaths.add(rel);
      }
    }
    reportProgress(ctx, bridge, i + 1, totalSteps, t.progress_flush);
  }

  const conflicts = Array.from(conflictPaths).sort();
  const failedCount = failedPaths.size;
  const incomplete = conflicts.length > 0 || failedCount > 0;
  if (totalRemoved > 0) {
    ctx.state.total_flushed += totalRemoved;
    appendLog(ctx, { event: 'flush_all', count: totalRemoved, tone: incomplete ? 'warning' : 'info' });
  }
  saveState(ctx, bridge);
  syncHostUI(ctx, bridge);

  if (incomplete) {
    if (conflicts.length === 1 && failedCount === 0 && totalRemoved === 0) {
      return [false, 'warning', formatMessage(t.toast_conflict, { note: conflicts[0] })];
    }
    return [
      false,
      'warning',
      formatMessage(t.toast_flush_partial, {
        n: totalRemoved,
        conflicts: conflicts.length,
        failed: failedCount,
      }),
    ];
  }
  if (totalRemoved > 0) {
    return [true, 'success', formatMessage(t.toast_flushed_all, { n: totalRemoved, notes: touchedNotes })];
  }
  return [true, 'info', t.toast_nothing_flush];
}

function exportDeveloperGuide() {
  const archiveDir = ctx.config.archive_dir || '';
  let outDir;
  let destLabel;
  if (archiveDir) {
    let st;
    try {
      st = callHost('host.fs.stat', { path: archiveDir });
    } catch (_err) {
      return { outPath: '', destLabel: '', errKind: 'invalid' };
    }
    const exists = st && typeof st === 'object' && (st.exists === undefined ? true : Boolean(st.exists));
    const isDir = st && typeof st === 'object' && (
      Boolean(st.is_dir) || Boolean(st.isDir) || st.type === 'dir' || st.kind === 'dir'
    );
    if (!exists || !isDir) {
      return { outPath: '', destLabel: '', errKind: 'invalid' };
    }
    outDir = archiveDir;
    destLabel = basename(archiveDir) || archiveDir;
  } else {
    outDir = ctx.downloadsDir || ctx.dataDir || '.';
    destLabel = isEn(ctx.locale) ? 'Downloads' : '下载目录';
    try {
      callHost('host.fs.mkdir', { path: outDir });
    } catch (_err) {
      return { outPath: '', destLabel: '', errKind: 'write_failed' };
    }
  }

  const filename = isEn(ctx.locale)
    ? 'block-poop-everywhere-guide-en.md'
    : 'block-poop-everywhere-guide.md';
  const outPath = joinPath(outDir, filename);
  const [total, notes] = activeCountsSummary(ctx);
  const lines = isEn(ctx.locale)
    ? [
        '# Block Plugin Extension Points Reference (Poop Everywhere)',
        '',
        `- Plugin ID: \`${PLUGIN_ID}\` v${PLUGIN_VERSION}`,
        `- Host Version: \`${ctx.hostVersion || 'unknown'}\``,
        `- Active Drops: ${total} across ${notes} note(s)`,
        '',
        '## All 16 Connected Extension Surfaces',
        '',
        '| Extension Key | Required Permission |',
        '| --- | --- |',
      ]
    : [
        '# Block 插件全扩展点参考手册（到处拉屎）',
        '',
        `- 插件 ID：\`${PLUGIN_ID}\` v${PLUGIN_VERSION}`,
        `- 宿主版本：\`${ctx.hostVersion || 'unknown'}\``,
        `- 当前统计：共 ${total} 坨，波及 ${notes} 篇笔记`,
        '',
        '## 已接入的 16 项扩展点',
        '',
        '| 扩展点键名 | 所需权限 |',
        '| --- | --- |',
      ];
  for (const [key, perm] of EXTENSION_MAP) {
    lines.push(`| \`${key}\` | \`${perm}\` |`);
  }
  const content = `${lines.join('\n')}\n`;

  try {
    callHost('host.fs.write', {
      path: outPath,
      content,
      atomic: true,
      mkdir_parents: true,
    });
  } catch (_err) {
    return { outPath: '', destLabel: '', errKind: 'write_failed' };
  }
  return { outPath, destLabel, errKind: '' };
}

function openFlushConfirmation() {
  const t = getStrings(ctx.locale);
  ctx.pendingFlushToken = '';
  ctx.pendingFlushNb = '';
  let opened;
  try {
    opened = callHost('host.ui.open_dialog', { id: 'flush-confirm' });
  } catch (_err) {
    return [false, t.toast_dialog_unavailable];
  }
  if (!opened || typeof opened !== 'object' || opened.ok !== true) {
    return [false, t.toast_dialog_unavailable];
  }
  const hostToken = opened.dialog_token;
  if (ctx.capabilities.has('dialog_token')) {
    if (typeof hostToken !== 'string' || !hostToken.trim()) {
      return [false, t.toast_dialog_unavailable];
    }
    ctx.pendingFlushToken = hostToken.trim();
  } else {
    ctx.pendingFlushToken = (typeof hostToken === 'string' && hostToken.trim())
      ? hostToken.trim()
      : randomHex(8);
  }
  ctx.pendingFlushNb = ctx.notebookRoot;
  ctx.state.dialog_opens += 1;
  saveState(ctx, bridge);
  return [true, t.dialog_title];
}

function handleOpenTargetAction(actionId, surface) {
  const t = getStrings(ctx.locale);
  const target = ctx.openTargets.get(actionId);
  if (!target) {
    return { ok: false, tone: 'warning', status: t.toast_open_missing };
  }
  const [nbRoot, relPath] = target;
  ctx.state.sidebar_hits += 1;
  saveState(ctx, bridge);
  try {
    const res = callHost('host.notes.open', { notebook_root: nbRoot, path: relPath });
    if (res && typeof res === 'object' && res.ok) {
      const msg = formatMessage(t.toast_opened_note, { note: relPath });
      return {
        ok: true,
        tone: 'info',
        status: msg,
        page: renderSurface(ctx, bridge, surface),
      };
    }
  } catch (err) {
    if (err && (err.code === -32601 || err.code === -32005)) {
      return { ok: true, tone: 'info', status: t.toast_open_unavailable };
    }
    return { ok: false, tone: 'danger', status: localizeError(err && err.message, ctx.locale) };
  }
  return { ok: true, tone: 'info', status: t.toast_open_unavailable };
}

function handleAction(surface, actionId, values, dialogToken = '') {
  const t = getStrings(ctx.locale);
  if (actionId.startsWith('open_target:')) {
    return handleOpenTargetAction(actionId, surface);
  }

  if (actionId === 'drop_now' || actionId === 'panel_drop' || actionId === 'sidebar_drop') {
    const [ok, tone, msg] = dropAtEditorOrNote({ source: surface });
    refreshOtherSurfaces(bridge, surface);
    return {
      ok,
      tone,
      status: msg,
      page: renderSurface(ctx, bridge, surface),
      values: pageValuesFor(surface, ctx.config),
    };
  }

  if (actionId === 'save_prefs') {
    saveConfig(ctx, bridge);
    appendLog(ctx, { event: 'saved', tone: 'success' });
    saveState(ctx, bridge);
    syncHostUI(ctx, bridge);
    refreshOtherSurfaces(bridge, surface);
    return {
      ok: true,
      tone: 'success',
      status: t.toast_saved,
      page: renderSurface(ctx, bridge, surface),
      values: pageValuesFor(surface, ctx.config),
    };
  }

  if (actionId === 'demo_toasts') {
    showToast(bridge, t.toast_demo_info, 'info');
    showToast(bridge, t.toast_demo_success, 'success');
    showToast(bridge, t.toast_demo_warning, 'warning');
    showToast(bridge, t.toast_demo_error, 'error');
    return {
      ok: true,
      tone: 'info',
      status: t.toast_demo_1,
      page: renderSurface(ctx, bridge, surface),
    };
  }

  if (actionId === 'rescan_notes') {
    const [, failedPaths, listOk] = scanNotebookMarkers();
    if (!listOk) {
      return {
        ok: false,
        tone: 'error',
        status: t.toast_list_failed,
        page: renderSurface(ctx, bridge, surface),
      };
    }
    saveState(ctx, bridge);
    syncHostUI(ctx, bridge);
    refreshOtherSurfaces(bridge, surface);
    const [total, notes] = activeCountsSummary(ctx);
    if (failedPaths.size > 0) {
      return {
        ok: false,
        tone: 'warning',
        status: formatMessage(t.toast_rescan_partial, { n: total, notes, failed: failedPaths.size }),
        page: renderSurface(ctx, bridge, surface),
      };
    }
    return {
      ok: true,
      tone: 'success',
      status: formatMessage(t.toast_rescanned, { n: total, notes }),
      page: renderSurface(ctx, bridge, surface),
    };
  }

  if (actionId === 'export_guide') {
    const { outPath, destLabel, errKind } = exportDeveloperGuide();
    if (!outPath) {
      const msg = errKind === 'invalid' ? t.toast_archive_invalid : t.toast_export_failed;
      return {
        ok: false,
        tone: 'error',
        status: msg,
        page: renderSurface(ctx, bridge, surface),
      };
    }
    return {
      ok: true,
      tone: 'success',
      status: formatMessage(t.toast_exported, { dest: destLabel }),
      reveal_path: outPath,
      page: renderSurface(ctx, bridge, surface),
    };
  }

  if (actionId === 'open_flush' || actionId === 'panel_open_flush') {
    const [ok, msg] = openFlushConfirmation();
    return {
      ok,
      tone: ok ? 'info' : 'warning',
      status: msg,
      page: renderSurface(ctx, bridge, surface),
    };
  }

  if (actionId === 'panel_flush_page') {
    const [ok, tone, msg] = flushSingleNote('');
    refreshOtherSurfaces(bridge, surface);
    return {
      ok,
      tone,
      status: msg,
      page: renderSurface(ctx, bridge, surface),
    };
  }

  if (actionId === 'dialog_keep') {
    if (surface !== SURFACE_DIALOG || !ctx.pendingFlushToken || ctx.pendingFlushNb !== ctx.notebookRoot) {
      return {
        ok: false,
        tone: 'warning',
        status: t.toast_stale_confirm,
        page: renderSurface(ctx, bridge, surface),
      };
    }
    if (ctx.capabilities.has('dialog_token') && dialogToken !== ctx.pendingFlushToken) {
      return {
        ok: false,
        tone: 'warning',
        status: t.toast_stale_confirm,
        page: renderFlushDialog(ctx),
      };
    }
    ctx.pendingFlushToken = '';
    ctx.pendingFlushNb = '';
    bestEffortCall(bridge, 'host.ui.close_dialog', { id: 'flush-confirm' });
    return {
      ok: true,
      tone: 'info',
      status: t.toast_kept,
      page: renderFlushDialog(ctx),
    };
  }

  if (actionId === 'dialog_flush_confirm') {
    if (surface !== SURFACE_DIALOG || !ctx.pendingFlushToken || ctx.pendingFlushNb !== ctx.notebookRoot) {
      return {
        ok: false,
        tone: 'warning',
        status: t.toast_stale_confirm,
        page: renderSurface(ctx, bridge, surface),
      };
    }
    if (ctx.capabilities.has('dialog_token') && dialogToken !== ctx.pendingFlushToken) {
      return {
        ok: false,
        tone: 'warning',
        status: t.toast_stale_confirm,
        page: renderFlushDialog(ctx),
      };
    }
    const secret = ctx.config.flush_secret || '';
    if (secret && String(values.confirm_secret || '') !== secret) {
      return {
        ok: false,
        tone: 'danger',
        status: t.toast_wrong_secret,
        page: renderFlushDialog(ctx),
      };
    }
    ctx.pendingFlushToken = '';
    ctx.pendingFlushNb = '';
    const [ok, tone, msg] = flushAllNotes();
    bestEffortCall(bridge, 'host.ui.close_dialog', { id: 'flush-confirm' });
    const page = renderFlushDialog(ctx);
    showToast(bridge, msg, tone);
    refreshOtherSurfaces(bridge, surface);
    return { ok, tone, status: msg, page };
  }

  throw new Error(formatMessage(t.err_unknown_action, { action: actionId }));
}

function handleCommand(cmdId, cmdCtx) {
  const t = getStrings(ctx.locale);
  const note = typeof cmdCtx.note === 'string' ? cmdCtx.note : '';
  const selection = typeof cmdCtx.selection === 'string' ? cmdCtx.selection : '';
  const source = String(cmdCtx.source || '');

  if (cmdId === 'drop_here') {
    const [ok, tone, msg] = dropAtEditorOrNote({
      noteRel: note,
      selection,
      wrapSelection: false,
      source,
    });
    refreshOtherSurfaces(bridge);
    return { ok, tone, status: msg };
  }

  if (cmdId === 'poopify_selection') {
    const [ok, tone, msg] = dropAtEditorOrNote({
      noteRel: note,
      selection,
      wrapSelection: true,
      source,
    });
    refreshOtherSurfaces(bridge);
    return { ok, tone, status: msg };
  }

  if (cmdId === 'toggle_panel') {
    const methodName = ctx.capabilities.has('panel_toggle')
      ? 'host.ui.toggle_panel'
      : 'host.ui.open_panel';
    let res;
    try {
      res = callHost(methodName, { id: 'poop-board' });
    } catch (_err) {
      return { ok: false, tone: 'warning', status: t.toast_panel_unavailable };
    }
    if (!res || typeof res !== 'object' || res.ok !== true) {
      return { ok: false, tone: 'warning', status: t.toast_panel_unavailable };
    }
    syncHostUI(ctx, bridge);
    return { ok: true };
  }

  if (cmdId === 'drop_in_note') {
    const strict = source === 'sidebar_menu';
    const target = resolveTargetNote(note, strict);
    if (!target) {
      return { ok: false, tone: 'warning', status: t.toast_no_note };
    }
    if (!isActiveNotebookAllowed(ctx)) {
      appendLog(ctx, { event: 'blocked', note: target, tone: 'danger' });
      saveState(ctx, bridge);
      return { ok: false, tone: 'error', status: t.toast_blocked_nb };
    }
    if (strict) {
      ctx.state.sidebar_hits += 1;
    }
    const [ok, tone, msg] = dropIntoNoteFile(target);
    refreshOtherSurfaces(bridge);
    return { ok, tone, status: msg };
  }

  if (cmdId === 'flush_note') {
    const strict = source === 'sidebar_menu';
    const [ok, tone, msg] = flushSingleNote(note, strict);
    refreshOtherSurfaces(bridge);
    return { ok, tone, status: msg };
  }

  if (cmdId === 'open_flush_dialog') {
    const [ok, msg] = openFlushConfirmation();
    if (!ok) {
      return { ok: false, tone: 'warning', status: msg };
    }
    return { ok: true };
  }

  throw new Error(formatMessage(t.err_unknown_command, { cmd: cmdId }));
}

function handleEvent(params) {
  const ev = String(params.event || '');
  if (ev === 'note.saved') {
    const rel = typeof params.path === 'string' ? params.path : '';
    const nbRoot = String(params.notebook_root || '');
    if (rel && (!nbRoot || !ctx.notebookRoot || normPath(nbRoot) === normPath(ctx.notebookRoot))) {
      try {
        const note = callHost('host.notes.read', { path: rel });
        const cnt = countMarkers((note && note.content) || '');
        const counts = noteCounts(ctx);
        if (cnt > 0) {
          counts[rel] = cnt;
        } else {
          delete counts[rel];
        }
        appendLog(ctx, { event: 'note_saved', note: rel, count: cnt, tone: 'info' });
        saveState(ctx, bridge);
        syncHostUI(ctx, bridge);
        refreshOtherSurfaces(bridge);
      } catch (_err) {
        // Ignore transient read errors during save hooks.
      }
    }
    return { handled: true };
  }

  if (ev === 'theme.changed') {
    let themeChanged = false;
    if (typeof params.theme === 'string' && params.theme.trim()) {
      const nextTheme = params.theme.trim();
      themeChanged = nextTheme !== ctx.hostTheme;
      ctx.hostTheme = nextTheme;
    }
    if (Object.prototype.hasOwnProperty.call(params, 'tarot')) {
      const nextTarot = Boolean(params.tarot);
      themeChanged = themeChanged || nextTarot !== ctx.tarotActive;
      ctx.tarotActive = nextTarot;
    }
    if (themeChanged) {
      syncHostUI(ctx, bridge);
      refreshOtherSurfaces(bridge);
    }
    return { handled: true };
  }

  if (ev === 'locale.changed') {
    const newLoc = String(params.locale || '');
    if (newLoc) {
      ctx.locale = newLoc;
      syncHostUI(ctx, bridge);
      refreshOtherSurfaces(bridge);
    }
    return { handled: true };
  }

  if (ev === 'note.opened') {
    syncHostUI(ctx, bridge);
    return { handled: true };
  }

  return { handled: false };
}

function dispatch(method, params) {
  if (method === 'plugin.initialize') {
    ctx.locale = String(params.locale || 'zh');
    ctx.notebookRoot = String(params.notebook_root || '');
    ctx.downloadsDir = String(params.downloads_dir || '');
    ctx.dataDir = String(params.data_dir || '');
    ctx.hostVersion = String(params.host_version || '');
    if (typeof params.theme === 'string' && params.theme.trim()) {
      ctx.hostTheme = params.theme.trim();
    }
    if (Object.prototype.hasOwnProperty.call(params, 'tarot')) {
      ctx.tarotActive = Boolean(params.tarot);
    }
    ctx.capabilities = new Set(Array.isArray(params.ui_capabilities) ? params.ui_capabilities : []);
    loadPersisted(ctx, bridge);
    scanNotebookMarkers();
    syncHostUI(ctx, bridge);
    return { ready: true };
  }

  if (method === 'plugin.render') {
    const surface = String(params.surface || SURFACE_SETTINGS);
    if (params.values && typeof params.values === 'object' && !Array.isArray(params.values)) {
      mergeFormValues(ctx, bridge, params.values, surface);
    }
    const page = renderSurface(ctx, bridge, surface);
    return { page, values: pageValuesFor(surface, ctx.config) };
  }

  if (method === 'plugin.action') {
    const surface = String(params.surface || SURFACE_SETTINGS);
    const actionId = String(params.action_id || '');
    const values = (params.values && typeof params.values === 'object' && !Array.isArray(params.values))
      ? params.values
      : {};
    const dialogToken = typeof params.dialog_token === 'string' ? params.dialog_token : '';
    if (surface !== SURFACE_DIALOG) {
      mergeFormValues(ctx, bridge, values, surface);
    }
    return handleAction(surface, actionId, values, dialogToken);
  }

  if (method === 'plugin.command') {
    const cmdId = String(params.command_id || '');
    const cmdCtx = (params.context && typeof params.context === 'object' && !Array.isArray(params.context))
      ? params.context
      : {};
    return handleCommand(cmdId, cmdCtx);
  }

  if (method === 'plugin.event') {
    return handleEvent(params);
  }

  if (method === 'plugin.shutdown') {
    return { ok: true };
  }

  throw new Error(formatMessage(getStrings(ctx.locale).err_unknown_method, { method }));
}

function handle(method, params) {
  try {
    return dispatch(method, params);
  } catch (err) {
    const code = err && typeof err.code === 'number' ? err.code : -32000;
    const msg = localizeError(err && err.message ? err.message : String(err), ctx.locale);
    throw new HostRPCError(code, msg);
  }
}

serve(handle);
