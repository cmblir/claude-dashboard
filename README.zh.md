<div align="center">

# 💤 LazyClaude

<img src="./docs/logo/mascot.svg" alt="LazyClaude 吉祥物 — 闭眼小憩的像素角色" width="200" height="171" />

**所有 Claude 工作，懒洋洋又优雅。**

_别再死记 50+ 个 CLI 命令。点一下就好。_

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md)
[![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v3.66.0-green.svg)](./CHANGELOG.md)

</div>

LazyClaude 是一个**本地优先的指挥中心**，管理你的 `~/.claude/` 目录（agents、skills、hooks、plugins、MCP、sessions、projects），附带 n8n 风格的工作流引擎和独立 CLI（`lazyclaw`）。所有功能通过一行 `python3 server.py` 启动 — Python 标准库、单文件 HTML、无安装步骤。

**无云端上传。无遥测。无依赖。**

---

## 🚀 快速开始

```bash
git clone https://github.com/cmblir/LazyClaude.git
cd LazyClaude
python3 server.py
# → http://127.0.0.1:8080
```

需要 Python 3.10+ 与 Anthropic 的 `claude` CLI（可选 — 仅 Claude 相关功能需要）。

```bash
# 可选环境变量
PORT=19500 python3 server.py
LOG_LEVEL=DEBUG python3 server.py
CLAUDE_HOME=/path/to/.claude python3 server.py
```

---

## 🐚 LazyClaw CLI

独立的 Node CLI（与仪表板分离），通过快速终端界面提供相同的 providers / sessions / skills / workflows / 计费表面。

```bash
node src/lazyclaw/cli.mjs onboard          # 一次性配置
node src/lazyclaw/cli.mjs chat             # 交互 REPL
node src/lazyclaw/cli.mjs agent "summarize: $(cat file.md)"   # 一次性
node src/lazyclaw/cli.mjs run my-job ./flow.mjs --parallel-persistent
node src/lazyclaw/cli.mjs inspect my-job --critical-path ./flow.mjs
node src/lazyclaw/cli.mjs daemon --port 0  # 本地 HTTP 网关
```

`lazyclaw help` 列出所有子命令。CLI 与 daemon 共享校验器（`config-validate.mjs`、`rates-validate.mjs`）和分析器（`workflow/summary.mjs`）— 两个表面输出完全一致。

---

## 🔄 Auto-Resume + 实时 TTY 注入 (v3.65.0+)

当 Claude session 遇到限流或选择 prompt 时，Auto-Resume 现在可以将按键直接注入**实时终端** — 而不只是 spawn 一个独立的 subprocess。仅 macOS：

- **策略 A**：TTY 定向 AppleScript（iTerm、Terminal.app）— 不切换焦点
- **策略 B**：System Events 按键 fallback（Warp、kitty、WezTerm、Alacritty、Ghostty、Hyper、Tabby、VS Code、Cursor）— 剪贴板粘贴，可靠处理任意 Unicode

`pressChoice: "1"`（默认）在注入 prompt 之前先关闭 `1) Continue / 2) Quit` 选择 prompt。System Events fallback 需要 python3 的辅助功能权限（系统设置 → 隐私与安全 → 辅助功能中授权一次）。

```
POST /api/auto_resume/inject_live
{ "sessionId": "...", "prompt": "继续。", "pressChoice": "1" }
```

时间型截止（`durationSec` / `deadlineMs`）取代了旧的 `maxAttempts` 上限 — 选择"何时停"，而非"试几次"。

---

## 📐 架构

```
LazyClaude/
├── server.py                  # 入口 — 绑定 127.0.0.1:8080
├── server/                    # ~25 个 Python stdlib 模块
│   ├── routes.py              # 单一 dispatch table
│   ├── workflows.py           # DAG 引擎 (ThreadPoolExecutor)
│   ├── ai_providers.py        # provider 注册表
│   ├── auto_resume.py         # 限流重试 + deadlineMs
│   ├── auto_resume_inject.py  # macOS 实时 TTY 注入 (v3.65)
│   └── ...
├── src/lazyclaw/              # Node CLI + daemon（独立于仪表板）
│   ├── cli.mjs                # 入口
│   ├── daemon.mjs             # HTTP 网关
│   ├── workflow/              # sequential / parallel / persistent 引擎
│   ├── providers/             # anthropic / openai / ollama / gemini / mock
│   ├── config-validate.mjs    # 与 daemon 共享
│   └── rates-validate.mjs     # 与 daemon 共享
├── dist/                      # 单文件 SPA (HTML + app.js + locales)
└── tests/                     # 491 pytest + 393 Playwright
```

### 数据存储

| 路径 | 用途 | 环境变量 |
|---|---|---|
| `~/.claude-dashboard.db` | SQLite — session 索引、成本、遥测 | `CLAUDE_DASHBOARD_DB` |
| `~/.claude-dashboard-workflows.json` | 工作流 + 运行记录 + 自定义模板 | `CLAUDE_DASHBOARD_WORKFLOWS` |
| `~/.claude-dashboard-ai-providers.json` | API 密钥、自定义 CLI、fallback 链 | `CLAUDE_DASHBOARD_AI_PROVIDERS` |
| `~/.claude-dashboard-auto-resume.json` | Auto-Resume 绑定 | `CLAUDE_DASHBOARD_AUTO_RESUME` |
| `~/.claude/` | Claude Code 自身状态 — 只读 | `CLAUDE_HOME` |

所有写入都通过原子 `tmp + rename`（`server/utils.py::_safe_write`）。

---

## 🌍 国际化

韩语为源语言。所有用户可见字符串都通过 `t('한국어 원문')` 包裹，并通过 `dist/locales/{ko,en,zh}.json` 解析。新增字符串后运行 `make i18n-refresh`。

---

## 🛠️ 故障排查

**"port 8080 already in use"** — `server.py` 在绑定前会自动 kill 之前的占用进程。如需其他端口：`PORT=19500 python3 server.py`。

**"command not found: claude"** — 安装 [Claude Code](https://claude.com/claude-code)。不依赖 `claude` 的标签（工作流编辑器、AI Providers、MCP 等）仍然可用。

**Auto-Resume 实时注入无响应** — macOS 系统设置 → 隐私与安全 → 辅助功能中为 `python3` 授权。权限缺失时会显示错误码 `1002 / -1719` 与提示。

**Toast 📋 按钮触发损坏的 HTML 输出** — v3.66.0 已修复。

---

## 🤝 贡献

```bash
make i18n-refresh          # 修改 t('...') 字符串后必须运行
python3 -m pytest tests/   # Python 测试套件
npx playwright test        # CLI/daemon 测试套件
node scripts/e2e-dashboard-qa.mjs   # 完整仪表板 probe
```

分支：`feat/*`、`fix/*`、`chore/*`。仅使用注释标签（`git tag -a vX.Y.Z -m "..."`）。fork 不得直接 push 到 `main`。

完整 release 日志见 [CHANGELOG.md](./CHANGELOG.md)。

---

## Star History

<a href="https://www.star-history.com/?repos=cmblir/lazyclaude&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=cmblir/lazyclaude&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=cmblir/lazyclaude&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=cmblir/lazyclaude&type=date&legend=top-left" />
 </picture>
</a>

---

## 📝 许可

[MIT](./LICENSE) — 个人和商业用途免费。

---

## 🙏 致谢

- [Anthropic Claude Code](https://claude.com/claude-code) — 本仪表板基于的 CLI
- [n8n](https://n8n.io) — 工作流编辑器的灵感
- [lazygit](https://github.com/jesseduffield/lazygit) / [lazydocker](https://github.com/jesseduffield/lazydocker) — 项目命名的灵感

<div align="center"><sub>用 💤 为更喜欢点击而不是打字的人打造。</sub></div>
