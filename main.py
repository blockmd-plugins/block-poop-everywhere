#!/usr/bin/env python3
"""Official block-poop-everywhere reference plugin for Block (blockmd).

Demonstrates every Block plugin extension point and declarative UI control:
- Titlebar buttons + dynamic badges + active state
- Command palette + shortcuts + page/editor/sidebar context menus
- Left sidebar collapsible section + file-tree row badges
- Custom vector editor backdrops (scatter / grid / watermark / corners + dark glow)
- Right side panel + bottom status bar with icon + modal dialog + icon toasts
- Built-in Appearance settings section + full 14-control plugin settings page
- Optimistic note read/write, note opening, live progress, save & workspace hooks
"""

import collections
import datetime
import hashlib
import json
import os
import re
import secrets
import sys

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PLUGIN_ID = "block-poop-everywhere"
PLUGIN_VERSION = "1.0.8"

SURFACE_SETTINGS = "settings_page"
SURFACE_APPEARANCE = "settings_section:poop-appearance"
SURFACE_PANEL = "panel:poop-board"
SURFACE_SIDEBAR = "sidebar_section:today-drops"
SURFACE_DIALOG = "dialog:flush-confirm"

ALL_SURFACES = (
    SURFACE_SETTINGS,
    SURFACE_APPEARANCE,
    SURFACE_PANEL,
    SURFACE_SIDEBAR,
    SURFACE_DIALOG,
)

STORAGE_CONFIG = "config"
STORAGE_STATE = "runtime_state"

DROP_SIGNATURE = "<!-- block-poop-everywhere:drop -->"
MARKER_LINE_RE = re.compile(
    r"^[ ]{0,3}>[ ]?(?:\[poop:(?P<legacy>[a-z0-9_-]+)\])?(?:[^\r\n\u2028\u2029]*?)"
    r"(?P<sig><!--\s*block-poop-everywhere:drop(?::(?P<kind>[a-z0-9_-]+))?(?::(?P<meta>[a-z0-9_=,-]+))?\s*-->)[ \t]*(?:\r\n|\r|\n)?$"
)


def match_marker_line(line):
    """Match a plugin drop line, rejecting backslash-escaped HTML comments (CommonMark §2.4)."""
    m = MARKER_LINE_RE.match(line)
    if not m:
        return None
    sig_pos = m.start("sig")
    bs = 0
    j = sig_pos - 1
    while j >= 0 and line[j] == "\\":
        bs += 1
        j -= 1
    if bs % 2 == 1:
        return None
    return m


def drop_sig(kind, meta=""):
    if meta:
        return f"<!-- block-poop-everywhere:drop:{kind}:{meta} -->"
    return f"<!-- block-poop-everywhere:drop:{kind} -->"


FENCE_OPEN_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
HTML_TYPE1_OPEN_RE = re.compile(r"^[ ]{0,3}<(pre|script|style|textarea)(?:[ \t>]|$)", re.I)
HTML_TYPE1_CLOSE_RE = re.compile(r"</(?:pre|script|style|textarea)>", re.I)
HTML_TYPE6_OPEN_RE = re.compile(
    r"^[ ]{0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|"
    r"dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|"
    r"h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|"
    r"optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)"
    r"(?:[ \t/>]|$)",
    re.I,
)
HTML_TYPE7_OPEN_RE = re.compile(
    r"^[ ]{0,3}(?:<[A-Za-z][A-Za-z0-9-]*"
    r"(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*(?:[ \t]*=[ \t]*(?:[^ \t\r\n\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*"
    r"[ \t]*/?>|</[A-Za-z][A-Za-z0-9-]*[ \t]*>)[ \t]*$"
)
LIST_ITEM_RE = re.compile(r"^([ ]{0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)")
ATX_HEADING_RE = re.compile(r"^[ ]{0,3}#{1,6}(?:[ \t]|$)")
THEMATIC_BREAK_RE = re.compile(r"^[ ]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
SETEXT_UNDERLINE_RE = re.compile(r"^[ ]{0,3}(?:=+|-+)[ \t]*$")
EMOJI_RE = re.compile(
    r"[\u200d\u20e3\ufe00-\ufe0f\u2600-\u27bf\U0001f000-\U0001faff]"
)
MARKDOWN_EXTENSIONS = {
    ".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn", ".mdtxt", ".mdtext", ".mdx",
}
MAX_SIDEBAR_BADGES = 512
CHINESE_RE = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe10-\ufe1f\ufe30-\ufe4f\uff00-\uffef]"
)

STYLES = ("shy", "normal", "wild")
SHAPES = ("classic", "ribbon", "pellet")
PATTERNS = ("scatter", "grid", "watermark", "corners")
DENSITIES = ("sparse", "medium", "dense")
TINTS = ("accent", "warm", "muted", "glow")
PREVIEW_MODES = ("article", "diff", "cards", "plan")

DENSITY_OPACITY = {
    "sparse": 0.06,
    "medium": 0.10,
    "dense": 0.18,
}

DEFAULT_CONFIG = {
    "style": "normal",
    "shape": "classic",
    "bg_enabled": True,
    "bg_backdrop": "poop-wallpaper",
    "bg_pattern": "scatter",
    "bg_density": "medium",
    "bg_tint": "accent",
    "bg_dark_glow": False,
    "caption": "",
    "flush_secret": "",
    "archive_dir": "",
    "preview_mode": "article",
    "selected_notebooks": [],
    "notebooks_configured": False,
}

DEFAULT_STATE = {
    "total_dropped": 0,
    "total_flushed": 0,
    "bg_toggles": 0,
    "sidebar_hits": 0,
    "dialog_opens": 0,
    "last_drop_at": "",
    "note_counts_by_nb": {},
    "logs": [],
}

EXTENSION_MAP = [
    ("contributes.titlebar_buttons", "ui:titlebar"),
    ("contributes.commands", "ui:commands"),
    ("contributes.page_menu", "ui:commands"),
    ("contributes.editor_menu", "ui:commands"),
    ("contributes.sidebar_menu", "ui:sidebar"),
    ("contributes.sidebar_sections", "ui:sidebar"),
    ("contributes.file_badges", "ui:sidebar"),
    ("contributes.backdrops", "ui:appearance"),
    ("contributes.panels", "ui:panels"),
    ("contributes.status_items", "ui:status"),
    ("contributes.dialogs", "ui:notify"),
    ("host.ui.toast (with icon)", "ui:notify"),
    ("contributes.settings_sections", "ui:settings"),
    ("surfaces: [settings_page]", "built-in"),
    ("host.editor.selection / insert", "editor:read / write"),
    ("host.notes.open / read / write", "notes:read / write"),
    ("plugin.event (note.saved / workspace)", "events:*"),
]

STRINGS = {
    "zh": {
        "title": "到处拉屎",
        "panel_title": "屎量面板",
        "sidebar_title": "今日屎迹",
        "appearance_title": "到处拉屎 · 编辑区背景",
        "dialog_title": "全部冲掉？",
        "default_caption": "到此一拉",
        "act_drop_now": "立即拉一坨",
        "act_drop_cursor": "在光标处拉一坨",
        "act_export": "导出扩展点手册",
        "act_flush_all": "全部冲掉",
        "act_flush_page": "冲掉当前页",
        "act_save": "保存设置",
        "act_demo_toast": "试看四类提示",
        "act_rescan": "重新扫描笔记",
        "act_reset_bg": "恢复默认背景",
        "act_keep": "先留着",
        "act_confirm_flush": "确认冲掉",
        "card_how": "怎么拉",
        "card_how_meta": "全部 14 种控件示范",
        "card_where": "允许拉屎的笔记本",
        "card_stats": "战况与空间分布",
        "card_map": "开发者扩展点速查表",
        "card_map_badge": "17 处全覆盖",
        "card_bg_sec": "编辑区矢量背景",
        "card_panel_stats": "实时战况",
        "card_panel_recent": "最近屎迹",
        "card_panel_ops": "快捷操作",
        "card_sidebar": "今日屎迹",
        "card_dialog": "清理确认",
        "lbl_style": "拉屎风格",
        "lbl_bg_enabled": "把编辑区背景也拉满",
        "lbl_bg_backdrop": "背景图标款型",
        "lbl_bg_pattern": "平铺布局",
        "lbl_bg_density": "背景浓度",
        "lbl_bg_tint": "背景色调",
        "lbl_dark_glow": "深色主题下换成夜光屎",
        "lbl_shape": "屎的形状",
        "lbl_caption": "每坨附言",
        "ph_caption": "留空则使用默认附言",
        "lbl_secret": "冲水口令（可选）",
        "ph_secret": "留空则冲水无需验证",
        "lbl_confirm_secret": "输入冲水口令确认",
        "ph_confirm_secret": "请输入已设置的冲水口令",
        "lbl_archive": "化粪池导出目录（可选）",
        "lbl_preview_mode": "预览样式",
        "lbl_notebooks_empty": "暂无已打开的笔记本",
        "lbl_logs": "最近战报",
        "lbl_logs_empty": "还没有拉过，点击任意入口试试看",
        "lbl_sidebar_empty": "今天还很干净，点下方按钮拉一坨",
        "lbl_map_empty": "暂无扩展点映射",
        "badge_current": "当前",
        "styles": {"shy": "含蓄", "normal": "正常", "wild": "放肆"},
        "shapes": {"classic": "经典三层", "ribbon": "细长条", "pellet": "一小粒"},
        "backdrops": {"poop-wallpaper": "满屏屎印", "poop-watermark": "居中大屎印"},
        "patterns": {"scatter": "错行斜铺", "grid": "规整矩阵", "watermark": "居中水印", "corners": "四角点缀"},
        "densities": {"sparse": "若隐若现", "medium": "看得见", "dense": "糊一脸"},
        "tints": {"accent": "海盐蓝", "warm": "暖纸棕", "muted": "中性灰", "glow": "夜光绿"},
        "preview_modes": {"article": "正文样式", "diff": "冲水对照", "cards": "能力卡片", "plan": "执行计划"},
        "m_active": "当前留存",
        "m_notes": "波及笔记",
        "m_flushed": "累计冲掉",
        "m_rss": "宿主内存",
        "m_unit_drop": "{n} 坨",
        "m_unit_note": "{n} 篇",
        "kv_version": "插件版本",
        "kv_last": "上次拉屎",
        "kv_never": "尚未开张",
        "kv_points": "已接入扩展点",
        "kv_points_val": "17 项全量接入",
        "kv_env": "运行环境",
        "tm_total_label": "全界面互动分布",
        "tm_total_val": "{n} 次互动",
        "tm_sub": "按扩展点类别统计",
        "tm_file_count": "涉及类别",
        "tm_body": "正文标记",
        "tm_body_detail": "光标插入与选区变屎",
        "tm_bg": "编辑区背景",
        "tm_bg_detail": "矢量水印与浓度切换",
        "tm_sidebar": "侧栏与角标",
        "tm_sidebar_detail": "侧栏分区、角标与右键",
        "tm_dialog": "弹窗与面板",
        "tm_dialog_detail": "确认弹窗与状态联动",
        "pv_title": "实时标记预览",
        "pv_diff_title": "冲水清理对照",
        "pv_cards_title": "插件自由度一览",
        "pv_plan_title": "冲水执行计划",
        "pv_badge": "零 Emoji · 安全可逆",
        "status_clean": "很干净",
        "status_count": "已拉 {n} 坨",
        "status_tip_clean": "当前笔记本很干净，点击打开屎量面板",
        "status_tip_count": "当前笔记本共 {n} 坨，分布在 {notes} 篇笔记；点击切换屎量面板",
        "badge_tip_note": "这篇笔记里留了 {n} 坨屎",
        "toast_dropped_editor": "拉好了，已在光标处放下 {n} 坨",
        "toast_dropped_note": "拉好了，已向 {note} 写入 {n} 坨",
        "toast_wrapped_sel": "已把选中的内容变成屎",
        "toast_no_selection": "当前没有选中文字，已改为在光标处拉一坨",
        "toast_bg_reset": "已恢复默认背景配置",
        "toast_heavy_warn": "{note} 已经堆了 {n} 坨，悠着点",
        "toast_blocked_nb": "当前笔记本未在允许列表里，已跳过",
        "toast_no_note": "当前没有可操作的 Markdown 笔记",
        "toast_flushed_note": "已冲掉 {note} 里的 {n} 坨屎",
        "toast_note_clean": "{note} 本来就很干净",
        "toast_flushed_all": "全部冲掉了，共清理 {n} 坨（{notes} 篇笔记）",
        "toast_flush_partial": "部分笔记未冲完：已清 {n} 坨，冲突 {conflicts} 篇，失败 {failed} 篇",
        "toast_list_failed": "无法列出当前笔记本中的笔记，为防漏清已取消冲水",
        "toast_nothing_flush": "已经干干净净，没有可冲掉的屎",
        "toast_dialog_unavailable": "当前宿主不支持确认弹窗，为防误删已取消冲水",
        "toast_panel_unavailable": "当前宿主无法切换侧栏面板",
        "toast_stale_confirm": "确认会话已失效或笔记本已切换，请重新点开确认弹窗",
        "toast_wrong_secret": "冲水口令不对，未能冲水",
        "toast_conflict": "{note} 有未保存编辑，请先保存后再操作",
        "toast_saved": "配置已保存并同步到全界面",
        "toast_exported": "已导出开发者扩展点手册到{dest}",
        "toast_archive_invalid": "归档目录不存在或不是有效文件夹，请重新选择",
        "toast_export_failed": "导出失败：目标目录无写入权限或磁盘不可用",
        "toast_unsafe_container": "目标笔记末尾处于未闭合代码块或 HTML 块中，已跳过以防标记无法清理",
        "toast_unsafe_wrap": "所选内容包含未闭合代码块或 HTML 块，无法保证无损还原，已保留原文",
        "toast_rescanned": "扫描完成：共发现 {n} 坨（{notes} 篇笔记）",
        "toast_rescan_partial": "扫描部分完成：发现 {n} 坨（{notes} 篇），另有 {failed} 篇读取失败",
        "toast_kept": "好，这几坨先留着",
        "toast_opened_note": "已跳转到 {note}",
        "toast_open_unavailable": "当前运行环境不支持直接跳转笔记",
        "toast_open_missing": "这条记录未绑定笔记本，无法跳转",
        "toast_demo_info": "信息提示：左侧展示插件双色图标",
        "toast_demo_success": "成功提示：标记写入与状态同步完成",
        "toast_demo_warning": "警告提示：单篇堆叠过多会触发提醒",
        "toast_demo_error": "错误提示：未授权笔记本将被安全拦截",
        "toast_demo_1": "已依次排队演示四类语气带图标轻提示",
        "log_drop": "在 {note} 拉了 {n} 坨",
        "log_wrap": "把 {note} 的选区变成了屎",
        "log_flush_note": "冲掉了 {note} 的 {n} 坨",
        "log_flush_all": "一键冲掉了 {n} 坨",
        "log_bg_on": "把编辑区背景拉满了",
        "log_bg_off": "收回了编辑区背景",
        "log_blocked": "{note} 所在笔记本不让拉，已跳过",
        "log_saved": "保存了配置与外观偏好",
        "log_theme": "主题已切换，背景已自动适配",
        "log_note_saved": "检测到 {note} 保存，当前共 {n} 坨",
        "log_status_ok": "完成",
        "log_status_warn": "跳过",
        "log_status_clean": "已冲",
        "log_status_info": "联动",
        "click_to_open": "点击打开 {note}",
        "dialog_desc_before": "当前笔记本共 {n} 坨，涉及 {notes} 篇笔记",
        "dialog_desc_after": "正文标记精确清除，其余内容原封不动\n侧栏角标与面板统计归零",
        "progress_flush": "冲水中",
        "err_unknown_action": "未知操作：{action}",
        "err_unknown_command": "未知命令：{cmd}",
        "err_unknown_surface": "不支持的界面：{surface}",
        "err_unknown_method": "不支持的方法：{method}",
        "err_failed": "操作失败",
    },
    "en": {
        "title": "Poop Everywhere",
        "panel_title": "Poop Board",
        "sidebar_title": "Today's Drops",
        "appearance_title": "Poop Everywhere Backdrop",
        "dialog_title": "Flush Everything?",
        "default_caption": "Poop was here",
        "act_drop_now": "Drop One Now",
        "act_drop_cursor": "Drop One at Cursor",
        "act_export": "Export Extension Guide",
        "act_flush_all": "Flush All",
        "act_flush_page": "Flush This Page",
        "act_save": "Save Settings",
        "act_demo_toast": "Preview 4 Toasts",
        "act_rescan": "Rescan Notes",
        "act_reset_bg": "Reset Backdrop",
        "act_keep": "Keep for Now",
        "act_confirm_flush": "Confirm Flush",
        "card_how": "How to Drop",
        "card_how_meta": "All 14 UI Controls Demo",
        "card_where": "Allowed Notebooks",
        "card_stats": "Status & Breakdown",
        "card_map": "Developer Extension Map",
        "card_map_badge": "17 Surfaces Wired",
        "card_bg_sec": "Editor Vector Backdrop",
        "card_panel_stats": "Live Metrics",
        "card_panel_recent": "Recent Drops",
        "card_panel_ops": "Quick Actions",
        "card_sidebar": "Today's Drops",
        "card_dialog": "Flush Confirmation",
        "lbl_style": "Drop Intensity",
        "lbl_bg_enabled": "Fill Editor Background",
        "lbl_bg_backdrop": "Backdrop Motif",
        "lbl_bg_pattern": "Pattern Layout",
        "lbl_bg_density": "Backdrop Density",
        "lbl_bg_tint": "Backdrop Tint",
        "lbl_dark_glow": "Glow in Dark Mode",
        "lbl_shape": "Drop Shape",
        "lbl_caption": "Drop Caption",
        "ph_caption": "Leave blank to use default caption",
        "lbl_secret": "Flush Passcode (Optional)",
        "ph_secret": "Leave blank to flush without passcode",
        "lbl_confirm_secret": "Enter Flush Passcode",
        "ph_confirm_secret": "Enter your configured flush passcode",
        "lbl_archive": "Septic Export Folder (Optional)",
        "lbl_preview_mode": "Preview Variant",
        "lbl_notebooks_empty": "No open notebooks found",
        "lbl_logs": "Activity Log",
        "lbl_logs_empty": "No drops yet. Trigger any surface to test.",
        "lbl_sidebar_empty": "Clean so far. Use buttons below to test.",
        "lbl_map_empty": "No extension entries",
        "badge_current": "Active",
        "styles": {"shy": "Subtle", "normal": "Normal", "wild": "Wild"},
        "shapes": {"classic": "Classic Swirl", "ribbon": "Long Ribbon", "pellet": "Tiny Pellet"},
        "backdrops": {"poop-wallpaper": "Poop Wallpaper", "poop-watermark": "Center Watermark"},
        "patterns": {"scatter": "Scattered", "grid": "Grid", "watermark": "Watermark", "corners": "Corners"},
        "densities": {"sparse": "Subtle", "medium": "Visible", "dense": "Bold"},
        "tints": {"accent": "Ocean Blue", "warm": "Warm Amber", "muted": "Neutral", "glow": "Night Glow"},
        "preview_modes": {"article": "Article", "diff": "Flush Diff", "cards": "Surface Cards", "plan": "Flush Plan"},
        "m_active": "Active Drops",
        "m_notes": "Marked Notes",
        "m_flushed": "Total Flushed",
        "m_rss": "Host Memory",
        "m_unit_drop": "{n}",
        "m_unit_note": "{n}",
        "kv_version": "Plugin Version",
        "kv_last": "Last Drop",
        "kv_never": "Not yet",
        "kv_points": "Extension Points",
        "kv_points_val": "All 17 Connected",
        "kv_env": "Runtime",
        "tm_total_label": "Surface Activity",
        "tm_total_val": "{n} events",
        "tm_sub": "Grouped by extension surface",
        "tm_file_count": "Categories",
        "tm_body": "Note Body",
        "tm_body_detail": "Caret inserts & selection wrap",
        "tm_bg": "Backdrop",
        "tm_bg_detail": "Vector patterns & dark glow",
        "tm_sidebar": "Sidebar & Badges",
        "tm_sidebar_detail": "Sidebar section, badges & menu",
        "tm_dialog": "Dialogs & Panels",
        "tm_dialog_detail": "Confirm modal & side panel",
        "pv_title": "Live Marker Preview",
        "pv_diff_title": "Flush Diff Preview",
        "pv_cards_title": "Extension Highlights",
        "pv_plan_title": "Flush Execution Plan",
        "pv_badge": "No Emoji - Reversible",
        "status_clean": "Clean",
        "status_count": "{n} Drops",
        "status_tip_clean": "Notebook is clean. Click to open Poop Board.",
        "status_tip_count": "{n} drops across {notes} notes. Click to toggle Poop Board.",
        "badge_tip_note": "{n} drop marker(s) in this note",
        "toast_dropped_editor": "Dropped {n} mark(s) at cursor",
        "toast_dropped_note": "Wrote {n} drop mark(s) into {note}",
        "toast_wrapped_sel": "Turned selection into a poop callout",
        "toast_no_selection": "No selection found; dropped one at cursor instead",
        "toast_bg_reset": "Reset backdrop to defaults",
        "toast_heavy_warn": "{note} already has {n} drops. Easy there.",
        "toast_blocked_nb": "Active notebook is not in the allowlist; skipped",
        "toast_no_note": "No active Markdown note to update",
        "toast_flushed_note": "Flushed {n} drop(s) from {note}",
        "toast_note_clean": "{note} is already squeaky clean",
        "toast_flushed_all": "Flushed {n} drop(s) across {notes} note(s)",
        "toast_flush_partial": "Partial flush: cleared {n}, {conflicts} conflict(s), {failed} failed",
        "toast_list_failed": "Failed to list notes in active notebook; flush aborted for safety",
        "toast_nothing_flush": "Everything is already clean",
        "toast_dialog_unavailable": "Confirmation dialog unavailable; flush aborted for safety",
        "toast_panel_unavailable": "Panel toggle unavailable in this host runtime",
        "toast_stale_confirm": "Confirmation expired or notebook changed; reopen the dialog",
        "toast_wrong_secret": "Incorrect flush passcode; flush aborted",
        "toast_conflict": "{note} has unsaved edits. Save first and retry.",
        "toast_saved": "Settings saved and synced across surfaces",
        "toast_exported": "Exported extension guide to {dest}",
        "toast_archive_invalid": "Archive folder does not exist or is not a directory",
        "toast_export_failed": "Export failed: target directory is not writable",
        "toast_unsafe_container": "Skipped drop: note ends inside an unclosed code or HTML block",
        "toast_unsafe_wrap": "Skipped wrap: selection has unclosed code/HTML that cannot round-trip losslessly",
        "toast_rescanned": "Scan finished: {n} drop(s) in {notes} note(s)",
        "toast_rescan_partial": "Partial scan: {n} drop(s) in {notes} note(s), {failed} failed to read",
        "toast_kept": "Kept existing drops for now",
        "toast_opened_note": "Opened {note}",
        "toast_open_unavailable": "Note jump unavailable in this host runtime",
        "toast_open_missing": "This log entry is not bound to a notebook",
        "toast_demo_info": "Info toast: dual-tone plugin icon on the left",
        "toast_demo_success": "Success toast: drop synced across surfaces",
        "toast_demo_warning": "Warning toast: heavy stack alert triggered",
        "toast_demo_error": "Error toast: disallowed notebook safely skipped",
        "toast_demo_1": "Queued all 4 icon-bearing toast tones",
        "log_drop": "Dropped {n} in {note}",
        "log_wrap": "Wrapped selection in {note}",
        "log_flush_note": "Flushed {n} from {note}",
        "log_flush_all": "Flushed {n} drop(s) across notebook",
        "log_bg_on": "Enabled editor vector backdrop",
        "log_bg_off": "Disabled editor vector backdrop",
        "log_blocked": "Skipped disallowed notebook for {note}",
        "log_saved": "Saved settings and backdrop options",
        "log_theme": "Theme changed; backdrop synced",
        "log_note_saved": "Detected save on {note} ({n} drop(s))",
        "log_status_ok": "OK",
        "log_status_warn": "Skip",
        "log_status_clean": "Flush",
        "log_status_info": "Sync",
        "click_to_open": "Click to open {note}",
        "dialog_desc_before": "{n} drop(s) across {notes} note(s)",
        "dialog_desc_after": "Only plugin marker lines removed; user text untouched\nSidebar badges and board counters reset to zero",
        "progress_flush": "Flushing",
        "err_unknown_action": "Unknown action: {action}",
        "err_unknown_command": "Unknown command: {cmd}",
        "err_unknown_surface": "Unsupported surface: {surface}",
        "err_unknown_method": "Unsupported method: {method}",
        "err_failed": "Operation failed",
    },
}


class HostRPCError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class HostBridge:
    def __init__(self):
        self._seq = 1000
        self._deferred = collections.deque()

    def send(self, obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def notify_host(self, method, params=None):
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def call_host(self, method, params=None):
        self._seq += 1
        req_id = f"p-{self._seq}"
        self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        while True:
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError("stdin closed while awaiting host response")
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if "method" in msg:
                self._deferred.append(msg)
                continue
            if str(msg.get("id")) == req_id:
                if msg.get("error"):
                    err = msg["error"]
                    raise HostRPCError(int(err.get("code", -32000)), str(err.get("message", "host error")))
                return msg.get("result", {})

    def _next_request(self):
        if self._deferred:
            return self._deferred.popleft()
        while True:
            line = sys.stdin.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            return json.loads(line)

    def serve(self, handler, localize_error):
        while True:
            req = self._next_request()
            if req is None:
                break
            method = req.get("method")
            if not method:
                continue
            req_id = req.get("id")
            try:
                result = handler(self, method, req.get("params") or {})
                if req_id is not None:
                    self.send({"jsonrpc": "2.0", "id": req_id, "result": result})
                if method == "plugin.shutdown":
                    break
            except Exception as exc:
                if req_id is not None:
                    self.send({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32000, "message": localize_error(str(exc))},
                    })


def now_hhmm():
    return datetime.datetime.now().strftime("%H:%M")


def format_bytes_mb(num_bytes):
    if not num_bytes or num_bytes <= 0:
        return "0 MB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def is_markdown_path(path):
    if not isinstance(path, str) or not path:
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in MARKDOWN_EXTENSIONS


def split_md_lines(content):
    """Split strictly on CommonMark line endings (CRLF, LF, CR), preserving bytes in O(N) time."""
    if not content:
        return []
    lines = []
    pos = 0
    n = len(content)
    nl_r = content.find("\r", 0)
    nl_n = content.find("\n", 0)
    while pos < n:
        if nl_r != -1 and nl_r < pos:
            nl_r = content.find("\r", pos)
        if nl_n != -1 and nl_n < pos:
            nl_n = content.find("\n", pos)
        if nl_r == -1 and nl_n == -1:
            lines.append(content[pos:])
            break
        if nl_r != -1 and (nl_n == -1 or nl_r < nl_n):
            end = nl_r + 2 if (nl_r + 1 < n and content[nl_r + 1] == "\n") else nl_r + 1
        else:
            end = nl_n + 1
        lines.append(content[pos:end])
        pos = end
    return lines


def leading_columns(text, start_col=0):
    """Return (indent_cols, first_non_ws_idx) using CommonMark 4-column tab stops."""
    col = start_col
    idx = 0
    n = len(text)
    while idx < n:
        ch = text[idx]
        if ch == " ":
            col += 1
            idx += 1
        elif ch == "\t":
            col += 4 - (col % 4)
            idx += 1
        else:
            break
    return col - start_col, idx


def strip_single_bq_prefix(text, start_col=0):
    """Strip one blockquote marker (<=3 spaces + '>' + optional space/tab).

    Returns (inner_text, inner_start_col) using exact CommonMark tab-stop columns,
    or (None, start_col) when text does not start with a blockquote marker.
    """
    cols, idx = leading_columns(text, start_col)
    if cols > 3 or idx >= len(text) or text[idx] != ">":
        return None, start_col
    col_after_gt = start_col + cols + 1
    rest = text[idx + 1:]
    if rest.startswith(" "):
        return rest[1:], col_after_gt + 1
    if rest.startswith("\t"):
        # CommonMark §2.2: tab expands to next 4-col tab stop from col_after_gt;
        # the optional single space after '>' consumes 1 col, leaving tab_w - 1 spaces.
        tab_w = 4 - (col_after_gt % 4)
        return (" " * (tab_w - 1)) + rest[1:], col_after_gt + 1
    return rest, col_after_gt


def html_block_end_kind(stripped_nl, allow_type7=False):
    """Detect CommonMark §4.6 HTML block open (types 1-7); return sentinel or None."""
    if HTML_TYPE1_OPEN_RE.match(stripped_nl):
        return "type1"
    s = stripped_nl.lstrip(" ")
    if len(stripped_nl) - len(s) > 3:
        return None
    if s.startswith("<!--"):
        return "comment"
    if s.startswith("<?"):
        return "pi"
    if len(s) >= 3 and s.startswith("<!") and "A" <= s[2].upper() <= "Z":
        return "decl"
    if s.startswith("<![CDATA["):
        return "cdata"
    if HTML_TYPE6_OPEN_RE.match(stripped_nl):
        return "blank"
    if allow_type7 and HTML_TYPE7_OPEN_RE.match(stripped_nl):
        return "blank"
    return None


def html_block_closes(kind, stripped_nl):
    if kind == "type1":
        return bool(HTML_TYPE1_CLOSE_RE.search(stripped_nl))
    if kind == "comment":
        return "-->" in stripped_nl
    if kind == "pi":
        return "?>" in stripped_nl
    if kind == "decl":
        return ">" in stripped_nl
    if kind == "cdata":
        return "]]>" in stripped_nl
    return False


def list_item_content_indent(line, start_col, m_list):
    """Compute CommonMark §5.2 continuation indent (relative to start_col)."""
    lead_cols, _ = leading_columns(m_list.group(1), start_col)
    marker_end_col = start_col + lead_cols + len(m_list.group(2))
    after = line[m_list.end(2):]
    ws_cols, ws_idx = leading_columns(after, marker_end_col)
    rest = after[ws_idx:]
    if rest == "" or ws_cols >= 5:
        return (marker_end_col - start_col) + 1
    return (marker_end_col - start_col) + max(ws_cols, 1)


def _is_bare_bq_sep(raw_line):
    stripped_nl = raw_line.rstrip("\r\n")
    cols, idx = leading_columns(stripped_nl, 0)
    return cols <= 3 and stripped_nl[idx:].rstrip(" \t") == ">"


def _can_list_interrupt_paragraph(m_list, line):
    """CommonMark §5.2: empty list items and ordered lists not starting at 1 cannot interrupt a paragraph."""
    marker = m_list.group(2)
    after = line[m_list.end():]
    if after.strip(" \t") == "":
        return False
    if marker[-1] in (".", ")"):
        return int(marker[:-1]) == 1
    return True


def _line_interrupts_bq_paragraph(stripped_nl, cols):
    """CommonMark §5.1: determine whether a non-'>' line breaks an open blockquote paragraph."""
    if stripped_nl.strip(" \t") == "":
        return True
    if cols <= 3:
        m_open = FENCE_OPEN_RE.match(stripped_nl)
        if m_open and not (m_open.group(1)[0] == "`" and "`" in m_open.group(2)):
            return True
        if html_block_end_kind(stripped_nl, allow_type7=False) is not None:
            return True
        if ATX_HEADING_RE.match(stripped_nl) or THEMATIC_BREAK_RE.match(stripped_nl):
            return True
        m_list = LIST_ITEM_RE.match(stripped_nl)
        if m_list and _can_list_interrupt_paragraph(m_list, stripped_nl):
            return True
    return False


def _line_interrupts_para_text(line):
    """Return True if `line` (without trailing CR/LF) interrupts a paragraph in CommonMark."""
    if line.strip(" \t") == "":
        return True
    if strip_single_bq_prefix(line, 0)[0] is not None:
        return True
    cols, _ = leading_columns(line, 0)
    return _line_interrupts_bq_paragraph(line, cols)


def _parse_link_ref_def(text_lines, start_idx):
    """If text_lines[start_idx:] begins a CommonMark §4.7 link reference definition,
    return the number of lines consumed (>= 1). Otherwise return 0.
    """
    n_lines = len(text_lines)
    if start_idx >= n_lines:
        return 0
    first = text_lines[start_idx]
    cols, idx = leading_columns(first, 0)
    if cols > 3 or idx >= len(first) or first[idx] != "[":
        return 0

    def line_ok(li_idx):
        if li_idx >= n_lines:
            return False
        if li_idx == start_idx:
            return True
        return not _line_interrupts_para_text(text_lines[li_idx])

    # 1. Link label: '[' + 1..999 chars (at least one non-ws), no unescaped '[' or ']'.
    li = start_idx
    ci = idx + 1
    label_len = 0
    has_non_ws = False
    found_close = False
    while line_ok(li):
        ln = text_lines[li]
        ln_len = len(ln)
        while ci < ln_len:
            ch = ln[ci]
            if ch == "\\" and ci + 1 < ln_len:
                label_len += 2
                if label_len > 999:
                    return 0
                has_non_ws = True
                ci += 2
                continue
            if ch == "[":
                return 0
            if ch == "]":
                found_close = True
                ci += 1
                break
            label_len += 1
            if label_len > 999:
                return 0
            if ch not in (" ", "\t"):
                has_non_ws = True
            ci += 1
        if found_close:
            break
        label_len += 1
        if label_len > 999:
            return 0
        li += 1
        ci = 0

    if not found_close or not has_non_ws:
        return 0
    ln = text_lines[li]
    if ci >= len(ln) or ln[ci] != ":":
        return 0
    ci += 1

    # 2. Optional spaces/tabs + at most one line break + optional spaces/tabs before destination.
    while ci < len(ln) and ln[ci] in (" ", "\t"):
        ci += 1
    if ci >= len(ln):
        li += 1
        if not line_ok(li):
            return 0
        ln = text_lines[li]
        ci = 0
        while ci < len(ln) and ln[ci] in (" ", "\t"):
            ci += 1
        if ci >= len(ln):
            return 0

    # 3. Link destination: <...> on one line or non-empty balanced-parens bare destination.
    if ln[ci] == "<":
        ci += 1
        closed_angle = False
        while ci < len(ln):
            ch = ln[ci]
            if ch == "\\" and ci + 1 < len(ln):
                ci += 2
                continue
            if ch == "<":
                return 0
            if ch == ">":
                closed_angle = True
                ci += 1
                break
            ci += 1
        if not closed_angle:
            return 0
    else:
        dest_start = ci
        paren_depth = 0
        while ci < len(ln):
            ch = ln[ci]
            oc = ord(ch)
            if oc <= 0x20 or oc == 0x7F:
                break
            if ch == "\\" and ci + 1 < len(ln):
                ci += 2
                continue
            if ch == "(":
                paren_depth += 1
                if paren_depth > 32:
                    return 0
            elif ch == ")":
                if paren_depth == 0:
                    return 0
                paren_depth -= 1
            ci += 1
        if ci == dest_start or paren_depth != 0:
            return 0

    dest_line_idx = li

    def parse_title(t_li, t_ci):
        t_ln = text_lines[t_li]
        if t_ci >= len(t_ln):
            return 0
        opener = t_ln[t_ci]
        if opener == '"':
            closer = '"'
        elif opener == "'":
            closer = "'"
        elif opener == "(":
            closer = ")"
        else:
            return 0
        t_ci += 1
        cur_li = t_li
        while cur_li < n_lines:
            if cur_li > t_li and not line_ok(cur_li):
                return 0
            cur_ln = text_lines[cur_li]
            cur_len = len(cur_ln)
            while t_ci < cur_len:
                ch = cur_ln[t_ci]
                if ch == "\\" and t_ci + 1 < cur_len:
                    t_ci += 2
                    continue
                if opener == "(" and ch == "(":
                    return 0
                if ch == closer:
                    t_ci += 1
                    if cur_ln[t_ci:].strip(" \t") != "":
                        return 0
                    return cur_li + 1
                t_ci += 1
            cur_li += 1
            t_ci = 0
        return 0

    # 4. Trailing content on destination line, or optional title starting on next line.
    ws_start = ci
    while ci < len(ln) and ln[ci] in (" ", "\t"):
        ci += 1
    if ci < len(ln):
        if ci == ws_start:
            return 0
        title_end = parse_title(li, ci)
        if title_end == 0:
            return 0
        return title_end - start_idx

    base_consumed = (dest_line_idx + 1) - start_idx
    next_li = dest_line_idx + 1
    if line_ok(next_li):
        next_ln = text_lines[next_li]
        nci = 0
        while nci < len(next_ln) and next_ln[nci] in (" ", "\t"):
            nci += 1
        if nci < len(next_ln) and next_ln[nci] in ('"', "'", "("):
            title_end = parse_title(next_li, nci)
            if title_end > 0:
                return title_end - start_idx
    return base_consumed


def _list_item_body(line, start_col, m_list):
    """Return (body_text, body_start_col) for the first line of a list item per CommonMark §5.2."""
    lead_cols, _ = leading_columns(m_list.group(1), start_col)
    marker_end_col = start_col + lead_cols + len(m_list.group(2))
    after = line[m_list.end(2):]
    ws_cols, ws_idx = leading_columns(after, marker_end_col)
    rest = after[ws_idx:]
    if rest == "":
        return "", marker_end_col + 1
    if ws_cols >= 5:
        return (" " * (ws_cols - 1)) + rest, marker_end_col + 1
    return rest, marker_end_col + max(ws_cols, 1)


def _nested_line_opens_or_continues_para(text, start_col, prev_in_para):
    """Return True iff `text` inside a nested container (list item or nested blockquote)
    leaves an open paragraph at the end of this line."""
    if text.strip(" \t") == "":
        return False
    cols, idx = leading_columns(text, start_col)
    if not prev_in_para and cols >= 4:
        return False
    if cols <= 3:
        norm = (" " * cols) + text[idx:]
        m_f = FENCE_OPEN_RE.match(norm)
        if m_f and not (m_f.group(1)[0] == "`" and "`" in m_f.group(2)):
            return False
        if html_block_end_kind(norm, allow_type7=not prev_in_para) is not None:
            return False
        if ATX_HEADING_RE.match(norm) or THEMATIC_BREAK_RE.match(norm):
            return False
        if prev_in_para and SETEXT_UNDERLINE_RE.match(norm):
            return False
        if not prev_in_para and text[idx] == "[" and _parse_link_ref_def([norm], 0) > 0:
            return False
        inner_bq, inner_col = strip_single_bq_prefix(text, start_col)
        if inner_bq is not None:
            return _nested_line_opens_or_continues_para(inner_bq, inner_col, False)
        m_list = LIST_ITEM_RE.match(norm)
        if m_list:
            if (not prev_in_para) or _can_list_interrupt_paragraph(m_list, norm):
                body, body_col = _list_item_body(norm, start_col, m_list)
                return _nested_line_opens_or_continues_para(body, body_col, False)
            return True
    return True


def _strip_exact_bq_layers(text, start_col, depth):
    """Strip exactly `depth` leading '>' layers; return (inner, col) or (None, start_col)."""
    cur, col = text, start_col
    for _ in range(depth):
        nxt, nxt_col = strip_single_bq_prefix(cur, col)
        if nxt is None:
            return None, start_col
        cur, col = nxt, nxt_col
    return cur, col


def _commonmark_code_span_ranges(para_text):
    """Return list of (start, end) character ranges of CommonMark §6.1 inline code spans."""
    ranges = []
    n = len(para_text)
    i = 0
    while i < n:
        ch = para_text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "`":
            ticks = 0
            while i + ticks < n and para_text[i + ticks] == "`":
                ticks += 1
            j = i + ticks
            closed = False
            while j < n:
                if para_text[j] == "`":
                    run = 0
                    while j + run < n and para_text[j + run] == "`":
                        run += 1
                    if run == ticks:
                        ranges.append((i, j + run))
                        i = j + run
                        closed = True
                        break
                    j += run
                    continue
                j += 1
            if not closed:
                i += ticks
            continue
        i += 1
    return ranges


MARKER_COMMENT_RE = re.compile(r"<!--\s*block-poop-everywhere:drop(?::[a-z0-9_-]+)?(?::[a-z0-9_=,-]+)?\s*-->")


def _comment_in_code_span(line_offset, inner_text, span_ranges):
    if not span_ranges:
        return False
    m = None
    for m in MARKER_COMMENT_RE.finditer(inner_text):
        pass
    if m is None:
        return False
    abs_pos = line_offset + m.start()
    for lo, hi in span_ranges:
        if lo <= abs_pos < hi:
            return True
    return False


def iter_markdown_lines(content):
    """Yield (raw_line, eligible_for_top_level_drop) with CommonMark container tracking."""
    raw_lines = split_md_lines(content)
    stripped_lines = []
    for idx_s, rl in enumerate(raw_lines):
        sn = rl.rstrip("\r\n")
        if idx_s == 0 and sn.startswith("\ufeff"):
            sn = sn[1:]
        stripped_lines.append(sn)

    def collect_bq_ref_lines(start_i):
        out = []
        n_all = len(stripped_lines)
        k = start_i
        while k < n_all:
            s = stripped_lines[k]
            inn, _ = strip_single_bq_prefix(s, 0)
            cand = inn if inn is not None else s
            if k > start_i and _line_interrupts_para_text(cand):
                break
            out.append(cand)
            k += 1
        return out

    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_list_indent = None
    in_indented = False
    html_kind = None
    in_paragraph = False
    skip_ref_def_lines = 0
    # List container stack: list of minimum content column offsets
    list_indents = []
    list_in_para = False
    # Blockquote-nested state (tracks fences, HTML blocks, indented code, nested lists, nested quotes)
    bq_fence_char = ""
    bq_fence_len = 0
    bq_fence_list_indent = None
    bq_html_kind = None
    bq_in_paragraph = False
    bq_in_nested_para = False
    bq_in_indented = False
    bq_list_indents = []
    bq_skip_ref_def_lines = 0
    bq_nested_fence_char = ""
    bq_nested_fence_len = 0
    bq_nested_html_kind = None
    bq_nested_depth = 0

    def reset_bq_nested_blocks():
        nonlocal bq_nested_fence_char, bq_nested_fence_len, bq_nested_html_kind, bq_nested_depth
        bq_nested_fence_char = ""
        bq_nested_fence_len = 0
        bq_nested_html_kind = None
        bq_nested_depth = 0

    # Collect (raw_line, eligible, para_chunk_or_None, is_bq_para_line) so a second pass
    # can accurately protect single- and multi-line CommonMark §6.1 inline code spans
    # inside blockquote paragraphs (including lazy continuation closing backticks).
    records = []

    for line_idx, raw_line in enumerate(raw_lines):
        stripped_nl = stripped_lines[line_idx]
        is_blank = stripped_nl.strip(" \t") == ""
        cols, idx = leading_columns(stripped_nl, 0)

        # 0. Multi-line link reference definition continuation lines (CommonMark §4.7)
        if skip_ref_def_lines > 0:
            skip_ref_def_lines -= 1
            in_paragraph = False
            records.append([raw_line, False, None, False])
            continue
        if bq_skip_ref_def_lines > 0:
            bq_skip_ref_def_lines -= 1
            bq_in_paragraph = False
            bq_in_nested_para = False
            in_paragraph = False
            records.append([raw_line, False, None, False])
            continue

        # 1. Active fenced code block (top-level or list-nested)
        if in_fence:
            if fence_list_indent is not None and not is_blank and cols < fence_list_indent:
                in_fence = False
                fence_char = ""
                fence_len = 0
                fence_list_indent = None
            else:
                records.append([raw_line, False, None, False])
                max_close_col = 3 if fence_list_indent is None else fence_list_indent + 3
                if not is_blank and cols <= max_close_col:
                    m_close = re.match(r"^(`{3,}|~{3,})[ \t]*$", stripped_nl[idx:])
                    if m_close and m_close.group(1)[0] == fence_char and len(m_close.group(1)) >= fence_len:
                        in_fence = False
                        fence_char = ""
                        fence_len = 0
                        fence_list_indent = None
                in_paragraph = False
                continue

        # 2. Active top-level HTML block
        if html_kind is not None:
            if html_kind == "blank" and is_blank:
                html_kind = None
                in_paragraph = False
                records.append([raw_line, False, None, False])
                continue
            records.append([raw_line, False, None, False])
            if html_block_closes(html_kind, stripped_nl):
                html_kind = None
            in_paragraph = False
            continue

        # Handle lines without a leading '>' prefix: either lazy continuation of an
        # open blockquote paragraph (CommonMark §5.1) or blockquote termination.
        bq_inner, bq_col = strip_single_bq_prefix(stripped_nl, 0)
        if bq_inner is None:
            if (bq_in_paragraph or bq_in_nested_para) and not _line_interrupts_bq_paragraph(stripped_nl, cols):
                if bq_in_nested_para:
                    records.append([raw_line, False, None, False])
                else:
                    records.append([raw_line, False, stripped_nl, True])
                in_paragraph = False
                continue
            bq_fence_char = ""
            bq_fence_len = 0
            bq_fence_list_indent = None
            bq_html_kind = None
            bq_in_paragraph = False
            bq_in_nested_para = False
            bq_in_indented = False
            bq_list_indents = []
            reset_bq_nested_blocks()

        # 3. Blank line
        if is_blank:
            records.append([raw_line, False, None, False])
            in_paragraph = False
            list_in_para = False
            continue

        # 4. Active list container (popping levels whose indent exceeds current cols,
        # while respecting CommonMark §5.2 lazy paragraph continuation)
        if list_indents:
            if cols < list_indents[-1] and list_in_para and bq_inner is None and not _line_interrupts_bq_paragraph(stripped_nl, cols):
                records.append([raw_line, False, None, False])
                in_paragraph = False
                continue
            while list_indents and cols < list_indents[-1]:
                list_indents.pop()
            if not list_indents:
                list_in_para = False
            else:
                rel_cols = cols - list_indents[-1]
                rel_text = (" " * rel_cols) + stripped_nl[idx:]
                opened_fence = False
                if rel_cols <= 3:
                    m_lf = FENCE_OPEN_RE.match(rel_text)
                    if m_lf and not (m_lf.group(1)[0] == "`" and "`" in m_lf.group(2)):
                        in_fence = True
                        fence_char = m_lf.group(1)[0]
                        fence_len = len(m_lf.group(1))
                        fence_list_indent = list_indents[-1]
                        opened_fence = True
                list_in_para = False if opened_fence else _nested_line_opens_or_continues_para(rel_text, 0, list_in_para)
                records.append([raw_line, False, None, False])
                in_paragraph = False
                continue

        # 5. Active or newly starting top-level indented code block (CommonMark §4.4: cannot interrupt paragraph)
        if in_indented:
            if cols >= 4:
                records.append([raw_line, False, None, False])
                in_paragraph = False
                continue
            in_indented = False

        if (not in_paragraph) and cols >= 4:
            in_indented = True
            in_paragraph = False
            records.append([raw_line, False, None, False])
            continue

        # 6. Top-level fenced code block open
        if cols <= 3:
            m_open = FENCE_OPEN_RE.match(stripped_nl)
            if m_open:
                marker = m_open.group(1)
                info = m_open.group(2)
                if not (marker[0] == "`" and "`" in info):
                    in_fence = True
                    fence_char = marker[0]
                    fence_len = len(marker)
                    fence_list_indent = None
                    in_paragraph = False
                    records.append([raw_line, False, None, False])
                    continue

        # 7. Top-level raw HTML block open (CommonMark §4.6 types 1-7: type 7 cannot interrupt paragraph)
        hk = html_block_end_kind(stripped_nl, allow_type7=not in_paragraph)
        if hk is not None:
            records.append([raw_line, False, None, False])
            if not html_block_closes(hk, stripped_nl):
                html_kind = hk
            in_paragraph = False
            continue

        # 7b. ATX heading, setext heading underline, thematic break, or link reference definition
        if cols <= 3 and (
            ATX_HEADING_RE.match(stripped_nl)
            or (in_paragraph and SETEXT_UNDERLINE_RE.match(stripped_nl))
            or THEMATIC_BREAK_RE.match(stripped_nl)
        ):
            in_paragraph = False
            records.append([raw_line, False, None, False])
            continue

        if (not in_paragraph) and cols <= 3 and idx < len(stripped_nl) and stripped_nl[idx] == "[":
            ref_lines = _parse_link_ref_def(stripped_lines, line_idx)
            if ref_lines > 0:
                skip_ref_def_lines = ref_lines - 1
                in_paragraph = False
                records.append([raw_line, False, None, False])
                continue

        # 8. List item open (bullet or ordered) — respecting CommonMark §5.2 paragraph interruption
        m_list = LIST_ITEM_RE.match(stripped_nl)
        if m_list and ((not in_paragraph) or _can_list_interrupt_paragraph(m_list, stripped_nl)):
            list_indents.append(list_item_content_indent(stripped_nl, 0, m_list))
            body, body_col = _list_item_body(stripped_nl, 0, m_list)
            b_cols_l, _ = leading_columns(body, body_col)
            opened_fence = False
            if b_cols_l <= 3:
                m_lf = FENCE_OPEN_RE.match(body)
                if m_lf and not (m_lf.group(1)[0] == "`" and "`" in m_lf.group(2)):
                    in_fence = True
                    fence_char = m_lf.group(1)[0]
                    fence_len = len(m_lf.group(1))
                    fence_list_indent = list_indents[-1]
                    opened_fence = True
            list_in_para = False if opened_fence else _nested_line_opens_or_continues_para(body, body_col, False)
            records.append([raw_line, False, None, False])
            in_paragraph = False
            continue

        # 9. Top-level blockquote (only place plugin drop lines live)
        if bq_inner is not None:
            in_paragraph = False
            inner_blank = bq_inner.strip(" \t") == ""
            bcols, bidx = leading_columns(bq_inner, bq_col)

            # 9a. Active blockquote-nested fence (direct or inside bq list)
            if bq_fence_char:
                reset_bq_nested_blocks()
                if bq_fence_list_indent is not None and not inner_blank and bcols < bq_fence_list_indent:
                    bq_fence_char = ""
                    bq_fence_len = 0
                    bq_fence_list_indent = None
                else:
                    records.append([raw_line, False, None, False])
                    bmax_close = 3 if bq_fence_list_indent is None else bq_fence_list_indent + 3
                    if not inner_blank and bcols <= bmax_close:
                        m_bc = re.match(r"^(`{3,}|~{3,})[ \t]*$", bq_inner[bidx:])
                        if m_bc and m_bc.group(1)[0] == bq_fence_char and len(m_bc.group(1)) >= bq_fence_len:
                            bq_fence_char = ""
                            bq_fence_len = 0
                            bq_fence_list_indent = None
                    bq_in_paragraph = False
                    bq_in_nested_para = False
                    continue

            # 9b. Active blockquote-nested HTML block
            if bq_html_kind is not None:
                reset_bq_nested_blocks()
                if bq_html_kind == "blank" and inner_blank:
                    bq_html_kind = None
                elif html_block_closes(bq_html_kind, bq_inner):
                    bq_html_kind = None
                records.append([raw_line, False, None, False])
                bq_in_paragraph = False
                bq_in_nested_para = False
                continue

            if inner_blank:
                records.append([raw_line, False, None, False])
                bq_in_paragraph = False
                bq_in_nested_para = False
                reset_bq_nested_blocks()
                continue

            # 9c. Active blockquote-nested list container
            if bq_list_indents:
                while bq_list_indents and bcols < bq_list_indents[-1]:
                    bq_list_indents.pop()
                if bq_list_indents:
                    reset_bq_nested_blocks()
                    rel_bcols = bcols - bq_list_indents[-1]
                    rel_btext = (" " * rel_bcols) + bq_inner[bidx:]
                    opened_bfence = False
                    opened_bhtml = False
                    if rel_bcols <= 3:
                        m_blf = FENCE_OPEN_RE.match(rel_btext)
                        if m_blf and not (m_blf.group(1)[0] == "`" and "`" in m_blf.group(2)):
                            bq_fence_char = m_blf.group(1)[0]
                            bq_fence_len = len(m_blf.group(1))
                            bq_fence_list_indent = bq_list_indents[-1]
                            opened_bfence = True
                        else:
                            bhk_l = html_block_end_kind(rel_btext, allow_type7=not bq_in_nested_para)
                            if bhk_l is not None:
                                if not html_block_closes(bhk_l, rel_btext):
                                    bq_html_kind = bhk_l
                                opened_bhtml = True
                    records.append([raw_line, False, None, False])
                    bq_in_paragraph = False
                    bq_in_nested_para = False if (opened_bfence or opened_bhtml) else _nested_line_opens_or_continues_para(rel_btext, 0, bq_in_nested_para)
                    continue

            # 9d. Blockquote-nested indented code (CommonMark §4.4: cannot interrupt paragraph)
            if bq_in_indented:
                reset_bq_nested_blocks()
                if bcols >= 4:
                    records.append([raw_line, False, None, False])
                    bq_in_paragraph = False
                    bq_in_nested_para = False
                    continue
                bq_in_indented = False
            if (not bq_in_paragraph) and (not bq_in_nested_para) and bcols >= 4:
                reset_bq_nested_blocks()
                bq_in_indented = True
                records.append([raw_line, False, None, False])
                bq_in_paragraph = False
                bq_in_nested_para = False
                continue

            # 9e. Blockquote-nested fence, HTML block, heading/break, link ref def, or list open
            if bcols <= 3:
                m_bo = FENCE_OPEN_RE.match(bq_inner[bidx:])
                if m_bo and not (m_bo.group(1)[0] == "`" and "`" in m_bo.group(2)):
                    reset_bq_nested_blocks()
                    bq_fence_char = m_bo.group(1)[0]
                    bq_fence_len = len(m_bo.group(1))
                    bq_fence_list_indent = None
                    records.append([raw_line, False, None, False])
                    bq_in_paragraph = False
                    bq_in_nested_para = False
                    continue
                bhk = html_block_end_kind(bq_inner, allow_type7=(not bq_in_paragraph and not bq_in_nested_para))
                if bhk is not None:
                    reset_bq_nested_blocks()
                    if not html_block_closes(bhk, bq_inner):
                        bq_html_kind = bhk
                    records.append([raw_line, False, None, False])
                    bq_in_paragraph = False
                    bq_in_nested_para = False
                    continue
                if (
                    ATX_HEADING_RE.match(bq_inner)
                    or (bq_in_paragraph and SETEXT_UNDERLINE_RE.match(bq_inner))
                    or THEMATIC_BREAK_RE.match(bq_inner)
                ):
                    reset_bq_nested_blocks()
                    records.append([raw_line, False, None, False])
                    bq_in_paragraph = False
                    bq_in_nested_para = False
                    continue
                if (not bq_in_paragraph) and (not bq_in_nested_para) and bidx < len(bq_inner) and bq_inner[bidx] == "[":
                    bq_ref_lines = _parse_link_ref_def(collect_bq_ref_lines(line_idx), 0)
                    if bq_ref_lines > 0:
                        reset_bq_nested_blocks()
                        bq_skip_ref_def_lines = bq_ref_lines - 1
                        bq_in_paragraph = False
                        bq_in_nested_para = False
                        records.append([raw_line, False, None, False])
                        continue
                m_blist = LIST_ITEM_RE.match(bq_inner)
                if m_blist and ((not bq_in_paragraph and not bq_in_nested_para) or _can_list_interrupt_paragraph(m_blist, bq_inner)):
                    reset_bq_nested_blocks()
                    bq_list_indents.append(list_item_content_indent(bq_inner, bq_col, m_blist))
                    b_body, b_body_col = _list_item_body(bq_inner, bq_col, m_blist)
                    b_body_cols, _ = leading_columns(b_body, b_body_col)
                    opened_bfence = False
                    opened_bhtml = False
                    if b_body_cols <= 3:
                        m_blf = FENCE_OPEN_RE.match(b_body)
                        if m_blf and not (m_blf.group(1)[0] == "`" and "`" in m_blf.group(2)):
                            bq_fence_char = m_blf.group(1)[0]
                            bq_fence_len = len(m_blf.group(1))
                            bq_fence_list_indent = bq_list_indents[-1]
                            opened_bfence = True
                        else:
                            bhk_l = html_block_end_kind(b_body, allow_type7=True)
                            if bhk_l is not None:
                                if not html_block_closes(bhk_l, b_body):
                                    bq_html_kind = bhk_l
                                opened_bhtml = True
                    records.append([raw_line, False, None, False])
                    bq_in_paragraph = False
                    bq_in_nested_para = False if (opened_bfence or opened_bhtml) else _nested_line_opens_or_continues_para(b_body, b_body_col, False)
                    continue

            # Nested blockquote (`> > ...`) and its lazy continuation lines are never plugin drops.
            nested_inner, nested_col = strip_single_bq_prefix(bq_inner, bq_col)
            if nested_inner is not None:
                # First handle active fence / HTML block at exact bq_nested_depth.
                if bq_nested_fence_char or bq_nested_html_kind is not None:
                    exact_inner, exact_col = _strip_exact_bq_layers(bq_inner, bq_col, bq_nested_depth)
                    if exact_inner is not None:
                        ecols, eidx = leading_columns(exact_inner, exact_col)
                        e_blank = exact_inner.strip(" \t") == ""
                        if bq_nested_fence_char:
                            if not e_blank and ecols <= 3:
                                m_nc = re.match(r"^(`{3,}|~{3,})[ \t]*$", exact_inner[eidx:])
                                if m_nc and m_nc.group(1)[0] == bq_nested_fence_char and len(m_nc.group(1)) >= bq_nested_fence_len:
                                    bq_nested_fence_char = ""
                                    bq_nested_fence_len = 0
                        elif bq_nested_html_kind is not None:
                            if bq_nested_html_kind == "blank" and e_blank:
                                bq_nested_html_kind = None
                            elif html_block_closes(bq_nested_html_kind, exact_inner):
                                bq_nested_html_kind = None
                        bq_in_nested_para = False
                        bq_in_paragraph = False
                        records.append([raw_line, False, None, False])
                        continue
                    reset_bq_nested_blocks()

                deep_inner, deep_col = nested_inner, nested_col
                depth = 1
                while True:
                    nxt, nxt_col = strip_single_bq_prefix(deep_inner, deep_col)
                    if nxt is None:
                        break
                    deep_inner, deep_col = nxt, nxt_col
                    depth += 1

                prev_same_para = bq_in_nested_para and (depth <= bq_nested_depth)
                dcols, didx = leading_columns(deep_inner, deep_col)
                d_blank = deep_inner.strip(" \t") == ""
                if d_blank:
                    bq_in_nested_para = False
                elif dcols <= 3:
                    dnorm = (" " * dcols) + deep_inner[didx:]
                    m_nf = FENCE_OPEN_RE.match(dnorm)
                    if m_nf and not (m_nf.group(1)[0] == "`" and "`" in m_nf.group(2)):
                        bq_nested_fence_char = m_nf.group(1)[0]
                        bq_nested_fence_len = len(m_nf.group(1))
                        bq_in_nested_para = False
                    else:
                        nhk = html_block_end_kind(dnorm, allow_type7=not prev_same_para)
                        if nhk is not None:
                            if not html_block_closes(nhk, dnorm):
                                bq_nested_html_kind = nhk
                            bq_in_nested_para = False
                        else:
                            bq_in_nested_para = _nested_line_opens_or_continues_para(deep_inner, deep_col, prev_same_para)
                else:
                    bq_in_nested_para = _nested_line_opens_or_continues_para(deep_inner, deep_col, prev_same_para)
                bq_nested_depth = depth
                bq_in_paragraph = False
                records.append([raw_line, False, None, False])
                continue

            reset_bq_nested_blocks()
            if bq_in_nested_para:
                # CommonMark §5.1 lazy continuation of nested blockquote or bq-list paragraph.
                records.append([raw_line, False, None, False])
                continue

            bq_in_paragraph = True
            records.append([raw_line, bcols <= 3, bq_inner, True])
            continue

        in_paragraph = True
        records.append([raw_line, False, stripped_nl, False])

    # Pass 2: Protect CommonMark §6.1 inline code spans (single-line and multi-line)
    # within each contiguous blockquote paragraph (including trailing lazy continuation lines).
    n_rec = len(records)
    idx_rec = 0
    while idx_rec < n_rec:
        if not records[idx_rec][3]:
            idx_rec += 1
            continue
        start_rec = idx_rec
        while idx_rec < n_rec and records[idx_rec][3]:
            idx_rec += 1
        end_rec = idx_rec
        # Include immediately following top-level lazy paragraph continuation lines (no '>')
        # so backtick spans closed on a lazy continuation line are recognized.
        while end_rec < n_rec and (not records[end_rec][3]) and records[end_rec][2] is not None:
            end_rec += 1
        chunks = [records[k][2] for k in range(start_rec, end_rec)]
        joined = "\n".join(chunks)
        if "`" in joined:
            span_ranges = _commonmark_code_span_ranges(joined)
            if span_ranges:
                offset = 0
                for k in range(start_rec, end_rec):
                    chunk = records[k][2]
                    if records[k][1] and _comment_in_code_span(offset, chunk, span_ranges):
                        records[k][1] = False
                    offset += len(chunk) + 1
        idx_rec = end_rec

    for rec in records:
        yield rec[0], rec[1]


class PoopEverywherePlugin:
    def __init__(self):
        self.locale = "zh"
        self.notebook_root = ""
        self.downloads_dir = ""
        self.data_dir = ""
        self.host_version = ""
        self.host_theme = "system"
        self.tarot_active = False
        self.capabilities = set()
        self.config = dict(DEFAULT_CONFIG)
        self.state = dict(DEFAULT_STATE)
        self.open_targets = {}
        self.pending_flush_token = ""
        self.pending_flush_nb = ""
        self.last_rss_bytes = 0

    def is_en(self):
        return str(self.locale or "").strip().lower().startswith("en")

    def t(self):
        return STRINGS["en"] if self.is_en() else STRINGS["zh"]

    def localize_error(self, message):
        raw = str(message or "").strip()
        if self.is_en() and CHINESE_RE.search(raw):
            return self.t()["err_failed"]
        return raw or self.t()["err_failed"]

    @staticmethod
    def normalize_config(raw):
        cfg = dict(DEFAULT_CONFIG)
        if not isinstance(raw, dict):
            return cfg
        if raw.get("style") in STYLES:
            cfg["style"] = raw["style"]
        if raw.get("shape") in SHAPES:
            cfg["shape"] = raw["shape"]
        if isinstance(raw.get("bg_enabled"), bool):
            cfg["bg_enabled"] = raw["bg_enabled"]
        if raw.get("bg_backdrop") in ("poop-wallpaper", "poop-watermark"):
            cfg["bg_backdrop"] = raw["bg_backdrop"]
        if raw.get("bg_pattern") in PATTERNS:
            cfg["bg_pattern"] = raw["bg_pattern"]
        if raw.get("bg_density") in DENSITIES:
            cfg["bg_density"] = raw["bg_density"]
        if raw.get("bg_tint") in TINTS:
            cfg["bg_tint"] = raw["bg_tint"]
        if isinstance(raw.get("bg_dark_glow"), bool):
            cfg["bg_dark_glow"] = raw["bg_dark_glow"]
        if isinstance(raw.get("caption"), str):
            cfg["caption"] = raw["caption"][:60]
        if isinstance(raw.get("flush_secret"), str):
            cfg["flush_secret"] = raw["flush_secret"][:64]
        if isinstance(raw.get("archive_dir"), str):
            cfg["archive_dir"] = raw["archive_dir"]
        if raw.get("preview_mode") in PREVIEW_MODES:
            cfg["preview_mode"] = raw["preview_mode"]
        if isinstance(raw.get("selected_notebooks"), list):
            cfg["selected_notebooks"] = [str(x) for x in raw["selected_notebooks"] if isinstance(x, str) and x.strip()]
        if isinstance(raw.get("notebooks_configured"), bool):
            cfg["notebooks_configured"] = raw["notebooks_configured"]
        return cfg

    @staticmethod
    def normalize_state(raw):
        st = dict(DEFAULT_STATE)
        st["note_counts_by_nb"] = {}
        st["logs"] = []
        if not isinstance(raw, dict):
            return st
        for key in ("total_dropped", "total_flushed", "bg_toggles", "sidebar_hits", "dialog_opens"):
            val = raw.get(key)
            if isinstance(val, int) and val >= 0:
                st[key] = val
        if isinstance(raw.get("last_drop_at"), str):
            st["last_drop_at"] = raw["last_drop_at"][:32]
        if isinstance(raw.get("note_counts_by_nb"), dict):
            cleaned_by_nb = {}
            for nb_k, nb_map in list(raw["note_counts_by_nb"].items())[:64]:
                if not isinstance(nb_k, str) or not nb_k or not isinstance(nb_map, dict):
                    continue
                cleaned = {}
                for k, v in nb_map.items():
                    if isinstance(k, str) and k and isinstance(v, int) and v > 0:
                        cleaned[k] = v
                cleaned_by_nb[nb_k] = cleaned
            st["note_counts_by_nb"] = cleaned_by_nb
        if isinstance(raw.get("logs"), list):
            logs = []
            for item in raw["logs"][:20]:
                if isinstance(item, dict) and isinstance(item.get("event"), str):
                    logs.append({
                        "event": item["event"],
                        "note": str(item.get("note") or ""),
                        "notebook_root": str(item.get("notebook_root") or ""),
                        "count": int(item.get("count") or 0),
                        "time": str(item.get("time") or ""),
                        "tone": str(item.get("tone") or "info"),
                    })
            st["logs"] = logs
        return st

    def nb_key(self):
        return os.path.normpath(self.notebook_root) if self.notebook_root else "__default__"

    def note_counts(self):
        by_nb = self.state.setdefault("note_counts_by_nb", {})
        key = self.nb_key()
        if key not in by_nb or not isinstance(by_nb[key], dict):
            by_nb[key] = {}
        return by_nb[key]

    def set_note_counts(self, counts):
        by_nb = self.state.setdefault("note_counts_by_nb", {})
        by_nb[self.nb_key()] = dict(counts)

    def safe_call(self, bridge, method, params=None):
        try:
            return bridge.call_host(method, params or {})
        except HostRPCError as exc:
            if exc.code in (-32601, -32005):
                return None
            raise

    def best_effort_call(self, bridge, method, params=None):
        try:
            return bridge.call_host(method, params or {})
        except HostRPCError:
            return None

    def load_persisted(self, bridge):
        res_cfg = self.safe_call(bridge, "host.storage.get", {"key": STORAGE_CONFIG})
        if isinstance(res_cfg, dict) and res_cfg.get("found"):
            self.config = self.normalize_config(res_cfg.get("value"))
        res_st = self.safe_call(bridge, "host.storage.get", {"key": STORAGE_STATE})
        if isinstance(res_st, dict) and res_st.get("found"):
            self.state = self.normalize_state(res_st.get("value"))

    def save_config(self, bridge):
        self.safe_call(bridge, "host.storage.set", {"key": STORAGE_CONFIG, "value": self.config})

    def save_state(self, bridge):
        self.safe_call(bridge, "host.storage.set", {"key": STORAGE_STATE, "value": self.state})

    def append_log(self, event, note="", count=0, tone="success", notebook_root=None):
        nb = self.notebook_root if notebook_root is None else str(notebook_root)
        self.state["logs"].insert(0, {
            "event": event,
            "note": note,
            "notebook_root": nb if note else "",
            "count": int(count),
            "time": now_hhmm(),
            "tone": tone,
        })
        self.state["logs"] = self.state["logs"][:20]

    def register_open_target(self, notebook_root, rel_path):
        if not notebook_root or not rel_path or not is_markdown_path(rel_path):
            return ""
        digest = hashlib.sha256(f"{notebook_root}\x00{rel_path}".encode("utf-8")).hexdigest()[:16]
        action_id = f"open_target:{digest}"
        if len(self.open_targets) >= 256 and action_id not in self.open_targets:
            self.open_targets.pop(next(iter(self.open_targets)))
        self.open_targets[action_id] = (notebook_root, rel_path)
        return action_id

    def list_notebooks(self, bridge):
        res = self.safe_call(bridge, "host.notebooks.list", {})
        if isinstance(res, dict) and isinstance(res.get("notebooks"), list):
            return res["notebooks"]
        if self.notebook_root:
            return [{"path": self.notebook_root, "name": os.path.basename(self.notebook_root) or self.notebook_root, "active": True}]
        return []

    def ensure_selected_notebooks(self, notebooks):
        if not self.config["notebooks_configured"] and not self.config["selected_notebooks"] and notebooks:
            self.config["selected_notebooks"] = [nb["path"] for nb in notebooks if nb.get("path")]

    def is_active_notebook_allowed(self, bridge):
        if not self.notebook_root:
            return True
        if not self.config["notebooks_configured"] and not self.config["selected_notebooks"]:
            return True
        return self.notebook_root in self.config["selected_notebooks"]

    def count_markers(self, content):
        if not isinstance(content, str):
            return 0
        return sum(1 for line, eligible in iter_markdown_lines(content) if eligible and match_marker_line(line))

    def strip_markers(self, content):
        if not isinstance(content, str):
            return "", 0
        items = list(iter_markdown_lines(content))
        n_items = len(items)

        def is_bare_bq_sep(raw_line):
            stripped_nl = raw_line.rstrip("\r\n")
            cols, idx = leading_columns(stripped_nl, 0)
            return cols <= 3 and stripped_nl[idx:].rstrip(" \t") == ">"

        def is_nonwrap_drop(idx_pos):
            if idx_pos >= n_items:
                return False
            raw, elig = items[idx_pos]
            if not elig:
                return False
            mm = match_marker_line(raw)
            if not mm:
                return False
            k = mm.group("kind") or mm.group("legacy") or "classic"
            return k not in ("wrap-start", "wrap-end")

        kept = []
        removed = 0
        in_wrap = False
        in_wrap_legacy = False
        eat_next_blank = False
        prev_removed_drop = False
        pending_bq_sep = False
        pending_blank_sep = False
        for i, (line, eligible) in enumerate(items):
            if eat_next_blank:
                eat_next_blank = False
                if line in ("\n", "\r\n", "\r") or is_bare_bq_sep(line):
                    continue
            if eligible:
                m = match_marker_line(line)
                if m:
                    is_legacy = m.group("kind") is None
                    kind = m.group("kind") or m.group("legacy") or "classic"
                    meta = m.group("meta") or ""
                    meta_flags = set(meta.split(",")) if meta else set()
                    if kind == "wrap-start":
                        in_wrap = True
                        in_wrap_legacy = is_legacy
                        eat_next_blank = not is_legacy
                        prev_removed_drop = False
                        pending_bq_sep = False
                        pending_blank_sep = False
                    elif kind == "wrap-end":
                        if in_wrap:
                            if not in_wrap_legacy:
                                if kept and (kept[-1] in ("\n", "\r\n", "\r") or is_bare_bq_sep(kept[-1])):
                                    kept.pop()
                            if not line.endswith(("\n", "\r")) and kept and kept[-1].endswith("\n"):
                                kept[-1] = kept[-1][:-1]
                                if kept[-1] == "":
                                    kept.pop()
                        in_wrap = False
                        in_wrap_legacy = False
                        eat_next_blank = False
                        prev_removed_drop = False
                        pending_bq_sep = False
                        pending_blank_sep = False
                    else:
                        if pending_bq_sep and kept:
                            kept.pop()
                        elif pending_blank_sep and kept:
                            kept.pop()
                        elif "noeol" in meta_flags and len(kept) >= 2 and kept[-1] in ("\n", "\r\n", "\r"):
                            kept.pop()
                            if kept[-1].endswith("\r\n"):
                                kept[-1] = kept[-1][:-2]
                            elif kept[-1].endswith(("\n", "\r")):
                                kept[-1] = kept[-1][:-1]
                        elif "sep1" in meta_flags and kept and kept[-1] in ("\n", "\r\n", "\r"):
                            kept.pop()
                        elif "keepblank" in meta_flags:
                            pass
                        elif (not is_legacy) and len(kept) >= 2 and kept[-1] in ("\n", "\r\n", "\r") and kept[-2] not in ("\n", "\r\n", "\r"):
                            next_is_eof = i + 1 >= n_items
                            next_is_blank = (not next_is_eof) and (items[i + 1][0] in ("\n", "\r\n", "\r"))
                            next_is_drop = is_nonwrap_drop(i + 1) or (
                                (i + 2 < n_items) and is_bare_bq_sep(items[i + 1][0]) and is_nonwrap_drop(i + 2)
                            )
                            if prev_removed_drop or next_is_eof or next_is_blank or next_is_drop:
                                kept.pop()
                        prev_removed_drop = True
                        pending_bq_sep = False
                        pending_blank_sep = False
                    removed += 1
                    continue
            if prev_removed_drop and not pending_bq_sep and not pending_blank_sep and is_bare_bq_sep(line):
                pending_bq_sep = True
            elif prev_removed_drop and not pending_bq_sep and not pending_blank_sep and line in ("\n", "\r\n", "\r") and is_nonwrap_drop(i + 1):
                pending_blank_sep = True
            else:
                prev_removed_drop = False
                pending_bq_sep = False
                pending_blank_sep = False
            kept.append(line)
        return "".join(kept), removed

    def scan_notebook_markers(self, bridge):
        try:
            res = bridge.call_host("host.notes.list", {})
        except HostRPCError:
            return self.note_counts(), set(), False
        if not isinstance(res, dict) or not isinstance(res.get("notes"), list):
            return self.note_counts(), set(), False
        prev_counts = self.note_counts()
        counts = {}
        failed_paths = set()
        for item in res["notes"]:
            rel = item.get("path")
            if not isinstance(rel, str) or not rel:
                continue
            try:
                note = bridge.call_host("host.notes.read", {"path": rel})
            except HostRPCError:
                failed_paths.add(rel)
                if rel in prev_counts:
                    counts[rel] = prev_counts[rel]
                continue
            n = self.count_markers(note.get("content", ""))
            if n > 0:
                counts[rel] = n
        self.set_note_counts(counts)
        return counts, failed_paths, True

    def active_counts_summary(self):
        counts = self.note_counts()
        total = sum(counts.values())
        notes = len(counts)
        return total, notes

    def effective_caption(self):
        raw = str(self.config.get("caption") or "")
        raw = re.sub(r"[\r\n\u2028\u2029]+", " ", raw)
        while "<!--" in raw or "-->" in raw:
            raw = raw.replace("-->", "").replace("<!--", "")
        raw = raw.replace("`", "'")
        raw = EMOJI_RE.sub("", raw)
        while True:
            trimmed = raw.strip().rstrip("\\").strip()
            if trimmed == raw:
                break
            raw = trimmed
        if raw and not (self.is_en() and CHINESE_RE.search(raw)):
            probe = f"{raw}{DROP_SIGNATURE}"
            is_opener = (
                strip_single_bq_prefix(raw, 0)[0] is not None
                or strip_single_bq_prefix(probe, 0)[0] is not None
                or bool(ATX_HEADING_RE.match(raw))
                or bool(ATX_HEADING_RE.match(probe))
                or bool(THEMATIC_BREAK_RE.match(raw))
                or bool(THEMATIC_BREAK_RE.match(probe))
                or bool(SETEXT_UNDERLINE_RE.match(raw))
                or bool(SETEXT_UNDERLINE_RE.match(probe))
                or bool(FENCE_OPEN_RE.match(raw))
                or bool(FENCE_OPEN_RE.match(probe))
                or bool(LIST_ITEM_RE.match(raw))
                or bool(LIST_ITEM_RE.match(probe))
                or html_block_end_kind(raw, allow_type7=True) is not None
                or html_block_end_kind(probe, allow_type7=True) is not None
            )
            cand = f"· {raw}" if is_opener else raw
            probes = (
                f"> {cand}{DROP_SIGNATURE}",
                f"> {cand} #1{DROP_SIGNATURE}",
                f"> --- {cand} ---{DROP_SIGNATURE}",
                f"> · {cand} ·{DROP_SIGNATURE}",
                f"> prev\n> {cand}{DROP_SIGNATURE}",
            )
            if all(self.count_markers(p) == 1 for p in probes):
                return cand
        return self.t()["default_caption"]

    def build_drop_block(self, wrapped_text="", first_meta=""):
        caption = self.effective_caption()
        shape = self.config.get("shape", "classic")
        style = self.config.get("style", "normal")
        repeat = {"shy": 1, "normal": 1, "wild": 3}.get(style, 1)
        if wrapped_text:
            # Always end wrap-start with LF ('\n\n') so a leading LF in wrapped_text
            # never merges with a trailing CR separator into a single CRLF line.
            if wrapped_text.endswith("\r\n"):
                return f"> {caption}{drop_sig('wrap-start')}\n\n{wrapped_text}\n> ···{drop_sig('wrap-end')}\r\n"
            if wrapped_text.endswith("\n"):
                return f"> {caption}{drop_sig('wrap-start')}\n\n{wrapped_text}\n> ···{drop_sig('wrap-end')}\n"
            if wrapped_text.endswith("\r"):
                return f"> {caption}{drop_sig('wrap-start')}\n\n{wrapped_text}\r> ···{drop_sig('wrap-end')}\r"
            return f"> {caption}{drop_sig('wrap-start')}\n\n{wrapped_text}\n\n> ···{drop_sig('wrap-end')}"
        lines = []
        for idx in range(repeat):
            suffix = f" #{idx + 1}" if repeat > 1 else ""
            meta = first_meta if idx == 0 else ""
            if shape == "ribbon":
                lines.append(f"> --- {caption}{suffix} ---{drop_sig('ribbon', meta)}")
            elif shape == "pellet":
                lines.append(f"> · {caption}{suffix} ·{drop_sig('pellet', meta)}")
            else:
                lines.append(f"> {caption}{suffix}{drop_sig('classic', meta)}")
        return "\n\n".join(lines)

    def is_editor_wrap_safe(self, text):
        """Return True iff text survives Block's block parser + serializer + strip_markers losslessly."""
        if not isinstance(text, str) or not text:
            return False
        # Block's InsertMarkdown normalizes CR/CRLF to LF and trims block boundaries.
        if "\r" in text or text.startswith("\n") or text.endswith("\n"):
            return False
        # Consecutive top-level blank lines (\n\n\n+) collapse to a single blank line
        # when parsed into blocks and serialized back (inside fenced/HTML blocks they survive).
        lines = split_md_lines(text)
        if lines and (_is_bare_bq_sep(lines[0]) or _is_bare_bq_sep(lines[-1])):
            return False
        in_fence = False
        fence_ch = ""
        fence_len = 0
        html_kind = None
        blank_run = 0
        prev_was_bq = False
        saw_blank_after_bq = False
        for raw in lines:
            s = raw.rstrip("\n")
            is_blank = s.strip(" \t") == ""
            cols, idx = leading_columns(s, 0)
            if in_fence:
                if not is_blank and cols <= 3:
                    mc = re.match(r"^(`{3,}|~{3,})[ \t]*$", s[idx:])
                    if mc and mc.group(1)[0] == fence_ch and len(mc.group(1)) >= fence_len:
                        in_fence = False
                blank_run = 0
                prev_was_bq = False
                saw_blank_after_bq = False
                continue
            if html_kind is not None:
                if html_kind == "blank" and is_blank:
                    html_kind = None
                    blank_run = 1
                    continue
                if html_block_closes(html_kind, s):
                    html_kind = None
                blank_run = 0
                prev_was_bq = False
                saw_blank_after_bq = False
                continue
            if is_blank:
                blank_run += 1
                if blank_run >= 2:
                    return False
                if prev_was_bq:
                    saw_blank_after_bq = True
                continue
            blank_run = 0
            cur_is_bq = strip_single_bq_prefix(s, 0)[0] is not None
            if prev_was_bq and not saw_blank_after_bq and not cur_is_bq:
                # Block's parser does not support CommonMark lazy blockquote continuations
                # ("> A\nlazy" splits into "> A\n\nlazy"), so wrapping cannot round-trip losslessly.
                return False
            if cur_is_bq and saw_blank_after_bq:
                # Block's serializer merges consecutive separate blockquotes ("> A\n\n> B")
                # into a single blockquote ("> A\n>\n> B"), so wrapping cannot round-trip losslessly.
                return False
            prev_was_bq = cur_is_bq
            saw_blank_after_bq = False
            if cols <= 3:
                mo = FENCE_OPEN_RE.match(s)
                if mo and not (mo.group(1)[0] == "`" and "`" in mo.group(2)):
                    in_fence = True
                    fence_ch = mo.group(1)[0]
                    fence_len = len(mo.group(1))
                    continue
                hk = html_block_end_kind(s, allow_type7=True)
                if hk is not None and not html_block_closes(hk, s):
                    html_kind = hk
                    continue
        if in_fence or html_kind in ("type1", "comment", "pi", "decl", "cdata"):
            return False
        return True

    def sync_host_ui(self, bridge):
        t = self.t()
        total, note_n = self.active_counts_summary()

        # 1. Custom vector editor backdrop
        self.best_effort_call(bridge, "host.ui.set_backdrop", {
            "id": self.config["bg_backdrop"],
            "enabled": bool(self.config["bg_enabled"]),
            "pattern": self.config["bg_pattern"],
            "density": self.config["bg_density"],
            "opacity": DENSITY_OPACITY.get(self.config["bg_density"], 0.10),
            "tint": self.config["bg_tint"],
            "dark_glow": bool(self.config["bg_dark_glow"]),
        })

        # 2. Titlebar button badge (active highlight is managed atomically by host panel state)
        badge_str = str(min(total, 999)) if total > 0 else ""
        self.best_effort_call(bridge, "host.titlebar.set_button", {
            "id": "poop-panel",
            "badge": badge_str,
        })

        # 3. Bottom status bar with icon
        if total > 0:
            st_text = t["status_count"].format(n=total)
            st_tip = t["status_tip_count"].format(n=total, notes=note_n)
        else:
            st_text = t["status_clean"]
            st_tip = t["status_tip_clean"]
        self.best_effort_call(bridge, "host.status.set", {
            "id": "poop-counter",
            "text": st_text,
            "tooltip": st_tip,
            "show_plugin_icon": True,
        })

        # 4. Left sidebar file-tree badges (capped to host limit MAX_SIDEBAR_BADGES)
        if self.notebook_root:
            entries = {}
            ranked = sorted(
                ((rel, cnt) for rel, cnt in self.note_counts().items() if cnt > 0),
                key=lambda kv: (-kv[1], kv[0]),
            )[:MAX_SIDEBAR_BADGES]
            for rel, cnt in ranked:
                entries[rel] = {
                    "text": str(min(cnt, 999)),
                    "tooltip": t["badge_tip_note"].format(n=cnt),
                    "tone": "warning" if cnt >= 5 else "accent",
                }
            self.best_effort_call(bridge, "host.sidebar.set_badges", {
                "badge_id": "poop-mark",
                "entries": entries,
                "clear": len(entries) == 0,
            })

    def refresh_other_surfaces(self, bridge, current_surface=""):
        for surf in ALL_SURFACES:
            if surf == current_surface:
                continue
            self.best_effort_call(bridge, "host.ui.refresh", {"surface": surf})

    def show_toast(self, bridge, message, tone="info"):
        self.best_effort_call(bridge, "host.ui.toast", {
            "message": message,
            "tone": tone,
            "show_plugin_icon": True,
        })

    def report_progress(self, bridge, done, total, label=""):
        if "action_progress" not in self.capabilities:
            return
        payload = {"done": int(done), "total": int(total)}
        if label:
            payload["label"] = label
        bridge.notify_host("host.action.progress", payload)

    def resolve_active_note(self, bridge):
        res = self.safe_call(bridge, "host.notes.active", {})
        if isinstance(res, dict) and isinstance(res.get("path"), str) and res["path"] != "":
            return res["path"]
        return ""

    def resolve_target_note(self, bridge, explicit_note="", strict=False, active_only=False):
        if isinstance(explicit_note, str) and explicit_note != "":
            return explicit_note
        if strict:
            return ""
        active = self.resolve_active_note(bridge)
        if active:
            return active
        if active_only:
            return ""
        listed = self.safe_call(bridge, "host.notes.list", {})
        if isinstance(listed, dict) and listed.get("notes"):
            return str(listed["notes"][0].get("path") or "")
        return ""

    def drop_into_note_file(self, bridge, note_rel, wrapped_text=""):
        t = self.t()
        if not note_rel:
            return False, "warning", t["toast_no_note"]
        try:
            read_res = bridge.call_host("host.notes.read", {"path": note_rel})
        except HostRPCError as exc:
            return False, "error", self.localize_error(exc.message)
        content = str(read_res.get("content") or "")
        rev = read_res.get("revision")
        orig_lines = split_md_lines(content)
        if not orig_lines:
            sep, eol, first_meta = "", "\n", "keepblank"
        elif orig_lines[-1] in ("\r\n", "\n", "\r"):
            sep, eol, first_meta = "", orig_lines[-1], "keepblank"
        elif orig_lines[-1].endswith("\r\n"):
            sep, eol, first_meta = "\r\n", "\r\n", "sep1"
        elif orig_lines[-1].endswith("\n"):
            sep, eol, first_meta = "\n", "\n", "sep1"
        elif orig_lines[-1].endswith("\r"):
            sep, eol, first_meta = "\r", "\r", "sep1"
        else:
            sep, eol, first_meta = "\n\n", "\n", "noeol"
        block = self.build_drop_block(wrapped_text, first_meta="" if wrapped_text else first_meta)
        if wrapped_text:
            rt_text, rt_rem = self.strip_markers(block)
            if rt_rem != 2 or rt_text != wrapped_text:
                return False, "warning", t["toast_unsafe_wrap"]
        next_content = content + sep + block + eol
        prev_cnt = self.count_markers(content)
        expected_added = self.count_markers(block)
        new_cnt = self.count_markers(next_content)
        if expected_added <= 0 or new_cnt != prev_cnt + expected_added:
            return False, "warning", t["toast_unsafe_container"]
        if not wrapped_text:
            base_clean, _ = self.strip_markers(content)
            next_clean, next_rem = self.strip_markers(next_content)
            if next_rem != prev_cnt + expected_added or next_clean != base_clean:
                return False, "warning", t["toast_unsafe_container"]
        write_params = {"path": note_rel, "content": next_content}
        if isinstance(rev, str):
            write_params["expected_revision"] = rev
        try:
            bridge.call_host("host.notes.write", write_params)
        except HostRPCError as exc:
            if exc.code == -32006:
                return False, "warning", t["toast_conflict"].format(note=note_rel)
            return False, "error", self.localize_error(exc.message)
        self.note_counts()[note_rel] = new_cnt
        self.state["total_dropped"] += expected_added
        self.state["last_drop_at"] = now_hhmm()
        self.append_log("drop", note=note_rel, count=expected_added, tone="success")
        self.save_state(bridge)
        self.sync_host_ui(bridge)
        if new_cnt >= 5:
            return True, "warning", t["toast_heavy_warn"].format(note=note_rel, n=new_cnt)
        return True, "success", t["toast_dropped_note"].format(note=note_rel, n=expected_added)

    def drop_at_editor_or_note(self, bridge, note_rel="", selection="", wrap_selection=False, source=""):
        t = self.t()
        target = self.resolve_target_note(bridge, note_rel)
        if not self.is_active_notebook_allowed(bridge):
            self.append_log("blocked", note=target or "notebook", tone="danger")
            self.save_state(bridge)
            return False, "error", t["toast_blocked_nb"]
        if source == "sidebar_menu":
            self.state["sidebar_hits"] += 1
            return self.drop_into_note_file(bridge, target)

        sel_text = selection
        if wrap_selection and not sel_text:
            sel_res = self.safe_call(bridge, "host.editor.selection", {})
            if isinstance(sel_res, dict):
                sel_text = str(sel_res.get("text") or "")
                if not target and sel_res.get("note"):
                    target = str(sel_res["note"])

        is_wrapping = bool(wrap_selection and sel_text)
        block = self.build_drop_block(sel_text if is_wrapping else "")
        if is_wrapping:
            if not self.is_editor_wrap_safe(sel_text):
                return False, "warning", t["toast_unsafe_wrap"]
            rt_text, rt_rem = self.strip_markers(block)
            if rt_rem != 2 or rt_text != sel_text:
                return False, "warning", t["toast_unsafe_wrap"]

        inserted = None
        if is_wrapping:
            insert_params = {"text": block, "mode": "replace"}
            if target:
                insert_params["note"] = target
            try:
                inserted = self.safe_call(bridge, "host.editor.insert", insert_params)
            except HostRPCError as exc:
                if exc.code == -32006:
                    return False, "warning", t["toast_conflict"].format(note=target or "note")
                return False, "warning", t["toast_unsafe_wrap"]
            if not (isinstance(inserted, dict) and inserted.get("ok")):
                return False, "warning", t["toast_unsafe_wrap"]
        elif "editor_insert_mode" in self.capabilities:
            insert_params = {"text": "\n" + block + "\n", "mode": "insert"}
            if target:
                insert_params["note"] = target
            try:
                inserted = self.safe_call(bridge, "host.editor.insert", insert_params)
            except HostRPCError as exc:
                if exc.code == -32006:
                    return False, "warning", t["toast_conflict"].format(note=target or "note")
                inserted = None

        if isinstance(inserted, dict) and inserted.get("ok"):
            added = self.count_markers(block)
            if target:
                counts = self.note_counts()
                counts[target] = counts.get(target, 0) + added
            self.state["total_dropped"] += added
            self.state["last_drop_at"] = now_hhmm()
            if is_wrapping:
                self.append_log("wrap", note=target or "note", count=added, tone="success")
                msg = t["toast_wrapped_sel"]
            else:
                self.append_log("drop", note=target or "note", count=added, tone="success")
                msg = t["toast_no_selection"] if wrap_selection else t["toast_dropped_editor"].format(n=added)
            self.save_state(bridge)
            self.sync_host_ui(bridge)
            return True, "success", msg

        return self.drop_into_note_file(bridge, target)

    def flush_single_note(self, bridge, note_rel, strict=False):
        t = self.t()
        # Flushing "current page" must ONLY target the active note (never fall back to notes.list[0]).
        target = self.resolve_target_note(bridge, note_rel, strict=strict, active_only=True)
        if not target:
            return False, "warning", t["toast_no_note"]
        try:
            read_res = bridge.call_host("host.notes.read", {"path": target})
        except HostRPCError as exc:
            return False, "error", self.localize_error(exc.message)
        content = str(read_res.get("content") or "")
        rev = read_res.get("revision")
        cleaned, removed = self.strip_markers(content)
        if removed == 0:
            self.note_counts().pop(target, None)
            self.save_state(bridge)
            self.sync_host_ui(bridge)
            return True, "info", t["toast_note_clean"].format(note=target)
        write_params = {"path": target, "content": cleaned}
        if isinstance(rev, str):
            write_params["expected_revision"] = rev
        try:
            bridge.call_host("host.notes.write", write_params)
        except HostRPCError as exc:
            if exc.code == -32006:
                return False, "warning", t["toast_conflict"].format(note=target)
            return False, "error", self.localize_error(exc.message)
        self.note_counts().pop(target, None)
        self.state["total_flushed"] += removed
        self.append_log("flush_note", note=target, count=removed, tone="info")
        self.save_state(bridge)
        self.sync_host_ui(bridge)
        return True, "success", t["toast_flushed_note"].format(note=target, n=removed)

    def flush_all_notes(self, bridge):
        t = self.t()
        _, scan_failed_paths, list_ok = self.scan_notebook_markers(bridge)
        if not list_ok:
            return False, "error", t["toast_list_failed"]
        counts = self.note_counts()
        targets = sorted(counts.keys())
        total_removed = 0
        touched_notes = 0
        conflict_paths = set()
        failed_paths = set(scan_failed_paths)
        total_steps = max(len(targets), 1)
        for idx, rel in enumerate(targets, 1):
            self.report_progress(bridge, idx - 1, total_steps, t["progress_flush"])
            try:
                read_res = bridge.call_host("host.notes.read", {"path": rel})
            except HostRPCError:
                failed_paths.add(rel)
                continue
            cleaned, removed = self.strip_markers(str(read_res.get("content") or ""))
            if removed <= 0:
                counts.pop(rel, None)
                failed_paths.discard(rel)
                continue
            write_params = {"path": rel, "content": cleaned}
            if isinstance(read_res.get("revision"), str):
                write_params["expected_revision"] = read_res["revision"]
            try:
                bridge.call_host("host.notes.write", write_params)
                counts.pop(rel, None)
                failed_paths.discard(rel)
                total_removed += removed
                touched_notes += 1
            except HostRPCError as exc:
                if exc.code == -32006:
                    conflict_paths.add(rel)
                    failed_paths.discard(rel)
                else:
                    failed_paths.add(rel)
            self.report_progress(bridge, idx, total_steps, t["progress_flush"])

        conflicts = sorted(conflict_paths)
        failed_count = len(failed_paths)
        incomplete = bool(conflicts or failed_count > 0)
        if total_removed > 0:
            self.state["total_flushed"] += total_removed
            self.append_log("flush_all", count=total_removed, tone="warning" if incomplete else "info")
        self.save_state(bridge)
        self.sync_host_ui(bridge)

        if incomplete:
            if len(conflicts) == 1 and failed_count == 0 and total_removed == 0:
                return False, "warning", t["toast_conflict"].format(note=conflicts[0])
            return False, "warning", t["toast_flush_partial"].format(
                n=total_removed, conflicts=len(conflicts), failed=failed_count
            )
        if total_removed > 0:
            return True, "success", t["toast_flushed_all"].format(n=total_removed, notes=touched_notes)
        return True, "info", t["toast_nothing_flush"]

    def export_developer_guide(self):
        archive_dir = self.config.get("archive_dir") or ""
        if archive_dir:
            if not os.path.isdir(archive_dir):
                return None, "", "invalid"
            out_dir = archive_dir
            dest_label = os.path.basename(archive_dir.rstrip(os.sep)) or archive_dir
        else:
            out_dir = self.downloads_dir or self.data_dir or os.getcwd()
            dest_label = "Downloads" if self.is_en() else "下载目录"
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError:
                return None, "", "write_failed"
        filename = "block-poop-everywhere-guide-en.md" if self.is_en() else "block-poop-everywhere-guide.md"
        out_path = os.path.join(out_dir, filename)
        total, notes = self.active_counts_summary()
        if self.is_en():
            lines = [
                "# Block Plugin Extension Points Reference (Poop Everywhere)",
                "",
                f"- Plugin ID: `{PLUGIN_ID}` v{PLUGIN_VERSION}",
                f"- Host Version: `{self.host_version or 'unknown'}`",
                f"- Active Drops: {total} across {notes} note(s)",
                "",
                "## All 17 Connected Extension Surfaces",
                "",
                "| Extension Key | Required Permission |",
                "| --- | --- |",
            ]
        else:
            lines = [
                "# Block 插件全扩展点参考手册（到处拉屎）",
                "",
                f"- 插件 ID：`{PLUGIN_ID}` v{PLUGIN_VERSION}",
                f"- 宿主版本：`{self.host_version or 'unknown'}`",
                f"- 当前统计：共 {total} 坨，波及 {notes} 篇笔记",
                "",
                "## 已接入的 17 项扩展点",
                "",
                "| 扩展点键名 | 所需权限 |",
                "| --- | --- |",
            ]
        for key, perm in EXTENSION_MAP:
            lines.append(f"| `{key}` | `{perm}` |")
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError:
            return None, "", "write_failed"
        return out_path, dest_label, ""

    def render_log_entry(self, entry):
        t = self.t()
        ev = entry.get("event", "")
        note = entry.get("note", "")
        cnt = int(entry.get("count", 0))
        tm = entry.get("time", "")
        tone = entry.get("tone", "info")
        if ev == "drop":
            title = t["log_drop"].format(note=note, n=cnt)
            status = t["log_status_ok"]
        elif ev == "wrap":
            title = t["log_wrap"].format(note=note)
            status = t["log_status_ok"]
        elif ev == "flush_note":
            title = t["log_flush_note"].format(note=note, n=cnt)
            status = t["log_status_clean"]
        elif ev == "flush_all":
            title = t["log_flush_all"].format(n=cnt)
            status = t["log_status_clean"]
        elif ev == "bg_on":
            title = t["log_bg_on"]
            status = t["log_status_info"]
        elif ev == "bg_off":
            title = t["log_bg_off"]
            status = t["log_status_info"]
        elif ev == "blocked":
            title = t["log_blocked"].format(note=note)
            status = t["log_status_warn"]
        elif ev == "saved":
            title = t["log_saved"]
            status = t["log_status_ok"]
        elif ev == "theme":
            title = t["log_theme"]
            status = t["log_status_info"]
        elif ev == "note_saved":
            title = t["log_note_saved"].format(note=note, n=cnt)
            status = t["log_status_info"]
        else:
            title = ev or "event"
            status = t["log_status_info"]

        out = {
            "title": title,
            "time": tm,
            "status": status,
            "tone": tone,
        }
        entry_nb = str(entry.get("notebook_root") or "")
        if entry_nb and note and is_markdown_path(note) and "log_actions" in self.capabilities:
            act_id = self.register_open_target(entry_nb, note)
            if act_id:
                out["action_id"] = act_id
                out["tooltip"] = t["click_to_open"].format(note=note)
        return out

    def build_preview_item(self):
        t = self.t()
        mode = self.config.get("preview_mode", "article")
        total, notes = self.active_counts_summary()
        sample_block = self.build_drop_block()
        palette = "warm" if self.config["bg_tint"] == "warm" else ("ink" if self.config["bg_dark_glow"] else "paper")

        if mode == "diff":
            return {
                "kind": "preview",
                "preview": {
                    "variant": "diff",
                    "palette": palette,
                    "title": t["pv_diff_title"],
                    "badge": t["pv_badge"],
                    "before": f"# Sample Note\n{sample_block}\nUser paragraph remains intact.",
                    "after": "# Sample Note\nUser paragraph remains intact.",
                },
            }
        if mode == "cards":
            cards = [
                {"badge": "Titlebar", "title": "3 Buttons + Badges", "body": "Panel toggle, instant drop, and flush modal"},
                {"badge": "Sidebar", "title": "Section + File Badges", "body": "Collapsible card, row counters, and tree menu"},
                {"badge": "Backdrop", "title": "Vector Motifs", "body": f"{self.config['bg_pattern']} / {self.config['bg_density']} / safe opacity"},
            ] if self.is_en() else [
                {"badge": "顶栏", "title": "3 按钮 + 动态角标", "body": "面板开关、快捷拉一坨与确认冲水"},
                {"badge": "侧栏", "title": "侧栏分区 + 文件树角标", "body": "可折叠战报、行尾数字与右键菜单"},
                {"badge": "背景", "title": "自定义矢量水印", "body": f"{t['patterns'][self.config['bg_pattern']]} · {t['densities'][self.config['bg_density']]}"},
            ]
            return {
                "kind": "preview",
                "preview": {
                    "variant": "cards",
                    "palette": "ocean",
                    "title": t["pv_cards_title"],
                    "badge": t["card_map_badge"],
                    "cards": cards,
                },
            }
        if mode == "plan":
            body = (
                f"1. Scan {max(notes, 1)} note(s) via host.notes.read\n"
                f"2. Strip {total} signed drop line(s) using expected_revision\n"
                "3. Clear sidebar badges, titlebar badge, and backdrop\n"
                "4. Sync status bar and notify with icon toast"
            ) if self.is_en() else (
                f"1. 通过 host.notes.read 扫描 {max(notes, 1)} 篇笔记\n"
                f"2. 携带 expected_revision 精确移除 {total} 条专属标记行\n"
                "3. 清空文件树角标、顶栏角标与编辑区背景\n"
                "4. 同步状态栏并弹出带图标 Toast"
            )
            return {
                "kind": "preview",
                "preview": {
                    "variant": "plan",
                    "palette": "ocean",
                    "title": t["pv_plan_title"],
                    "badge": t["pv_badge"],
                    "body": body,
                },
            }
        return {
            "kind": "preview",
            "preview": {
                "variant": "article",
                "palette": palette,
                "title": t["pv_title"],
                "badge": t["pv_badge"],
                "subtitle": f"{t['styles'][self.config['style']]} / {t['shapes'][self.config['shape']]}",
                "body": f"# {t['title']}\n## {t['shapes'][self.config['shape']]}\n{sample_block}",
            },
        }

    def merge_form_values(self, bridge, values, surface):
        if not isinstance(values, dict) or not values:
            return False
        changed = False
        bg_changed = False
        is_settings = surface in (SURFACE_SETTINGS, SURFACE_APPEARANCE)
        prev_bg_enabled = self.config["bg_enabled"]

        for key, allowed in (
            ("style", STYLES),
            ("shape", SHAPES),
            ("bg_backdrop", ("poop-wallpaper", "poop-watermark")),
            ("bg_pattern", PATTERNS),
            ("bg_density", DENSITIES),
            ("bg_tint", TINTS),
            ("preview_mode", PREVIEW_MODES),
        ):
            is_background = key.startswith("bg_")
            if is_background and not is_settings:
                continue
            val = values.get(key)
            if isinstance(val, str) and val in allowed and self.config[key] != val:
                self.config[key] = val
                changed = True
                bg_changed |= is_background

        if is_settings:
            for key in ("bg_enabled", "bg_dark_glow"):
                val = values.get(key)
                if isinstance(val, bool) and self.config[key] != val:
                    self.config[key] = val
                    changed = True
                    bg_changed = True

        if isinstance(values.get("caption"), str) and values["caption"][:60] != self.config["caption"]:
            self.config["caption"] = values["caption"][:60]
            changed = True
        if isinstance(values.get("flush_secret"), str) and values["flush_secret"][:64] != self.config["flush_secret"]:
            self.config["flush_secret"] = values["flush_secret"][:64]
            changed = True
        if isinstance(values.get("archive_dir"), str) and values["archive_dir"] != self.config["archive_dir"]:
            self.config["archive_dir"] = values["archive_dir"]
            changed = True
        if isinstance(values.get("selected_notebooks"), list):
            next_nbs = [str(x) for x in values["selected_notebooks"] if isinstance(x, str) and x.strip()]
            if next_nbs != self.config["selected_notebooks"] or not self.config["notebooks_configured"]:
                self.config["selected_notebooks"] = next_nbs
                self.config["notebooks_configured"] = True
                changed = True

        if changed:
            self.save_config(bridge)
        if bg_changed:
            if self.config["bg_enabled"] != prev_bg_enabled:
                self.state["bg_toggles"] += 1
                self.append_log("bg_on" if self.config["bg_enabled"] else "bg_off", tone="info")
                self.save_state(bridge)
            self.sync_host_ui(bridge)
            self.refresh_other_surfaces(bridge, surface)
        return changed

    def render_settings_page(self, bridge):
        t = self.t()
        notebooks = self.list_notebooks(bridge)
        self.ensure_selected_notebooks(notebooks)
        total, notes = self.active_counts_summary()

        perf = self.best_effort_call(bridge, "host.perf.snapshot", {"refresh_disk": False})
        if isinstance(perf, dict) and isinstance(perf.get("rss_bytes"), (int, float)):
            self.last_rss_bytes = int(perf["rss_bytes"])

        nb_options = []
        for nb in notebooks:
            path = str(nb.get("path") or "")
            if not path:
                continue
            opt = {
                "value": path,
                "label": str(nb.get("name") or os.path.basename(path) or path),
                "detail": path,
                "tooltip": path,
            }
            if nb.get("active"):
                opt["badge"] = t["badge_current"]
            nb_options.append(opt)

        body_weight = max(self.state["total_dropped"], total, 1)
        bg_weight = max(self.state["bg_toggles"] + (1 if self.config["bg_enabled"] else 0), 1)
        sidebar_weight = max(self.state["sidebar_hits"] + notes, 1)
        dialog_weight = max(self.state["dialog_opens"] + self.state["total_flushed"], 1)
        interaction_total = body_weight + bg_weight + sidebar_weight + dialog_weight

        log_entries = [self.render_log_entry(item) for item in self.state["logs"][:8]]
        map_entries = [
            {"title": key, "status": "→", "time": perm, "tooltip": f"{key} ({perm})"}
            for key, perm in EXTENSION_MAP
        ]

        metrics = [
            {"label": t["m_active"], "value": t["m_unit_drop"].format(n=total), "tone": "ai_sessions"},
            {"label": t["m_notes"], "value": t["m_unit_note"].format(n=notes), "tone": "notes"},
            {"label": t["m_flushed"], "value": t["m_unit_drop"].format(n=self.state["total_flushed"]), "tone": "assets"},
        ]
        if self.last_rss_bytes > 0:
            metrics.append({"label": t["m_rss"], "value": format_bytes_mb(self.last_rss_bytes), "tone": "config"})

        page_status = t["status_count"].format(n=total) if total > 0 else ""

        return {
            "title": t["title"],
            "status": page_status,
            "header_actions": [
                {"id": "drop_now", "label": t["act_drop_now"], "variant": "primary"},
                {"id": "export_guide", "label": t["act_export"], "variant": "secondary"},
                {"id": "open_flush", "label": t["act_flush_all"], "variant": "danger"},
            ],
            "cards": [
                {
                    "id": "how-card",
                    "title": t["card_how"],
                    "meta": t["card_how_meta"],
                    "items": [
                        {
                            "kind": "segmented",
                            "id": "style",
                            "label": t["lbl_style"],
                            "value": self.config["style"],
                            "options": [{"value": v, "label": t["styles"][v]} for v in STYLES],
                        },
                        {
                            "kind": "switch",
                            "id": "bg_enabled",
                            "label": t["lbl_bg_enabled"],
                            "value": self.config["bg_enabled"],
                        },
                        {
                            "kind": "group",
                            "visible_when": {"control_id": "bg_enabled", "equals": True},
                            "fields": [
                                {
                                    "kind": "select",
                                    "id": "bg_backdrop",
                                    "label": t["lbl_bg_backdrop"],
                                    "value": self.config["bg_backdrop"],
                                    "options": [
                                        {"value": "poop-wallpaper", "label": t["backdrops"]["poop-wallpaper"]},
                                        {"value": "poop-watermark", "label": t["backdrops"]["poop-watermark"]},
                                    ],
                                },
                                {
                                    "kind": "select",
                                    "id": "bg_pattern",
                                    "label": t["lbl_bg_pattern"],
                                    "value": self.config["bg_pattern"],
                                    "options": [{"value": v, "label": t["patterns"][v]} for v in PATTERNS],
                                },
                            ],
                        },
                        {
                            "kind": "group",
                            "visible_when": {"control_id": "bg_enabled", "equals": True},
                            "fields": [
                                {
                                    "kind": "segmented",
                                    "id": "bg_density",
                                    "label": t["lbl_bg_density"],
                                    "value": self.config["bg_density"],
                                    "options": [{"value": v, "label": t["densities"][v]} for v in DENSITIES],
                                },
                                {
                                    "kind": "select",
                                    "id": "bg_tint",
                                    "label": t["lbl_bg_tint"],
                                    "value": self.config["bg_tint"],
                                    "options": [{"value": v, "label": t["tints"][v]} for v in TINTS],
                                },
                            ],
                        },
                        {
                            "kind": "switch",
                            "id": "bg_dark_glow",
                            "label": t["lbl_dark_glow"],
                            "value": self.config["bg_dark_glow"],
                            "visible_when": {"control_id": "bg_enabled", "equals": True},
                        },
                        {
                            "kind": "group",
                            "fields": [
                                {
                                    "kind": "select",
                                    "id": "shape",
                                    "label": t["lbl_shape"],
                                    "value": self.config["shape"],
                                    "options": [{"value": v, "label": t["shapes"][v]} for v in SHAPES],
                                },
                                {
                                    "kind": "input",
                                    "id": "caption",
                                    "label": t["lbl_caption"],
                                    "value": self.config["caption"],
                                    "placeholder": t["ph_caption"],
                                },
                            ],
                        },
                        {
                            "kind": "secret",
                            "id": "flush_secret",
                            "label": t["lbl_secret"],
                            "value": self.config["flush_secret"],
                            "placeholder": t["ph_secret"],
                        },
                        {
                            "kind": "folder",
                            "id": "archive_dir",
                            "label": t["lbl_archive"],
                            "value": self.config["archive_dir"],
                        },
                        {
                            "kind": "actions",
                            "buttons": [
                                {"id": "save_prefs", "label": t["act_save"], "variant": "primary"},
                                {"id": "demo_toasts", "label": t["act_demo_toast"], "variant": "secondary"},
                                {"id": "rescan_notes", "label": t["act_rescan"], "variant": "secondary"},
                            ],
                        },
                    ],
                },
                {
                    "id": "notebooks-card",
                    "title": t["card_where"],
                    "items": [
                        {
                            "kind": "checklist",
                            "id": "selected_notebooks",
                            "value": self.config["selected_notebooks"],
                            "empty_text": t["lbl_notebooks_empty"],
                            "options": nb_options,
                        }
                    ],
                },
                {
                    "id": "stats-card",
                    "title": t["card_stats"],
                    "items": [
                        {"kind": "metrics", "metrics": metrics},
                        {
                            "kind": "treemap",
                            "id": "surface-breakdown",
                            "total_bytes": interaction_total * 1024,
                            "summary": {
                                "total_label": t["tm_total_label"],
                                "total_value": t["tm_total_val"].format(n=interaction_total),
                                "sub_text": t["tm_sub"],
                                "metrics": [{"label": t["tm_file_count"], "value": "4"}],
                            },
                            "tiles": [
                                {
                                    "id": "ai_sessions",
                                    "label": t["tm_body"],
                                    "detail": t["tm_body_detail"],
                                    "bytes": body_weight * 1024,
                                    "file_count": max(notes, 1),
                                    "color": "ai_sessions",
                                    "entries": [
                                        {"name": rel, "bytes": cnt * 1024, "count": cnt}
                                        for rel, cnt in sorted(self.note_counts().items())[:6]
                                    ],
                                },
                                {
                                    "id": "config",
                                    "label": t["tm_bg"],
                                    "detail": t["tm_bg_detail"],
                                    "bytes": bg_weight * 1024,
                                    "file_count": 2,
                                    "color": "config",
                                },
                                {
                                    "id": "assets",
                                    "label": t["tm_sidebar"],
                                    "detail": t["tm_sidebar_detail"],
                                    "bytes": sidebar_weight * 1024,
                                    "file_count": 3,
                                    "color": "assets",
                                },
                                {
                                    "id": "history",
                                    "label": t["tm_dialog"],
                                    "detail": t["tm_dialog_detail"],
                                    "bytes": dialog_weight * 1024,
                                    "file_count": 2,
                                    "color": "history",
                                },
                            ],
                        },
                        {
                            "kind": "kv",
                            "rows": [
                                {"label": t["kv_version"], "value": PLUGIN_VERSION, "tooltip": PLUGIN_ID},
                                {"label": t["kv_last"], "value": self.state["last_drop_at"] or t["kv_never"]},
                                {"label": t["kv_points"], "value": t["kv_points_val"], "tooltip": "contributes + host.*"},
                                {
                                    "label": t["kv_env"],
                                    "value": f"Block {self.host_version or '1.x'} ({self.locale} / {self.host_theme + '+tarot' if self.tarot_active else self.host_theme})",
                                },
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "preview_mode",
                            "label": t["lbl_preview_mode"],
                            "value": self.config["preview_mode"],
                            "options": [{"value": v, "label": t["preview_modes"][v]} for v in PREVIEW_MODES],
                        },
                        self.build_preview_item(),
                        {
                            "kind": "log_list",
                            "id": "activity-log",
                            "label": t["lbl_logs"],
                            "empty_text": t["lbl_logs_empty"],
                            "entries": log_entries,
                        },
                    ],
                },
                {
                    "id": "extension-map-card",
                    "title": t["card_map"],
                    "badge": t["card_map_badge"],
                    "collapsible": True,
                    "default_collapsed": True,
                    "items": [
                        {
                            "kind": "log_list",
                            "id": "extension-map",
                            "empty_text": t["lbl_map_empty"],
                            "entries": map_entries,
                        }
                    ],
                },
            ],
        }

    def render_appearance_section(self):
        t = self.t()
        return {
            "title": t["appearance_title"],
            "cards": [
                {
                    "id": "appearance-backdrop",
                    "title": t["appearance_title"],
                    "items": [
                        {
                            "kind": "switch",
                            "id": "bg_enabled",
                            "label": t["lbl_bg_enabled"],
                            "value": self.config["bg_enabled"],
                        },
                        {
                            "kind": "segmented",
                            "id": "bg_density",
                            "label": t["lbl_bg_density"],
                            "value": self.config["bg_density"],
                            "options": [{"value": v, "label": t["densities"][v]} for v in DENSITIES],
                            "visible_when": {"control_id": "bg_enabled", "equals": True},
                        },
                        {
                            "kind": "group",
                            "visible_when": {"control_id": "bg_enabled", "equals": True},
                            "fields": [
                                {
                                    "kind": "select",
                                    "id": "bg_pattern",
                                    "label": t["lbl_bg_pattern"],
                                    "value": self.config["bg_pattern"],
                                    "options": [{"value": v, "label": t["patterns"][v]} for v in PATTERNS],
                                },
                                {
                                    "kind": "select",
                                    "id": "bg_tint",
                                    "label": t["lbl_bg_tint"],
                                    "value": self.config["bg_tint"],
                                    "options": [{"value": v, "label": t["tints"][v]} for v in TINTS],
                                },
                            ],
                        },
                        {
                            "kind": "switch",
                            "id": "bg_dark_glow",
                            "label": t["lbl_dark_glow"],
                            "value": self.config["bg_dark_glow"],
                            "visible_when": {"control_id": "bg_enabled", "equals": True},
                        },
                        {
                            "kind": "actions",
                            "buttons": [
                                {"id": "reset_backdrop", "label": t["act_reset_bg"], "variant": "secondary"},
                            ],
                        },
                    ],
                }
            ],
        }

    def render_panel(self):
        t = self.t()
        total, notes = self.active_counts_summary()
        counts = self.note_counts()
        note_rows = []
        max_cnt = max(counts.values(), default=1)
        for rel, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]:
            row = {
                "title": os.path.basename(rel),
                "sub_text": os.path.dirname(rel),
                "status": t["m_unit_drop"].format(n=cnt),
                "tone": "ai_sessions" if cnt >= 5 else "notes",
                "ratio": min(1.0, max(0.08, cnt / max_cnt)),
                "tooltip": t["click_to_open"].format(note=rel),
            }
            if "log_actions" in self.capabilities and self.notebook_root:
                act_id = self.register_open_target(self.notebook_root, rel)
                if act_id:
                    row["action_id"] = act_id
            note_rows.append(row)

        return {
            "title": t["panel_title"],
            "cards": [
                {
                    "id": "panel-stats",
                    "title": t["card_panel_stats"],
                    "items": [
                        {
                            "kind": "metrics",
                            "metrics": [
                                {"label": t["m_active"], "value": t["m_unit_drop"].format(n=total), "tone": "ai_sessions"},
                                {"label": t["m_notes"], "value": t["m_unit_note"].format(n=notes), "tone": "notes"},
                            ],
                        },
                    ],
                },
                {
                    "id": "panel-drops",
                    "title": t["card_panel_recent"],
                    "items": [
                        {
                            "kind": "log_list",
                            "id": "panel-note-list",
                            "empty_text": t["lbl_logs_empty"],
                            "entries": note_rows,
                        },
                        {
                            "kind": "actions",
                            "buttons": [
                                {"id": "panel_drop", "label": t["act_drop_cursor"], "variant": "primary"},
                                {"id": "panel_flush_page", "label": t["act_flush_page"], "variant": "secondary"},
                                {"id": "panel_open_flush", "label": t["act_flush_all"], "variant": "danger"},
                            ],
                        },
                    ],
                },
            ],
        }

    def render_sidebar_section(self):
        t = self.t()
        entries = []
        for rel, cnt in sorted(self.note_counts().items(), key=lambda kv: (-kv[1], kv[0]))[:5]:
            item = {
                "title": os.path.splitext(os.path.basename(rel))[0],
                "time": t["m_unit_drop"].format(n=cnt),
                "tone": "warning" if cnt >= 5 else "accent",
                "tooltip": t["click_to_open"].format(note=rel),
            }
            if "log_actions" in self.capabilities and self.notebook_root:
                act_id = self.register_open_target(self.notebook_root, rel)
                if act_id:
                    item["action_id"] = act_id
            entries.append(item)
        return {
            "title": t["sidebar_title"],
            "cards": [
                {
                    "id": "sidebar-drops",
                    "title": t["sidebar_title"],
                    "items": [
                        {
                            "kind": "log_list",
                            "id": "sidebar-drop-list",
                            "empty_text": t["lbl_sidebar_empty"],
                            "entries": entries,
                        },
                        {
                            "kind": "actions",
                            "buttons": [
                                {"id": "sidebar_drop", "label": t["act_drop_now"], "variant": "primary"},
                            ],
                        },
                    ],
                }
            ],
        }

    def render_flush_dialog(self):
        t = self.t()
        total, notes = self.active_counts_summary()
        items = [
            {
                "kind": "metrics",
                "metrics": [
                    {"label": t["m_active"], "value": t["m_unit_drop"].format(n=total), "tone": "ai_sessions"},
                    {"label": t["m_notes"], "value": t["m_unit_note"].format(n=notes), "tone": "notes"},
                ],
            },
            {
                "kind": "preview",
                "preview": {
                    "variant": "diff",
                    "palette": "warm",
                    "title": t["pv_diff_title"],
                    "badge": t["pv_badge"],
                    "before": t["dialog_desc_before"].format(n=total, notes=notes),
                    "after": t["dialog_desc_after"],
                },
            },
        ]
        if self.config.get("flush_secret"):
            items.append({
                "kind": "secret",
                "id": "confirm_secret",
                "label": t["lbl_confirm_secret"],
                "value": "",
                "placeholder": t["ph_confirm_secret"],
            })
        items.append({
            "kind": "actions",
            "buttons": [
                {"id": "dialog_keep", "label": t["act_keep"], "variant": "secondary"},
                {"id": "dialog_flush_confirm", "label": t["act_confirm_flush"], "variant": "danger"},
            ],
        })
        return {
            "title": t["dialog_title"],
            "cards": [
                {
                    "id": "flush-confirm-card",
                    "title": t["card_dialog"],
                    "items": items,
                }
            ],
        }

    def open_flush_confirmation(self, bridge):
        t = self.t()
        self.pending_flush_token = ""
        self.pending_flush_nb = ""
        try:
            opened = bridge.call_host("host.ui.open_dialog", {"id": "flush-confirm"})
        except HostRPCError:
            return False, t["toast_dialog_unavailable"]
        if not isinstance(opened, dict) or opened.get("ok") is not True:
            return False, t["toast_dialog_unavailable"]
        host_token = opened.get("dialog_token")
        if "dialog_token" in self.capabilities:
            if not isinstance(host_token, str) or not host_token.strip():
                return False, t["toast_dialog_unavailable"]
            self.pending_flush_token = host_token.strip()
        else:
            self.pending_flush_token = (
                host_token.strip()
                if isinstance(host_token, str) and host_token.strip()
                else secrets.token_hex(8)
            )
        self.pending_flush_nb = self.notebook_root
        self.state["dialog_opens"] += 1
        self.save_state(bridge)
        return True, t["dialog_title"]

    def render_surface(self, bridge, surface):
        if surface == SURFACE_SETTINGS:
            return self.render_settings_page(bridge)
        if surface == SURFACE_APPEARANCE:
            return self.render_appearance_section()
        if surface == SURFACE_PANEL:
            return self.render_panel()
        if surface == SURFACE_SIDEBAR:
            return self.render_sidebar_section()
        if surface == SURFACE_DIALOG:
            return self.render_flush_dialog()
        raise ValueError(self.t()["err_unknown_surface"].format(surface=surface))

    def handle_open_target_action(self, bridge, action_id, surface):
        t = self.t()
        target = self.open_targets.get(action_id)
        if not target:
            return {"ok": False, "tone": "warning", "status": t["toast_open_missing"]}
        nb_root, rel_path = target
        self.state["sidebar_hits"] += 1
        self.save_state(bridge)
        try:
            res = bridge.call_host("host.notes.open", {"notebook_root": nb_root, "path": rel_path})
            if isinstance(res, dict) and res.get("ok"):
                msg = t["toast_opened_note"].format(note=rel_path)
                return {"ok": True, "tone": "info", "status": msg, "page": self.render_surface(bridge, surface)}
        except HostRPCError as exc:
            if exc.code in (-32601, -32005):
                return {"ok": True, "tone": "info", "status": t["toast_open_unavailable"]}
            return {"ok": False, "tone": "danger", "status": self.localize_error(exc.message)}
        return {"ok": True, "tone": "info", "status": t["toast_open_unavailable"]}

    def handle(self, bridge, method, params):
        if method == "plugin.initialize":
            self.locale = str(params.get("locale") or "zh")
            self.notebook_root = str(params.get("notebook_root") or "")
            self.downloads_dir = str(params.get("downloads_dir") or "")
            self.data_dir = str(params.get("data_dir") or "")
            self.host_version = str(params.get("host_version") or "")
            if isinstance(params.get("theme"), str) and params["theme"].strip():
                self.host_theme = params["theme"].strip()
            if "tarot" in params:
                self.tarot_active = bool(params.get("tarot"))
            caps = params.get("ui_capabilities")
            self.capabilities = set(caps) if isinstance(caps, list) else set()
            self.load_persisted(bridge)
            self.scan_notebook_markers(bridge)
            self.sync_host_ui(bridge)
            return {"ready": True}

        if method == "plugin.render":
            surface = str(params.get("surface") or SURFACE_SETTINGS)
            if isinstance(params.get("values"), dict):
                self.merge_form_values(bridge, params["values"], surface)
            page = self.render_surface(bridge, surface)
            return {"page": page, "values": page_values_for(surface, self.config)}

        if method == "plugin.action":
            surface = str(params.get("surface") or SURFACE_SETTINGS)
            action_id = str(params.get("action_id") or "")
            values = params.get("values") if isinstance(params.get("values"), dict) else {}
            raw_tok = params.get("dialog_token")
            dialog_token = raw_tok if isinstance(raw_tok, str) else ""
            if surface != SURFACE_DIALOG:
                self.merge_form_values(bridge, values, surface)
            return self.handle_action(bridge, surface, action_id, values, dialog_token)

        if method == "plugin.command":
            cmd_id = str(params.get("command_id") or "")
            ctx = params.get("context") if isinstance(params.get("context"), dict) else {}
            return self.handle_command(bridge, cmd_id, ctx)

        if method == "plugin.event":
            return self.handle_event(bridge, params)

        if method == "plugin.shutdown":
            return {"ok": True}

        raise ValueError(self.t()["err_unknown_method"].format(method=method))

    def handle_action(self, bridge, surface, action_id, values, dialog_token=""):
        t = self.t()
        if action_id.startswith("open_target:"):
            return self.handle_open_target_action(bridge, action_id, surface)

        if action_id in ("drop_now", "panel_drop", "sidebar_drop"):
            ok, tone, msg = self.drop_at_editor_or_note(bridge, source=surface)
            self.refresh_other_surfaces(bridge, surface)
            return {
                "ok": ok,
                "tone": tone,
                "status": msg,
                "page": self.render_surface(bridge, surface),
                "values": page_values_for(surface, self.config),
            }

        if action_id == "save_prefs":
            self.save_config(bridge)
            self.append_log("saved", tone="success")
            self.save_state(bridge)
            self.sync_host_ui(bridge)
            self.refresh_other_surfaces(bridge, surface)
            return {
                "ok": True,
                "tone": "success",
                "status": t["toast_saved"],
                "page": self.render_surface(bridge, surface),
                "values": page_values_for(surface, self.config),
            }

        if action_id == "demo_toasts":
            self.show_toast(bridge, t["toast_demo_info"], "info")
            self.show_toast(bridge, t["toast_demo_success"], "success")
            self.show_toast(bridge, t["toast_demo_warning"], "warning")
            self.show_toast(bridge, t["toast_demo_error"], "error")
            return {
                "ok": True,
                "tone": "info",
                "status": t["toast_demo_1"],
                "page": self.render_surface(bridge, surface),
            }

        if action_id == "rescan_notes":
            _, failed_paths, list_ok = self.scan_notebook_markers(bridge)
            if not list_ok:
                return {
                    "ok": False,
                    "tone": "error",
                    "status": t["toast_list_failed"],
                    "page": self.render_surface(bridge, surface),
                }
            self.save_state(bridge)
            self.sync_host_ui(bridge)
            self.refresh_other_surfaces(bridge, surface)
            total, notes = self.active_counts_summary()
            if failed_paths:
                return {
                    "ok": False,
                    "tone": "warning",
                    "status": t["toast_rescan_partial"].format(n=total, notes=notes, failed=len(failed_paths)),
                    "page": self.render_surface(bridge, surface),
                }
            return {
                "ok": True,
                "tone": "success",
                "status": t["toast_rescanned"].format(n=total, notes=notes),
                "page": self.render_surface(bridge, surface),
            }

        if action_id == "export_guide":
            out_path, dest_label, err_kind = self.export_developer_guide()
            if not out_path:
                msg = t["toast_archive_invalid"] if err_kind == "invalid" else t["toast_export_failed"]
                return {
                    "ok": False,
                    "tone": "error",
                    "status": msg,
                    "page": self.render_surface(bridge, surface),
                }
            return {
                "ok": True,
                "tone": "success",
                "status": t["toast_exported"].format(dest=dest_label),
                "reveal_path": out_path,
                "page": self.render_surface(bridge, surface),
            }

        if action_id in ("open_flush", "panel_open_flush"):
            ok, msg = self.open_flush_confirmation(bridge)
            return {
                "ok": ok,
                "tone": "info" if ok else "warning",
                "status": msg,
                "page": self.render_surface(bridge, surface),
            }

        if action_id == "panel_flush_page":
            ok, tone, msg = self.flush_single_note(bridge, "")
            self.refresh_other_surfaces(bridge, surface)
            return {"ok": ok, "tone": tone, "status": msg, "page": self.render_surface(bridge, surface)}

        if surface == SURFACE_APPEARANCE and action_id == "reset_backdrop":
            for key in ("bg_enabled", "bg_backdrop", "bg_pattern", "bg_density", "bg_tint", "bg_dark_glow"):
                self.config[key] = DEFAULT_CONFIG[key]
            self.save_config(bridge)
            self.sync_host_ui(bridge)
            self.refresh_other_surfaces(bridge, surface)
            return {
                "ok": True,
                "tone": "info",
                "status": t["toast_bg_reset"],
                "page": self.render_surface(bridge, surface),
                "values": page_values_for(surface, self.config),
            }

        if action_id == "dialog_keep":
            if surface != SURFACE_DIALOG or not self.pending_flush_token or self.pending_flush_nb != self.notebook_root:
                return {"ok": False, "tone": "warning", "status": t["toast_stale_confirm"], "page": self.render_surface(bridge, surface)}
            if "dialog_token" in self.capabilities and dialog_token != self.pending_flush_token:
                return {"ok": False, "tone": "warning", "status": t["toast_stale_confirm"], "page": self.render_flush_dialog()}
            self.pending_flush_token = ""
            self.pending_flush_nb = ""
            self.best_effort_call(bridge, "host.ui.close_dialog", {"id": "flush-confirm"})
            return {"ok": True, "tone": "info", "status": t["toast_kept"], "page": self.render_flush_dialog()}

        if action_id == "dialog_flush_confirm":
            if surface != SURFACE_DIALOG or not self.pending_flush_token or self.pending_flush_nb != self.notebook_root:
                return {"ok": False, "tone": "warning", "status": t["toast_stale_confirm"], "page": self.render_surface(bridge, surface)}
            if "dialog_token" in self.capabilities and dialog_token != self.pending_flush_token:
                return {"ok": False, "tone": "warning", "status": t["toast_stale_confirm"], "page": self.render_flush_dialog()}
            secret = self.config.get("flush_secret") or ""
            if secret and str(values.get("confirm_secret") or "") != secret:
                return {"ok": False, "tone": "danger", "status": t["toast_wrong_secret"], "page": self.render_flush_dialog()}
            self.pending_flush_token = ""
            self.pending_flush_nb = ""
            ok, tone, msg = self.flush_all_notes(bridge)
            self.best_effort_call(bridge, "host.ui.close_dialog", {"id": "flush-confirm"})
            page = self.render_flush_dialog()
            self.show_toast(bridge, msg, tone)
            self.refresh_other_surfaces(bridge, surface)
            return {"ok": ok, "tone": tone, "status": msg, "page": page}

        raise ValueError(t["err_unknown_action"].format(action=action_id))

    def handle_command(self, bridge, cmd_id, ctx):
        t = self.t()
        note = ctx.get("note") if isinstance(ctx.get("note"), str) else ""
        selection = ctx.get("selection") if isinstance(ctx.get("selection"), str) else ""
        source = str(ctx.get("source") or "")

        if cmd_id == "drop_here":
            ok, tone, msg = self.drop_at_editor_or_note(bridge, note, selection, wrap_selection=False, source=source)
            self.refresh_other_surfaces(bridge)
            return {"ok": ok, "tone": tone, "status": msg, "show_plugin_icon": True}

        if cmd_id == "poopify_selection":
            ok, tone, msg = self.drop_at_editor_or_note(bridge, note, selection, wrap_selection=True, source=source)
            self.refresh_other_surfaces(bridge)
            return {"ok": ok, "tone": tone, "status": msg, "show_plugin_icon": True}

        if cmd_id == "toggle_panel":
            method_name = "host.ui.toggle_panel" if "panel_toggle" in self.capabilities else "host.ui.open_panel"
            try:
                res = bridge.call_host(method_name, {"id": "poop-board"})
            except HostRPCError:
                return {"ok": False, "tone": "warning", "status": t["toast_panel_unavailable"], "show_plugin_icon": True}
            if not isinstance(res, dict) or res.get("ok") is not True:
                return {"ok": False, "tone": "warning", "status": t["toast_panel_unavailable"], "show_plugin_icon": True}
            self.sync_host_ui(bridge)
            return {"ok": True}

        if cmd_id == "drop_in_note":
            strict = source == "sidebar_menu"
            target = self.resolve_target_note(bridge, note, strict=strict)
            if not target:
                return {"ok": False, "tone": "warning", "status": t["toast_no_note"], "show_plugin_icon": True}
            if not self.is_active_notebook_allowed(bridge):
                self.append_log("blocked", note=target, tone="danger")
                self.save_state(bridge)
                return {"ok": False, "tone": "error", "status": t["toast_blocked_nb"], "show_plugin_icon": True}
            if strict:
                self.state["sidebar_hits"] += 1
            ok, tone, msg = self.drop_into_note_file(bridge, target)
            self.refresh_other_surfaces(bridge)
            return {"ok": ok, "tone": tone, "status": msg, "show_plugin_icon": True}

        if cmd_id == "flush_note":
            strict = source == "sidebar_menu"
            ok, tone, msg = self.flush_single_note(bridge, note, strict=strict)
            self.refresh_other_surfaces(bridge)
            return {"ok": ok, "tone": tone, "status": msg, "show_plugin_icon": True}

        if cmd_id == "open_flush_dialog":
            ok, msg = self.open_flush_confirmation(bridge)
            if not ok:
                return {"ok": False, "tone": "warning", "status": msg, "show_plugin_icon": True}
            return {"ok": True}

        raise ValueError(t["err_unknown_command"].format(cmd=cmd_id))

    def handle_event(self, bridge, params):
        ev = str(params.get("event") or "")
        if ev == "note.saved":
            rel = params.get("path") if isinstance(params.get("path"), str) else ""
            nb_root = str(params.get("notebook_root") or "")
            if rel and (not nb_root or not self.notebook_root or os.path.normpath(nb_root) == os.path.normpath(self.notebook_root)):
                try:
                    note = bridge.call_host("host.notes.read", {"path": rel})
                    cnt = self.count_markers(note.get("content", ""))
                    counts = self.note_counts()
                    if cnt > 0:
                        counts[rel] = cnt
                    else:
                        counts.pop(rel, None)
                    self.append_log("note_saved", note=rel, count=cnt, tone="info")
                    self.save_state(bridge)
                    self.sync_host_ui(bridge)
                    self.refresh_other_surfaces(bridge)
                except HostRPCError:
                    pass
            return {"handled": True}

        if ev == "theme.changed":
            if isinstance(params.get("theme"), str) and params["theme"].strip():
                self.host_theme = params["theme"].strip()
            if "tarot" in params:
                self.tarot_active = bool(params.get("tarot"))
            self.append_log("theme", tone="info")
            self.save_state(bridge)
            self.sync_host_ui(bridge)
            self.refresh_other_surfaces(bridge)
            return {"handled": True}

        if ev == "locale.changed":
            new_loc = str(params.get("locale") or "")
            if new_loc:
                self.locale = new_loc
                self.sync_host_ui(bridge)
                self.refresh_other_surfaces(bridge)
            return {"handled": True}

        if ev == "note.opened":
            self.sync_host_ui(bridge)
            return {"handled": True}

        return {"handled": False}


def page_values_for(surface, cfg):
    if surface == SURFACE_SETTINGS:
        return {
            "style": cfg["style"],
            "shape": cfg["shape"],
            "bg_enabled": cfg["bg_enabled"],
            "bg_backdrop": cfg["bg_backdrop"],
            "bg_pattern": cfg["bg_pattern"],
            "bg_density": cfg["bg_density"],
            "bg_tint": cfg["bg_tint"],
            "bg_dark_glow": cfg["bg_dark_glow"],
            "caption": cfg["caption"],
            "flush_secret": cfg["flush_secret"],
            "archive_dir": cfg["archive_dir"],
            "preview_mode": cfg["preview_mode"],
            "selected_notebooks": cfg["selected_notebooks"],
        }
    if surface == SURFACE_APPEARANCE:
        return {
            "bg_enabled": cfg["bg_enabled"],
            "bg_pattern": cfg["bg_pattern"],
            "bg_density": cfg["bg_density"],
            "bg_tint": cfg["bg_tint"],
            "bg_dark_glow": cfg["bg_dark_glow"],
        }
    return {}


def main():
    plugin = PoopEverywherePlugin()
    bridge = HostBridge()
    bridge.serve(plugin.handle, plugin.localize_error)


if __name__ == "__main__":
    main()
