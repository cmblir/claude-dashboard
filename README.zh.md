# 🧭 Claude Control Center

> **多 AI 编排仪表盘** — 在一个界面中管理 Claude、GPT、Gemini、Ollama 和 Codex。

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md) [![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md)

一个本地仪表盘，管理整个 `~/.claude/` 目录（代理、技能、钩子、插件、MCP、会话、项目），并提供强大的 **n8n 风格工作流引擎**，支持多 AI 供应商编排。

> 仅限本地使用，无外部调用 — Python 标准库服务器 + 单个 HTML 文件。

---

## ✨ 核心功能

### 🧠 多 AI 供应商编排
- **8 个内置供应商**：Claude CLI、Ollama、Gemini CLI、Codex + OpenAI API、Gemini API、Anthropic API、Ollama API
- **自定义 CLI 供应商**：将任意 CLI 工具注册为 AI 供应商
- **能力系统**：chat / embed / code / vision / reasoning
- **降级链**：失败时自动切换到下一个供应商（可编辑）
- **速率限制器**：每个供应商的令牌桶算法
- **多 AI 对比**：同时向多个 AI 发送相同提示并比较结果

### 🦙 Ollama 模型中心（Open WebUI 风格）
- **23 个模型目录**：LLM / 代码 / 嵌入 / 视觉 4 个类别
- **一键下载** + 进度条 + 删除 + 详细信息
- **自动启动**：仪表盘启动时自动运行 `ollama serve`
- **引擎设置**：默认聊天模型 + 嵌入模型选择
- **Modelfile 编辑器**：创建自定义模型

### 🔀 工作流引擎（n8n 风格）
- **16 种节点类型**：start、session、subagent、aggregate、branch、output、http、transform、variable、subworkflow、embedding、loop、retry、error_handler、merge、delay
- **并行执行**：使用 ThreadPoolExecutor 同时执行同一深度的节点
- **SSE 实时流**：节点进度实时更新
- **Webhook 触发**：外部 HTTP 触发工作流（`POST /api/workflows/webhook/{id}`）
- **Cron 调度器**：按计划自动执行
- **导出/导入**：以 JSON 格式共享工作流
- **版本历史**：保存最近 20 个版本 + 还原
- **8 个内置模板**：多 AI 对比、RAG 管道、代码审查、数据 ETL、重试工作流等
- **18 场景交互教程**：逐步使用指南
- **画布功能**：小地图、节点搜索、Ctrl+C/V/Z、键盘快捷键、节点分组

### 📊 分析与监控
- **会话评分**（0-100）：参与度、生产力、委托、多样性、可靠性
- **成本跟踪**：按供应商的每日成本图表 + 堆叠柱状图
- **用量警报**：每日成本/Token 阈值通知
- **供应商健康仪表盘**：实时状态 + 端口信息
- **工作流统计**：成功率、平均耗时、供应商分布

### 🌍 国际化
- **3 种语言**：韩语（ko）、英语（en）、中文（zh）
- 每种语言 **2,893 个翻译键**
- **动态翻译**：基于 MutationObserver 的实时 DOM 翻译
- **error_key 系统**：后端错误消息多语言支持

### 🎨 用户体验
- **5 个主题**：暗色、亮色、午夜、森林、日落
- **移动端响应式**：可折叠侧边栏、响应式网格
- **无障碍**：ARIA 标签、焦点陷阱、键盘导航
- **浏览器通知**：工作流完成、用量超标提醒
- **性能优化**：API 缓存、防抖渲染、RAF 批处理

---

## 🚀 快速开始

```bash
# 克隆
git clone https://github.com/cmblir/claude-dashboard.git
cd claude-dashboard

# 运行（需要 Python 3.10+，无需安装依赖）
python3 server.py

# 在浏览器中打开
open http://localhost:8080
```

### 前置条件
- **Python 3.10+**（仅使用标准库，无需 pip 安装）
- **Claude Code CLI**（`npm i -g @anthropic-ai/claude-code`）
- **Ollama**（可选，用于本地 LLM）— 仪表盘自动启动

### 环境变量
```bash
HOST=127.0.0.1          # 绑定地址（默认：127.0.0.1）
PORT=8080               # 端口（默认：8080）
OLLAMA_HOST=http://localhost:11434  # Ollama 服务器
OPENAI_API_KEY=sk-...   # OpenAI API（可选）
GEMINI_API_KEY=AIza...   # Gemini API（可选）
ANTHROPIC_API_KEY=sk-... # Anthropic API（可选）
```

---

## 📐 架构

```
claude-dashboard/
├── server.py              # 入口（自动端口冲突解决 + ollama 自动启动）
├── server/
│   ├── ai_providers.py    # 8 个供应商 + CustomCliProvider + RateLimiter
│   ├── ai_keys.py         # API 密钥管理 + 成本跟踪 + 用量警报
│   ├── ollama_hub.py      # 模型目录（23 种）+ pull/delete/create/serve
│   ├── workflows.py       # DAG 引擎（16 节点、并行、SSE、cron、webhook）
│   ├── errors.py          # i18n 错误键系统（49 键）
│   ├── routes.py          # 138 个 API 路由（GET 75 + POST 63）
│   ├── sessions.py        # 会话索引 + 评分
│   ├── nav_catalog.py     # 标签目录 + 多语言描述
│   └── ...                # 共 20 个模块
├── dist/
│   ├── index.html         # 单文件前端（~13,250 行）
│   └── locales/
│       ├── ko.json        # 2,893 键
│       ├── en.json        # 2,893 键
│       └── zh.json        # 2,893 键
└── tools/                 # i18n 审计、翻译脚本
```

---

## 🔢 统计（v2.1.0）

| 指标 | 值 |
|------|-----|
| 节点类型 | 16 种 |
| AI 供应商 | 8 内置 + 无限自定义 |
| API 路由 | 138（GET 75 + POST 63） |
| i18n 键 | 2,893 × 3 种语言 |
| Ollama 目录 | 23 个模型 |
| 内置模板 | 8 种 |
| 主题 | 5 种 |
| 教程场景 | 18 个 |

---

## 📝 许可证

MIT

---

## 🤝 贡献

欢迎在 [github.com/cmblir/claude-dashboard](https://github.com/cmblir/claude-dashboard) 提交 Issue 和 PR。
