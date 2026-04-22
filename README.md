# 🧭 Claude Control Center

> **Multi-AI Orchestration Dashboard** — Manage Claude, GPT, Gemini, Ollama, and Codex from a single interface.

[![한국어](https://img.shields.io/badge/🇰🇷_한국어-blue)](./README.ko.md) [![中文](https://img.shields.io/badge/🇨🇳_中文-red)](./README.zh.md)

A local dashboard that manages your entire `~/.claude/` directory (agents, skills, hooks, plugins, MCP, sessions, projects) and adds a powerful **n8n-style workflow engine** with multi-AI provider orchestration.

> Local only, no external calls — Python stdlib server + single HTML file.

---

## ✨ Key Features

### 🧠 Multi-AI Provider Orchestration
- **8 built-in providers**: Claude CLI, Ollama, Gemini CLI, Codex + OpenAI API, Gemini API, Anthropic API, Ollama API
- **Custom CLI providers**: Register any CLI tool as an AI provider
- **Capability system**: chat / embed / code / vision / reasoning
- **Fallback chain**: Auto-switch to next provider on failure
- **Rate limiter**: Token bucket algorithm per provider
- **Multi-AI comparison**: Send same prompt to multiple AIs simultaneously

### 🦙 Ollama Model Hub (Open WebUI Style)
- **23 model catalog**: LLM / Code / Embedding / Vision categories
- **One-click download** with progress bar + delete + model details
- **Auto-start**: `ollama serve` launches automatically with dashboard
- **Engine settings**: Default chat model + embedding model selection
- **Modelfile editor**: Create custom models

### 🔀 Workflow Engine (n8n-style)
- **16 node types**: start, session, subagent, aggregate, branch, output, http, transform, variable, subworkflow, embedding, loop, retry, error_handler, merge, delay
- **Parallel execution**: ThreadPoolExecutor for same-depth nodes
- **SSE real-time streaming**: Live node progress updates
- **Webhook trigger**: External HTTP trigger (`POST /api/workflows/webhook/{id}`)
- **Cron scheduler**: Auto-execute on schedule
- **Export/Import**: Share workflows as JSON
- **Version history**: Save up to 20 versions + restore
- **8 built-in templates**: Multi-AI compare, RAG pipeline, Code review, Data ETL, Retry workflow, etc.
- **18-scene interactive tutorial**: Step-by-step walkthrough
- **Canvas features**: Minimap, node search, Ctrl+C/V/Z, keyboard shortcuts, node grouping

### 📊 Analytics & Monitoring
- **Session scoring** (0-100): engagement, productivity, delegation, diversity, reliability
- **Cost tracking**: Per-provider daily cost charts + stacked bar
- **Usage alerts**: Daily cost/token threshold notifications
- **Provider health dashboard**: Real-time status with port info
- **Workflow statistics**: Success rate, avg duration, provider distribution

### 🌍 Internationalization
- **3 languages**: Korean (ko), English (en), Chinese (zh)
- **2,893 translation keys** per language
- **Dynamic translation**: MutationObserver-based real-time DOM translation
- **error_key system**: Backend error messages with i18n support

### 🎨 UX
- **5 themes**: Dark, Light, Midnight, Forest, Sunset
- **Mobile responsive**: Collapsible sidebar, responsive grids
- **Accessibility**: ARIA labels, focus traps, keyboard navigation
- **Browser notifications**: Workflow completion, usage alerts
- **Performance optimized**: API caching, debounced rendering, RAF batching

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/cmblir/claude-dashboard.git
cd claude-dashboard

# Run (Python 3.10+ required, no dependencies)
python3 server.py

# Open in browser
open http://localhost:8080
```

### Prerequisites
- **Python 3.10+** (stdlib only, no pip install needed)
- **Claude Code CLI** (`npm i -g @anthropic-ai/claude-code`)
- **Ollama** (optional, for local LLM) — auto-started by dashboard

### Environment Variables
```bash
HOST=127.0.0.1          # Bind address (default: 127.0.0.1)
PORT=8080               # Port (default: 8080)
OLLAMA_HOST=http://localhost:11434  # Ollama server
OPENAI_API_KEY=sk-...   # OpenAI API (optional)
GEMINI_API_KEY=AIza...   # Gemini API (optional)
ANTHROPIC_API_KEY=sk-... # Anthropic API (optional)
```

---

## 📐 Architecture

```
claude-dashboard/
├── server.py              # Entry point (auto port-conflict resolution + ollama auto-start)
├── server/
│   ├── ai_providers.py    # 8 providers + CustomCliProvider + RateLimiter
│   ├── ai_keys.py         # API key management + cost tracking + usage alerts
│   ├── ollama_hub.py      # Model catalog (23) + pull/delete/create/serve
│   ├── workflows.py       # DAG engine (16 nodes, parallel, SSE, cron, webhook)
│   ├── errors.py          # i18n error key system (49 keys)
│   ├── routes.py          # 138 API routes (GET 75 + POST 63)
│   ├── sessions.py        # Session indexing + scoring
│   ├── nav_catalog.py     # Tab catalog + multilingual descriptions
│   └── ...                # 20 modules total
├── dist/
│   ├── index.html         # Single-file frontend (~13,250 lines)
│   └── locales/
│       ├── ko.json        # 2,893 keys
│       ├── en.json        # 2,893 keys
│       └── zh.json        # 2,893 keys
└── tools/                 # i18n audit, translation scripts
```

### Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend | Python stdlib `ThreadingHTTPServer` (zero dependencies) |
| Database | SQLite WAL mode |
| Frontend | Single HTML + Tailwind CDN + Chart.js + vis-network |
| i18n | Runtime fetch (`/api/locales/{lang}.json`) + MutationObserver |
| Workflow | DAG topological sort + ThreadPoolExecutor parallel |

---

## 🔢 Stats (v2.1.0)

| Metric | Value |
|--------|-------|
| Node types | 16 |
| AI Providers | 8 built-in + unlimited custom |
| API Routes | 138 (GET 75 + POST 63) |
| i18n Keys | 2,893 × 3 languages |
| Ollama Catalog | 23 models |
| Built-in Templates | 8 |
| Themes | 5 |
| Tutorial Scenes | 18 |

---

## 📝 License

MIT

---

## 🤝 Contributing

Issues and PRs welcome at [github.com/cmblir/claude-dashboard](https://github.com/cmblir/claude-dashboard).
