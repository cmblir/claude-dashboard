<div align="center">

# 💤 LazyClaude

<img src="./docs/logo/mascot.svg" alt="LazyClaude 吉祥物 — 闭眼小憩的像素角色" width="200" height="171" />

**所有 Claude 工作，懒洋洋又优雅。**

_别再死记 50+ 个 CLI 命令。点一下就好。_

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md)
[![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v3.91.0-green.svg)](./CHANGELOG.md)
[![npm](https://img.shields.io/npm/v/lazyclaw.svg?label=lazyclaw%20cli)](https://www.npmjs.com/package/lazyclaw)

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

### 安装

```bash
npm install -g lazyclaw
lazyclaw version
```

要求：**Node 18+**。在 macOS / Linux / WSL 上工作。Windows 原生 PowerShell 大致可用，但 ghost-text 与 ANSI 横幅仅在 TTY 启用，否则回退到普通 prompt。

<details>
<summary>从源码安装（贡献者）</summary>

```bash
git clone https://github.com/cmblir/LazyClaude.git
cd LazyClaude

# 直接运行（无安装）
node src/lazyclaw/cli.mjs <subcommand>

# 或将 bin 链接到 $PATH
sudo ln -s "$PWD/src/lazyclaw/cli.mjs" /usr/local/bin/lazyclaw
sudo chmod +x /usr/local/bin/lazyclaw

# 或在 shell profile（~/.zshrc / ~/.bashrc）中设置 alias
alias lazyclaw="node $HOME/path/to/LazyClaude/src/lazyclaw/cli.mjs"
```

发布到 npm 的 `lazyclaw` 是 [`src/lazyclaw/`](./src/lazyclaw) 的快照。`main` 上每次 push 如果 bump 了 `src/lazyclaw/package.json#version`，`.github/workflows/publish-lazyclaw.yml` 会自动发布到 npmjs.org。

</details>

### 首次运行 — 交互式 onboarding

```bash
lazyclaw onboard               # 方向键 picker — 默认 claude-cli（无需 API key）
lazyclaw status                # 当前 provider/model + 掩码后的 key
lazyclaw doctor                # 校验配置与 provider 注册表
```

picker 的每一行都标注认证方式：

| 标签 | 含义 |
|---|---|
| `[subscription]` | 使用本地 `claude` CLI 的现有登录（Pro / Max / Team）。无需 API key。 |
| `[no key]` | 仅本地 provider（`ollama`, `mock`）。 |
| `[api key]` | 直连 provider API（`anthropic`, `openai`, `gemini`）— 需要 `sk-...` key。 |

自动化时：`lazyclaw onboard --non-interactive --provider X --model Y [--api-key Z]`。`--api-key` 仅在 provider 的 `requiresApiKey` 为 true 时被读取，因此 subscription / 本地 provider 保持无 key。

`onboard` 会写入 `~/.lazyclaw/config.json`。可通过 `LAZYCLAW_CONFIG_DIR=/path/to/dir` 改变位置。

### 交互式聊天（横幅 + 斜杠 ghost-text，v3.85+）

```bash
lazyclaw chat                  # 进入 REPL — 横幅 + 当前 provider/model
lazyclaw chat --pick           # 进入 prompt 前显示方向键 picker
lazyclaw chat --session daily  # 将 turn 持久化到 ~/.lazyclaw/sessions/daily.jsonl
lazyclaw chat --skill review,style  # 将命名 skill 合成为 system prompt
```

启动时（仅 TTY）：

```text
  ╭──────────────────────────────╮
  │   _                          │
  │  | |__ _ _____  _ _          │
  │  | / _` |_ / || | '_|         │
  │  |_\__,_/__\_, |_|            │
  │  LazyClaw  |__/  3.86.0      │
  ╰──────────────────────────────╯

  provider · anthropic
  model    · claude-opus-4-7
  slash    · /help · /model · /provider · /exit
  hint     · → to accept the suggested command, Tab to cycle

›
```

REPL 内：

| Slash | 作用 |
|---|---|
| `/help`        | 列出斜杠命令 |
| `/status`      | 输出 provider + model + 掩码后的 key |
| `/provider X`  | 会话中切换当前 provider（保留对话） |
| `/model X`     | 切换 model。支持统一的 `provider/model` 形式 |
| `/skill a,b`   | 用命名 skill 的合成替换 system prompt |
| `/usage`       | 消息数 + 字符 + 累计 token（当 provider 上报时） |
| `/new` / `/reset` | 清空历史并重新开始 |
| `/exit`        | 退出 |

Cursor 风格 ghost-text 自动补全：以 `/` 开头时，最长匹配的斜杠命令的剩余部分会以暗灰色显示在光标后。**`→`** 接受，**`Tab`** 仍然循环。流式回复中 **Ctrl-C** 仅中止当前 turn（进程不退出）；空 prompt 下 **Ctrl-C** 正常退出。

### 一次性调用（无 REPL）

```bash
lazyclaw agent "summarize: $(cat file.md)"
lazyclaw agent - < prompt.txt                    # 从 stdin 读取
lazyclaw agent "..." --provider openai --model gpt-4.1
lazyclaw agent "..." --skill review              # 合成 system prompt
lazyclaw agent "..." --usage                     # 在 stderr 输出 token 数
lazyclaw agent "..." --cost                      # 配置了 rates 时输出 $
```

### Providers / sessions / skills

```bash
lazyclaw providers list                          # 所有已注册的 provider
lazyclaw providers info anthropic                # 单个 provider 详情
lazyclaw providers test anthropic                # 1-token 可达性探测

lazyclaw sessions list                           # 已持久化的聊天
lazyclaw sessions show daily                     # 转储某个 session 的 turn
lazyclaw sessions search "deploy"                # 全文搜索
lazyclaw sessions export daily > daily.md
lazyclaw sessions clear daily                    # 清空一个 session

lazyclaw skills list                             # 已安装的 markdown skill bundle
lazyclaw skills show review                      # 输出 skill 正文
lazyclaw skills install ./my-skill.md            # 添加 skill
lazyclaw skills remove review
```

### 工作流（DAG / sequential / persistent）

```bash
# 顺序，可恢复（默认）。状态在 ./.workflow-state/<id>/
lazyclaw run my-job ./flow.mjs

# 拓扑层级 DAG，仅内存（更快，不可恢复）
lazyclaw run my-job ./flow.mjs --parallel --concurrency 4

# DAG + 检查点 + 恢复
lazyclaw run my-job ./flow.mjs --parallel-persistent

# 恢复之前中断的 run
lazyclaw resume my-job ./flow.mjs

# 检查持久状态（不执行）
lazyclaw inspect                                 # 列出所有 session
lazyclaw inspect my-job --summary
lazyclaw inspect my-job --critical-path ./flow.mjs
lazyclaw inspect my-job --slowest 5
```

### 本地 HTTP 网关

```bash
lazyclaw daemon                                  # 绑定空闲端口；输出 { port, url }
lazyclaw daemon --port 19600
lazyclaw daemon --auth-token $(openssl rand -hex 16)
lazyclaw daemon --rate-limit 60 --log info       # 60 req/min/IP, JSON access log
lazyclaw daemon --once                           # 应答一次后退出
```

daemon 与 CLI 共享配置和 rate card — `lazyclaw agent` 与 daemon 的 `POST /agent` 输出按字节一致。

### 成本 rate card

```bash
lazyclaw rates list                              # 当前 card
lazyclaw rates set anthropic/claude-opus-4-7 \
  --in 15 --out 75 --cache-read 1.5 --cache-create 18.75
lazyclaw rates copy anthropic/claude-opus-4-7 \
  anthropic/claude-opus-4-6                       # 复制 card
lazyclaw rates delete openai/gpt-3.5-turbo
lazyclaw rates validate                          # schema + 合理性检查
```

`/usage` 与 `--cost` 利用这些 card 在本地计算 USD 总额 — 不会再调用 provider。

### Config + 备份包

```bash
lazyclaw config path                             # → ~/.lazyclaw/config.json
lazyclaw config get provider
lazyclaw config set provider openai
lazyclaw config list
lazyclaw config edit                             # 用 $EDITOR 打开
lazyclaw config validate

lazyclaw export > backup.json                    # config + skills (+ 可选 sessions)
lazyclaw import --from backup.json
```

### Shell 自动补全

```bash
lazyclaw completion bash >> ~/.bashrc
lazyclaw completion zsh  >> ~/.zshrc
```

### 文件位置

| 路径 | 用途 |
|---|---|
| `~/.lazyclaw/config.json` | provider, model, api-key, skills, rates |
| `~/.lazyclaw/sessions/*.jsonl` | 持久化的聊天 session |
| `~/.lazyclaw/skills/*.md` | 已安装的 skill bundle |
| `./.workflow-state/<id>/` | 每个 session 的工作流检查点（基于 cwd） |

`LAZYCLAW_CONFIG_DIR=/elsewhere` 移动前三者的位置；`LAZYCLAW_WORKFLOW_STATE_DIR=...` 移动最后一个。

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
