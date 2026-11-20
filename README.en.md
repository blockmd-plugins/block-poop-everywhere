<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/card-en-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/card-en-light.png">
  <img alt="Poop Everywhere" src="assets/card-en-light.png">
</picture>

**Official Interactive Kitchen-Sink Reference Plugin** -- a playful, complete plugin built to show Block plugin authors all 17 interactive UI surfaces and common host APIs in one working codebase (declarative language grammars, Tarot mode, and legacy grid backgrounds have dedicated reference plugins).

- **All 17 Interactive Extension Points Wired**: Titlebar buttons with live badges, command palette & shortcuts, page menu, editor context menu (with native dual-tone icons), sidebar tree context menu, collapsible left-sidebar section, file-tree row badges, custom vector editor backdrops (with dark-mode glow), right side panel, bottom status bar with icon, modal dialog, icon-bearing toasts across all 4 tones, and an Appearance settings section.
- **All 14 Declarative UI Controls**: The plugin settings page showcases `segmented`, `switch`, `select`, `input`, `secret`, `folder`, `checklist`, `actions`, `metrics`, `treemap`, `kv`, `preview` (all 4 variants: `article`, `diff`, `cards`, `plan`), `log_list`, and `group` with instant `visible_when` rules and collapsible cards.
- **Zero Emoji, Zero Dependencies, Safely Reversible**: Written in pure Python standard library using Ocean Paper dual-tone SVG paths. Every note marker carries an owned HTML signature tag and skips fenced/indented code, raw HTML blocks, and list containers. Wrapped selections unwrap byte-for-byte intact alongside optimistic concurrency (`expected_revision`) so flushing removes only plugin-authored lines without touching user prose or code examples.

Adjust the editor backdrop in Settings > Appearance > Poop Everywhere Backdrop or on the plugin’s settings page. Saved preferences load at startup, and changes apply immediately.

## Extension Point Map

| Surface | Manifest / RPC Entry | Permission |
| --- | --- | --- |
| Titlebar buttons & live badges | `contributes.titlebar_buttons` + `host.titlebar.set_button` | `ui:titlebar` |
| Command palette & shortcuts | `contributes.commands` (`Cmd+Alt+P` / `K`) | `ui:commands` |
| Page action menu | `contributes.page_menu` | `ui:commands` |
| Editor context menu | `contributes.editor_menu` (native dual-tone icons) | `ui:commands` |
| Sidebar tree context menu | `contributes.sidebar_menu` | `ui:sidebar` |
| Left sidebar section | `contributes.sidebar_sections` (`sidebar_section:*`) | `ui:sidebar` |
| File-tree row badges | `contributes.file_badges` + `host.sidebar.set_badges` | `ui:sidebar` |
| Custom vector editor backdrops | `contributes.backdrops` + `host.ui.set_backdrop` | `ui:appearance` |
| Right side panel | `contributes.panels` (`panel:*`) | `ui:panels` |
| Bottom status bar (with icon) | `contributes.status_items` + `host.status.set` | `ui:status` |
| Modal dialog & icon toasts | `contributes.dialogs` + `host.ui.toast` | `ui:notify` |
| Built-in settings section | `contributes.settings_sections` (`appearance`) | `ui:settings` |
| Plugin settings page (14 controls) | `surfaces: ["settings_page"]` | Built-in |
| Caret insert & selection wrap | `host.editor.selection` / `host.editor.insert` | `editor:read` / `editor:write` |
| Note I/O & click-to-open jump | `host.notes.read` / `write` / `open` | `notes:read` / `notes:write` |
| Save & workspace hooks | `plugin.event` (`note.saved` / `theme.changed` / `locale.changed`) | `events:note_saved` / `events:workspace` |

**Install**: Open Block Settings -> App Store and search **Poop Everywhere**, or enter `blockmd-plugins/block-poop-everywhere`.
