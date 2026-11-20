<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/card-zh-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/card-zh-light.png">
  <img alt="到处拉屎" src="assets/card-zh-light.png">
</picture>

**官方全交互扩展点示范插件** —— 用一个带点幽默感的完整可玩插件，向 Block 插件开发者直观展示全部交互式界面挂载点与常用宿主能力（纯声明式语言扩展、塔罗模式与旧版点阵背景另有独立官方/第一方范例）。

- **全界面 17 处扩展点一次看全**：覆盖顶栏按钮与角标、命令面板与快捷键、页面「…」菜单、编辑器右键菜单、侧栏右键菜单、左侧栏可折叠分区、文件树行尾角标、编辑区自定义矢量背景（支持暗色夜光）、右侧边栏面板、带图标的底部状态栏、模态确认弹窗、带图标的四语气 Toast，以及内置「外观」设置页追加分区。
- **日常设置只留 3 项**：一次拉几坨、编辑区背景开关、每坨附言。形状、背景款式、浓度、色调、笔记本范围都使用默认值；其余控件仍由侧栏、面板、确认弹窗和外观分区实际跑通。
- **零 Emoji、零外部依赖、安全可逆**：仅用 Python 标准库与 Ocean Paper 双色矢量 SVG 图标，所有写入正文的内容均带插件专属标记签名（跳过代码围栏、缩进代码块、HTML 块与列表容器），选区包裹支持原样无损还原，配合乐观并发哈希 `expected_revision` 精确一键冲掉，绝不误伤用户正文或代码示例。

在「设置 → 外观 → 到处拉屎 · 编辑区背景」开关背景。插件设置页只调整一次拉几坨和附言。启动时自动加载已保存的样式，修改即时生效。

## 扩展点对照表

| 界面位置 | 清单 / RPC 入口 | 所需权限 |
| --- | --- | --- |
| 顶栏按钮与动态角标 | `contributes.titlebar_buttons` + `host.titlebar.set_button` | `ui:titlebar` |
| 命令面板与快捷键 | `contributes.commands`（`⌘⌥P` / `⌘⌥K`） | `ui:commands` |
| 页面「…」菜单 | `contributes.page_menu` | `ui:commands` |
| 编辑器右键菜单 | `contributes.editor_menu`（原生双色图标） | `ui:commands` |
| 左侧栏右键菜单 | `contributes.sidebar_menu` | `ui:sidebar` |
| 左侧栏底部插件分区 | `contributes.sidebar_sections`（`sidebar_section:*`） | `ui:sidebar` |
| 文件树行尾角标 | `contributes.file_badges` + `host.sidebar.set_badges` | `ui:sidebar` |
| 编辑区自定义矢量背景 | `contributes.backdrops` + `host.ui.set_backdrop` | `ui:appearance` |
| 右侧边栏面板 | `contributes.panels`（`panel:*`） | `ui:panels` |
| 底部状态栏（带图标） | `contributes.status_items` + `host.status.set` | `ui:status` |
| 模态弹窗与带图标 Toast | `contributes.dialogs` + `host.ui.toast` | `ui:notify` |
| 内置设置页追加分区 | `contributes.settings_sections`（`appearance`） | `ui:settings` |
| 插件设置页（3 项） | `surfaces: ["settings_page"]` | 无需额外权限 |
| 正文光标插入 / 选区替换 | `host.editor.selection` / `host.editor.insert` | `editor:read` / `editor:write` |
| 笔记读写与列表点击跳转 | `host.notes.read` / `write` / `open` | `notes:read` / `notes:write` |
| 保存钩子与工作区事件 | `plugin.event`（`note.saved` / `theme.changed` / `locale.changed`） | `events:note_saved` / `events:workspace` |

**安装**：打开 Block「设置 → 应用商店」搜索 **到处拉屎**，或手动填入 `blockmd-plugins/block-poop-everywhere`。
