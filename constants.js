export const PLUGIN_ID = 'block-poop-everywhere';
export const PLUGIN_VERSION = '1.0.11';

export const SURFACE_SETTINGS = 'settings_page';
export const SURFACE_PANEL = 'panel:poop-board';
export const SURFACE_SIDEBAR = 'sidebar_section:today-drops';
export const SURFACE_DIALOG = 'dialog:flush-confirm';

export const ALL_SURFACES = [
  SURFACE_SETTINGS,
  SURFACE_PANEL,
  SURFACE_SIDEBAR,
  SURFACE_DIALOG,
];

export const STORAGE_CONFIG = 'config';
export const STORAGE_STATE = 'runtime_state';

export const DROP_SIGNATURE = '<!-- block-poop-everywhere:drop -->';

export const MARKDOWN_EXTENSIONS = new Set([
  '.md',
  '.markdown',
  '.mdown',
  '.mkd',
  '.mkdn',
  '.mdwn',
  '.mdtxt',
  '.mdtext',
  '.mdx',
]);

export const MAX_SIDEBAR_BADGES = 512;

export const EMOJI_RE = /[\u200d\u20e3\ufe00-\ufe0f\u2600-\u27bf\u{1f000}-\u{1faff}]/gu;

export const CHINESE_RE = /[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\ufe10-\ufe1f\ufe30-\ufe4f\uff00-\uffef]/;

export const STYLES = ['shy', 'normal', 'wild'];
export const SHAPES = ['classic', 'ribbon', 'pellet'];
export const PATTERNS = ['scatter', 'grid', 'watermark', 'corners'];
export const DENSITIES = ['sparse', 'medium', 'dense'];
export const TINTS = ['accent', 'warm', 'muted', 'glow'];
export const PREVIEW_MODES = ['article', 'diff', 'cards', 'plan'];

export const DENSITY_OPACITY = {
  sparse: 0.06,
  medium: 0.1,
  dense: 0.18,
};

export const DEFAULT_CONFIG = {
  style: 'normal',
  shape: 'classic',
  bg_enabled: true,
  bg_backdrop: 'poop-wallpaper',
  bg_pattern: 'scatter',
  bg_density: 'medium',
  bg_tint: 'accent',
  bg_dark_glow: false,
  caption: '',
  flush_secret: '',
  archive_dir: '',
  preview_mode: 'article',
  selected_notebooks: [],
  notebooks_configured: false,
};

export const DEFAULT_STATE = {
  total_dropped: 0,
  total_flushed: 0,
  bg_toggles: 0,
  sidebar_hits: 0,
  dialog_opens: 0,
  last_drop_at: '',
  note_counts_by_nb: {},
  logs: [],
};

export const EXTENSION_MAP = [
  ['contributes.titlebar_buttons', 'built-in'],
  ['contributes.commands', 'built-in'],
  ['contributes.page_menu', 'built-in'],
  ['contributes.editor_menu', 'built-in'],
  ['contributes.sidebar_menu', 'built-in'],
  ['contributes.sidebar_sections', 'built-in'],
  ['contributes.file_badges', 'built-in'],
  ['contributes.backdrops', 'built-in'],
  ['contributes.panels', 'built-in'],
  ['contributes.status_items', 'built-in'],
  ['contributes.dialogs', 'built-in'],
  ['host.ui.toast (top-right banner)', 'built-in'],
  ['surfaces: [settings_page]', 'built-in'],
  ['host.editor.selection / insert', 'editor:read / write'],
  ['host.notes.open / read / write', 'notes:read / write'],
  ['plugin.event (note.saved / workspace)', 'events:*'],
];
