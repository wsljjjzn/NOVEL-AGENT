# Novel Studio UI 设计系统规范 (Linear Design System)

> 本文档规范 Novel Studio Web 端（`web_prototype/index.html`）的界面设计系统，基于 **Linear 现代极简工匠风格 (Linear Style)** 构建，提供全方位的深空曜黑与晶亮纯白双模自适应与多端响应式支持。

---

## 一、设计语言与调性

- **设计定位**：高工匠感数字写作套件（High-Craft Writing Suite）。以现代软件工程最高设计标杆 Linear 为底座，追求极致的克制、高密度、秩序感与安静的奢华。
- **色彩美学**：
  - **曜石暗色模式 (Dark)**：深空曜黑底色（`#08090a`），深炭微浮层面板（`#121315`），细腻发丝级微边框（`#23252a`），极度深邃、克制且专注。
  - **晶亮亮色模式 (Light)**：晶亮清爽纯白底色（`#fafbfc`），纯白卡片（`#ffffff`），冷灰发丝边框（`#e2e4e8`），纯净通透，无任何视觉杂质。
  - **品牌高亮 (Brand Accent)**：**Linear Lavender-Blue**（`#5e6ad2`，Hover `#828fff` / `#4e5ac0`），作为全系统唯一的色彩焦点，应用于主操作 CTA、品牌徽标、焦点光环与激活指示。

---

## 二、色彩令牌定义 (Color Tokens)

```css
:root {
  /* Linear Light Theme: 晶亮清爽纯白底色，冷灰发丝边框，标志性薰衣草紫罗兰点缀 */
  --canvas: #fafbfc;
  --canvas-soft: #f4f5f8;
  --surface-card: #ffffff;
  --surface-soft: #f0f1f4;
  --surface-elevated: #ffffff;
  --surface-strong: #e4e6eb;

  --ink: #0e1017;
  --ink-secondary: #4b5162;
  --ink-muted: #6c727e;
  --ink-faint: #8e95a5;

  --hairline: #e2e4e8;
  --hairline-soft: #edf0f4;
  --hairline-strong: #d0d4dc;

  /* Signature Linear Lavender-Blue */
  --primary: #5e6ad2;
  --primary-hover: #4e5ac0;
  --primary-subtle: rgba(94, 106, 210, 0.08);
  --primary-border: rgba(94, 106, 210, 0.3);
  --on-primary: #ffffff;

  --badge-bg: #f0f1f4;
  --badge-text: #4b5162;
  --status-success: #27a644;
  --status-warning: #d97706;
  --status-error: #e11d48;
}

html.dark {
  /* Linear Dark Theme: 深空曜黑底色 (#08090a)，深炭微浮层 (#121315)，发丝边框 (#23252a)，薰衣草紫罗兰 (#5e6ad2) */
  --canvas: #08090a;
  --canvas-soft: #0e1012;
  --surface-card: #121315;
  --surface-soft: #17181c;
  --surface-elevated: #1c1d22;
  --surface-strong: #24262c;

  --ink: #f7f8f8;
  --ink-secondary: #d0d6e0;
  --ink-muted: #8a8f98;
  --ink-faint: #62666d;

  --hairline: #23252a;
  --hairline-soft: #1c1d22;
  --hairline-strong: #34343a;

  /* Signature Linear Lavender-Blue */
  --primary: #5e6ad2;
  --primary-hover: #828fff;
  --primary-subtle: rgba(94, 106, 210, 0.16);
  --primary-border: rgba(94, 106, 210, 0.38);
  --on-primary: #ffffff;

  --badge-bg: #17181c;
  --badge-text: #d0d6e0;
  --status-success: #27a644;
  --status-warning: #f59e0b;
  --status-error: #f43f5e;
}
```

---

## 三、排版与字体系统 (Typography)

| 类别 | 推荐字体栈 | 用途 |
|---|---|---|
| **界面 UI** | `Inter, -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif` | 顶栏、菜单、按钮、表单、提示文案（负字距 `-0.01em`） |
| **代码与指标** | `"SF Mono", "JetBrains Mono", ui-monospace, Menlo, Monaco, Consolas, monospace` | 双螺旋自检、字数统计、切片指针、JSON 数据 |
| **小说正文 (默认)** | `Songti SC, STSong, SimSun, serif` | 编辑器核心正文排版（典雅衬线） |
| **小说正文 (可配置)** | 楷体 (`STKaiti, KaiTi`)、非衬线 (`PingFang SC`)、等宽码字流 | 设置模态框中自由调配 |

---

## 四、响应式多端断点 (Responsive Breakpoints)

- **桌面端 (>= 1024px)**：完整三栏可调节工作区（章节大纲树 + 居中沉浸编辑器 + 角色/剧情/审稿副驾），支持鼠标拖动分割条实时微调栏宽。
- **平板端 (768px ~ 1023px)**：顶栏保留核心操作，左右侧栏折叠为平滑滑入式抽屉（点击顶栏 📖 / 👥 唤出），保障编辑器享有充足横向书写面积。
- **移动端 (< 768px)**：
  - 顶栏控件自适应压缩。
  - 企划台由 3 列网格平滑降级为单列纵向流。
  - 剧情棋盘伏笔网格由 2/3 列降级为 1 列卡片流。
  - 划词菜单自适应视口避免溢出。
