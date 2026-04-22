# 🧭 Claude Control Center

> **多 AI 编排仪表板** — 在一个本地界面中管理 Claude、GPT、Gemini、Ollama 和 Codex。

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md)
[![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v2.3.0-green.svg)](./CHANGELOG.md)
[![Zero Dependencies](https://img.shields.io/badge/deps-stdlib_only-brightgreen.svg)](#技术栈)

Claude Control Center 是一款**本地优先的仪表板**，统一管理你的整个 `~/.claude/` 目录（代理、技能、钩子、插件、MCP、会话、项目），并内置一个强大的 **n8n 风格工作流引擎** 用于多 AI 供应商编排——全部包含在一行 `python3 server.py` 中。

**无云端上传。无遥测。无需安装任何依赖。** 只需 Python 标准库和一个 HTML 文件。

---

## 🎬 界面预览

```
┌────────────────────────────────────────────────────────────────┐
│  🧭  Claude Control Center                          v2.1.1 🇨🇳│
├────────┬───────────────────────────────────────────────────────┤
│ 🆕 新功能│   🔀 工作流                                          │
│ 🏠 主要 │   ┌──────┐      ┌──────┐      ┌──────┐               │
│ 🛠 工作 │   │🚀开始│─────▶│🗂 Claude│─┬──▶│📤 输出│              │
│ ⚙ 配置 │   └──────┘      └──────┘   │  └──────┘                │
│ 🎛 高级 │                  ┌──────┐   │                         │
│ 📈 系统 │                  │🗂 GPT │──┤                         │
│        │                  └──────┘   │                         │
│ 💬 🐙  │                  ┌──────┐   │                         │
│        │                  │🗂 Gemini│┘                         │
│        │                  └──────┘                              │
└────────┴───────────────────────────────────────────────────────┘
```

6 组 38 个标签页 · 16 种工作流节点 · 8 个 AI 供应商 · 5 种主题 · 3 种语言。

---

## ✨ 为什么做这个项目？

如果你已经在使用 Claude Code，当你添加更多工具（GPT、Gemini、Ollama、Codex）时，就得自己管理一堆 CLI、API 密钥、回退逻辑和成本追踪。而 Claude Code 的配置目录（`~/.claude/`）会不断积累代理、技能、钩子、插件、MCP 服务器和会话，却没有一个统一视图。

**Claude Control Center 在一个标签页内解决了这两个问题。**

| 以前 | 使用 Control Center |
|---|---|
| `cat ~/.claude/settings.json` 肉眼检查 | 38 个标签页各自渲染对应切片 |
| `ls ~/.claude/agents/` → 打开编辑器 | 16 种角色预设 · 一键创建 |
| 用 shell 脚本做多 AI 比较 | 拖 3 个 session 节点 → merge → output |
| 手动搭建 RAG 流水线 | 内置 `RAG Pipeline` 模板 |
| API 成本如黑盒 | 按供应商 / 日 的堆叠图表 |
| 中英文切换靠人脑 | 运行时 `ko` / `en` / `zh` 切换 |

---

## 🎯 使用场景

**个人开发者** — 在一处管理 Claude Code 配置（代理·技能·斜杠命令·MCP·会话）。从 16 种角色预设一键生成子代理。

**团队负责人** — 构建 `Lead → Frontend + Backend + Reviewer` 并行工作流。生成真实 Terminal 会话、按 `session_id` 续接、自动注入反馈笔记、按 N 个 sprint 循环执行。

**AI 研究者** — 将同一提示并行发送到 Claude + GPT + Gemini，合并结果，自动保存对比。或用 `embedding → 向量搜索（HTTP） → Claude` 五次拖拽搭出 RAG 流水线。

**自动化工程师** — 通过 Webhook（`POST /api/workflows/webhook/{id}`）从 GitHub Actions / Zapier 触发。用 Cron 每日自动执行。失败重试、回退到低价供应商、token 预算超标时告警。

**Ollama 高级用户** — 浏览 23 个模型目录，一键下载，用 Modelfile 创建自定义模型，选择默认聊天 / 嵌入模型——无需再记忆 `ollama pull` 命令。

---

## 🚀 快速开始（30 秒）

```bash
git clone https://github.com/cmblir/claude-dashboard.git
cd claude-dashboard
python3 server.py
# → 打开 http://localhost:8080
```

**就这样。** 无需 `pip install`、`npm install` 或 Docker。服务器仅使用 Python 标准库。

### 先决条件

| 必需 | 推荐 | 可选 |
|---|---|---|
| Python 3.10+ | Claude Code CLI — `npm i -g @anthropic-ai/claude-code` | Ollama（自动启动） |
| — | macOS（用于 Terminal.app 会话生成） | GPT / Gemini / Anthropic API 密钥 |

### 环境变量

```bash
HOST=127.0.0.1                       # 绑定地址（默认）
PORT=8080                            # 端口（默认）
CHAT_MODEL=haiku                     # 聊天机器人模型：haiku（默认） / sonnet / opus
OLLAMA_HOST=http://localhost:11434   # Ollama 服务器
OPENAI_API_KEY=sk-...                # 可选，也可在 UI 中设置
GEMINI_API_KEY=AIza...               # 可选
ANTHROPIC_API_KEY=sk-...             # 可选
```

API 密钥也可以在 `🧠 AI 供应商` 标签页中保存 — 存储于 `~/.claude-dashboard-config.json`。

🆕 **v2.3.0 — 提示缓存实验室**（`work` 组）：对 Anthropic Messages API 的 `cache_control` 在系统/工具/消息块中指定，实时测量 `cache_creation / cache_read` 令牌和 USD 成本节约。一键运行 3 种示例（系统/文档/工具缓存）+ 历史 20 条。→ [docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)

---

## ✨ 核心功能

### 🔀 工作流引擎（n8n 风格 DAG）

- **16 种节点类型**：`start` · `session` · `subagent` · `aggregate` · `branch` · `output` · `http` · `transform` · `variable` · `subworkflow` · `embedding` · `loop` · `retry` · `error_handler` · `merge` · `delay`
- **并行执行** — 拓扑分层 + ThreadPoolExecutor
- **SSE 流式** — 节点级实时进度
- **🔁 Repeat** — 最大次数 · 间隔 · 调度窗口（`HH:MM~HH:MM`）· 反馈笔记自动注入
- **Cron 调度器** — 5 字段 cron 表达式，分钟级精度
- **Webhook 触发** — `POST /api/workflows/webhook/{wfId}` 供任意外部系统调用
- **Export / Import** — 以 JSON 共享工作流
- **版本历史** — 自动保留最近 20 个版本 + 一键恢复
- **条件执行** — 11 种（contains · equals · regex · length · 带 AND/OR 的 expression ...）
- **变量作用域** — `{{变量名}}` 模板替换，全局或本地
- **8 个模板** — 5 个内置（多 AI 比较 · RAG · 代码审查 · 数据 ETL · 重试）+ 3 个团队启动（Lead/FE/BE · 研究 · 并行×3）+ 无限自定义
- **画布 UX** — 小地图 · 节点搜索（高亮+dim）· 分组（Shift+点击）· Ctrl+C/V/Z · `?` 快捷键帮助
- **18 幕交互式教程** — typewriter + 光标动画

### 🧠 多 AI 供应商

- **8 个内置** — Claude CLI · Ollama · Gemini CLI · Codex + OpenAI API · Gemini API · Anthropic API · Ollama API
- **自定义 CLI 供应商** — 将任意 CLI 注册为供应商（chat + embed 命令）
- **回退链** — 失败时自动切换（默认：`claude-cli → anthropic-api → openai-api → gemini-api`）
- **速率限制器** — 每供应商令牌桶（requests/min）
- **多 AI 比较** — 同一提示、多个供应商、结果并列
- **设置向导** — 新手三步引导（选择 → 配置 → 测试）
- **健康仪表板** — 每供应商实时可用性
- **成本追踪** — 按供应商 / 工作流 / 日的堆叠柱状图
- **使用量告警** — 可配置的每日 token / 成本阈值 → 浏览器通知

### 🦙 Ollama 模型中心（Open WebUI 风格）

- **23 个模型目录** — LLM · Code · Embedding · Vision 四个类别（llama3.1、qwen2.5、gemma2、deepseek-r1、bge-m3 等）
- **一键拉取** — 进度条（SSE 轮询）+ 删除 + 模型详情
- **自动启动** — 仪表板启动时自动运行 `ollama serve`
- **默认模型选择** — 每供应商聊天 / 嵌入默认值
- **Modelfile 编辑器** — 在 UI 中创建自定义模型

### 🤝 Claude Code 集成（38 个标签页）

| 分组 | 标签页 |
|---|---|
| 🆕 新功能 | `features` · `onboarding` · `guideHub` |
| 🏠 主要 | `overview` · `projects` · `analytics` · `aiEval` · `sessions` |
| 🛠️ 工作 | `workflows` · `aiProviders` · `agents` · `projectAgents` · `skills` · `commands` |
| ⚙️ 配置 | `hooks` · `permissions` · `mcp` · `plugins` · `settings` · `claudemd` |
| 🎛️ 高级 | `outputStyles` · `statusline` · `plans` · `envConfig` · `modelConfig` · `ideStatus` · `marketplaces` · `scheduled` |
| 📈 系统 | `usage` · `metrics` · `memory` · `tasks` · `backups` · `bashHistory` · `telemetry` · `homunculus` · `team` · `system` |

亮点：**16 种子代理角色预设**（backend-dev, security-reviewer, architect, ...）、带质量评分的会话时间线、带 Markdown 预览的 CLAUDE.md 编辑器、MCP 连接器安装器、插件市场集成。

### 🌍 多语言支持

- **3 种语言** — 韩语（`ko`，默认）· 英语（`en`）· 中文（`zh`）
- **每种语言 2,932 个翻译键** · **英文/中文模式下韩文残留为 0**（已验证）
- **运行时 DOM 翻译** — 基于 MutationObserver（无需刷新页面）
- **`error_key` 系统** — 后端错误消息在前端本地化
- **校验流水线** — `scripts/verify-translations.js` 执行四项检查（parity · `t()` 调用 · audit · static DOM）

### 🎨 UX 与无障碍

- **5 种主题** — Dark · Light · Midnight · Forest · Sunset
- **移动端响应** — 可折叠侧边栏、全屏模态
- **无障碍** — ARIA 标签、`role="dialog"`、焦点陷阱、键盘导航
- **浏览器通知** — 工作流完成、使用量告警、系统事件
- **性能优化** — API 缓存、防抖自动刷新、RAF 批处理

---

## 📐 架构

```
claude-dashboard/
├── server.py                     # 入口（端口冲突自动解决 + ollama 自动启动）
├── server/                       # 14,067 行 · 仅使用标准库
│   ├── routes.py                 # 143 个 API 路由（GET + POST + PUT + DELETE + regex webhook）
│   ├── workflows.py              # DAG 引擎 · 16 种节点执行 · Repeat · Cron · Webhook (2,296)
│   ├── ai_providers.py           # 8 个供应商 · 注册表 · 速率限制器 (1,723)
│   ├── ai_keys.py                # 密钥管理 · 自定义供应商 · 成本追踪 (734)
│   ├── ollama_hub.py             # 模型目录 · pull/delete/create · serve 管理 (606)
│   ├── nav_catalog.py            # 38 个标签页单一数据源 + i18n 描述
│   ├── features.py               # 功能发现 · AI 评估 · 推荐
│   ├── projects.py               # 项目浏览器 · 16 个子代理角色预设
│   ├── sessions.py               # 会话索引 · 质量评分 · 代理图谱
│   ├── system.py                 # usage · memory · tasks · metrics · backups · telemetry
│   ├── errors.py                 # i18n 错误键系统（49 个键）
│   └── …                         # 共 20 个模块
├── dist/
│   ├── index.html                # 单文件 SPA（~13,500 行）
│   └── locales/{ko,en,zh}.json   # 2,932 键 × 3 语言
├── tools/
│   ├── translations_manual_*.py  # 手动翻译覆盖
│   ├── extract_ko_strings.py     # 韩文字符串提取器
│   ├── build_locales.py          # ko/en/zh JSON 构建器
│   └── i18n_audit.mjs            # Node 端审计
├── scripts/
│   ├── verify-translations.js    # 四阶段 i18n 校验
│   └── translate-refresh.sh      # 一键流水线
├── VERSION · CHANGELOG.md
└── README.md · README.ko.md · README.zh.md
```

### 数据存储（均在 `$HOME`，可通过 env var 覆盖）

| 文件 | 内容 |
|---|---|
| `~/.claude-dashboard-workflows.json` | 工作流 + 执行记录 + 自定义模板 + 版本历史 + 成本 |
| `~/.claude-dashboard-config.json` | API 密钥 · 自定义供应商 · 默认模型 · 回退链 · 使用量阈值 |
| `~/.claude-dashboard-translations.json` | AI 翻译缓存 |
| `~/.claude-dashboard.db` | SQLite 会话索引 |
| `~/.claude-dashboard-mcp-cache.json` | MCP 目录缓存 |
| `~/.claude-dashboard-ai-evaluation.json` | AI 评估缓存 |

原子写入：`server/utils.py::_safe_write`（`.tmp → rename`），并发安全使用 threading lock。

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 标准库 `ThreadingHTTPServer`（零依赖） |
| 数据库 | SQLite WAL 模式 |
| 前端 | 单 HTML + Tailwind CDN + Chart.js + vis-network |
| i18n | 运行时 JSON fetch + MutationObserver DOM 翻译 |
| 工作流 | 拓扑 DAG 排序 + `concurrent.futures.ThreadPoolExecutor` |
| 聊天机器人 | 动态系统提示（每次请求读取 VERSION + CHANGELOG + nav_catalog） |

---

## 🔢 统计（v2.1.1）

| 指标 | 值 |
|---|---|
| 后端代码 | 14,067 行 · 20 个模块 · 仅标准库 |
| 前端代码 | ~13,500 行 · 单 HTML 文件 |
| API 路由 | **143** |
| 标签页 | **38**（6 组） |
| 工作流节点类型 | **16** |
| AI 供应商 | **8** 个内置 + 无限自定义 |
| Ollama 目录 | **23** 个模型 |
| 子代理角色预设 | **16** |
| 内置工作流模板 | **8**（内置 5 + 团队 3） |
| i18n 键 | **2,932** × 3 语言 · 缺失 0 |
| 主题 | **5** |
| 教程场景 | **18** |

---

## 🛠️ 故障排查

| 问题 | 解决方案 |
|---|---|
| 端口 8080 已被占用 | `PORT=8090 python3 server.py`（服务器也会询问是否关闭已有进程） |
| `claude` 命令未找到 | 安装 Claude Code CLI：`npm i -g @anthropic-ai/claude-code` |
| Ollama 连接失败 | 检查 `OLLAMA_HOST`（默认 `http://localhost:11434`），或让仪表板自动启动 |
| macOS 会话生成失败 | 在系统设置 → 隐私与安全性 → 自动化 中授予 Terminal 权限 |
| 英文模式仍显示韩文 | 运行 `scripts/translate-refresh.sh`（重建 locales + 校验） |
| 聊天机器人回答"不知道此功能" | 机器人会实时读取 `VERSION` + `CHANGELOG.md` + `nav_catalog.py` — 添加功能时请同步更新这三个文件 |

---

## 🤝 贡献

欢迎在 [github.com/cmblir/claude-dashboard](https://github.com/cmblir/claude-dashboard) 提交 Issue 和 PR。

### 添加新标签页（7 步）

1. 在 `dist/index.html::NAV` 添加条目
2. 在 `dist/index.html` 中实现 `VIEWS.<id>` 渲染器
3. 在 `server/nav_catalog.py::TAB_CATALOG` 添加 `(id, group, desc, keywords)`
4. 在 `TAB_DESC_I18N` 添加 `en` / `zh` 描述
5. （如需要）在 `server/routes.py` 添加后端路由 + `server/` 下的模块
6. 在 `tools/translations_manual_9.py` 注册新 UI 字符串
7. 运行 `python3 tools/extract_ko_strings.py && (cd tools && python3 build_locales.py) && node scripts/verify-translations.js`

### 翻译贡献

参阅 [`TRANSLATION_CONTRIBUTING.md`](./TRANSLATION_CONTRIBUTING.md) 和 [`TRANSLATION_MIGRATION.md`](./TRANSLATION_MIGRATION.md)。所有 UI 字符串必须在 ko / en / zh 中存在；`verify-translations.js` 会拦截缺失键。

### 版本规则

- `MAJOR` — 工作流 / 架构破坏性变更
- `MINOR` — 新增标签页或重要功能（向后兼容）
- `PATCH` — Bug 修复、UI 微调、i18n 加强

每次功能变更时，`VERSION` + `CHANGELOG.md` + `git tag -a vX.Y.Z` 三者一并更新。

---

## 📝 许可证

[MIT](./LICENSE) — 个人和商业使用均免费。署名欢迎但非必需。

---

## 🙏 致谢

- [Anthropic Claude Code](https://claude.com/claude-code) — 本仪表板所围绕的 CLI
- [n8n](https://n8n.io) — 工作流编辑器灵感来源
- [Open WebUI](https://openwebui.com) — Ollama 模型中心灵感来源
- 所有为开源 LLM 生态做出贡献的人 🧠
