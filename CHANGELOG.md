# Changelog

모든 의미 있는 변경은 이 파일에 기록된다. [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다 — `MAJOR.MINOR.PATCH`.

기능 추가 시 규칙:
- **MAJOR** : 기존 워크플로우·스키마 파괴적 변경
- **MINOR** : 신규 탭/기능 추가 (하위 호환)
- **PATCH** : 버그 수정, UI 미세 조정, i18n 보강

기능 업데이트 시 (a) `VERSION` 파일 번호 bump, (b) 아래 표에 한 줄 추가, (c) `git tag v<버전>` 권장.

---
## [2.66.132] — 2026-05-02

### Added
- 📷 **Stronger drag-over cue when files are dragged in** (QQ57). The
  composer's dashed outline turns blue (vs. the default amber) when
  the drag payload contains files, signalling that image / text
  attach is wired and ready. Subtle cue but pairs with QQ39 paste/
  drop to reduce "did anything happen?" hesitation.

### Verified
- ✅ Full pytest suite: **429 passed**, 2 pre-existing fails in
  `tests/test_provider_error_passthrough.py` (legacy assertions
  obsoleted by the FF1 fallback chain). No regression caused by
  the QQ18 → QQ57 changes.

---
## [2.66.131] — 2026-05-02

### Fixed
- 🧹 **Sweep orphan chat drafts/histories on tab open** (QQ56). One-
  time-per-tab-open scan: any `cc.lc.hist.<sid>` or
  `cc.lc.draft.<sid>` whose `<sid>` is no longer in `cc.lc.sessions`
  is removed. Cleans up legacy bytes left by users who deleted
  sessions before QQ54 fixed the cleanup match. Bounded in time —
  only runs when the chat view actually mounts.

---
## [2.66.130] — 2026-05-02

### Fixed
- 🛡 **Strip base64 images from the help-bot chat prompt too** (QQ55).
  QQ49 cleaned `handle_lazyclaw_chat_stream`, but the older help-bot
  SSE endpoint (line ~542 of `actions.py`) still piped the full
  prompt — including any image markdown forwarded from the chat —
  to `claude -p`. Now scrubbed via the same
  `_extract_inline_images()` helper.

---
## [2.66.129] — 2026-05-02

### Fixed
- 🧹 **Session delete now actually frees history + draft bytes**
  (QQ54). The old cleanup loop matched only keys ending in
  `:<sid>`, but the active schema is `cc.lc.hist.<sid>` and
  `cc.lc.draft.<sid>` — neither ends in a colon. Result: deleting
  a session left megabytes of orphan history in localStorage,
  silently shrinking the budget for new conversations and
  triggering QQ53 quota recovery prematurely. Cleanup now matches
  the real keys (and keeps the legacy suffix path as a fallback).

---
## [2.66.128] — 2026-05-02

### Fixed
- 💾 **Chat history quota recovery for embedded images** (QQ53). After
  QQ39 added base64 image attachments, a single chat session can
  push past localStorage's ~5–10 MB cap. `_lcSaveHistory()` now
  catches `QuotaExceededError` and recovers in two stages: (1)
  replace `data:image/…` URLs in the heaviest message with
  `_[image dropped to fit storage]_`, retry; (2) drop the oldest
  message; (3) repeat. Conversation text + recent images are
  preserved while ancient image bytes get evicted first.

---
## [2.66.127] — 2026-05-02

### Added
- 📖 **Keyboard shortcuts surfaced in `/help`** (QQ52). The `/help`
  slash command now lists the QQ50 session-nav keys, QQ51 history
  recall, Cmd+K search, Enter / Shift+Enter, and the QQ39 image
  paste/drop tip alongside the existing slash commands. Helps new
  users discover the recently-added shortcuts without spelunking
  the changelog.

---
## [2.66.126] — 2026-05-02

### Added
- ⌨ **Shell-history recall in chat composer** (QQ51). Cmd/Ctrl+↑
  pulls the previous user message into the composer; repeated
  presses walk back through the session's user messages.
  Cmd/Ctrl+↓ walks forward / clears back to a blank draft. The
  index resets on each send. Lets users tweak and resend a
  variation of an earlier prompt without scrolling and copying.

---
## [2.66.125] — 2026-05-02

### Added
- ⌨ **Cmd/Ctrl+Shift+[ / ] — prev/next chat session** (QQ50). Mirrors
  the workflow Cmd+[/] navigation (LL27) so users with many parallel
  conversations can jump session-to-session without leaving the
  keyboard. Skipped when focus is in an input/textarea so it doesn't
  hijack `[` typing in messages.

---
## [2.66.124] — 2026-05-02

### Fixed
- 🛡 **Strip base64 images from claude-cli prompts** (QQ49). claude-
  cli's `-p` flag is text-only — passing a multi-MB base64 blob via
  argv was either truncated by the OS or hallucinated about. The
  prompt is now scrubbed before invocation in both
  `ClaudeCliProvider.execute()` and the lazyclaw chat SSE relay
  (`actions.py::handle_lazyclaw_chat_stream`); the model receives a
  short note saying an image was attached and to switch to
  claude-api or a vision-capable assignee. Pairs with the QQ44
  client-side soft warning.

---
## [2.66.123] — 2026-05-02

### Performance
- 🚀 **Throttle inspector re-render under SSE bursts** (QQ48). QQ47
  re-renders the inspector on every status-sig change so the Gantt
  stays live, but a fast workflow (10+ nodes finishing within a
  second) would rebuild the inspector HTML 10× — visible lag on
  large boards. The trigger now keeps the dirty flag flip but only
  actually calls `_wfRenderInspector()` at most once every 250 ms
  (≤4 fps). User-driven renders bypass the throttle (they go through
  the normal `_wfRenderInspector({force:true})` paths).

---
## [2.66.122] — 2026-05-02

### Fixed
- 📊 **Gantt panel refreshes as run progresses** (QQ47, follow-up to
  QQ46). The inspector mini Gantt previously stayed stale during a
  run because the run-status apply path only invalidated the canvas
  cache, not `__wf._inspectorDirty`. The status-sig diff in the SSE
  apply loop now also marks the inspector dirty and re-renders it,
  so the duration bars grow live as nodes complete.

---
## [2.66.121] — 2026-05-02

### Added
- 📊 **Last-run mini Gantt in workflow inspector** (QQ46). After a
  workflow run completes, the inspector renders a per-node duration
  bar chart sorted descending — top 12 nodes, total time at the
  header, blue bars for normal runs, red for errors, amber for
  pinned (QQ20). Click a row to jump-select that node. Quick way
  to spot the slowest step without combing through `nodeResults`.

---
## [2.66.120] — 2026-05-02

### Fixed
- 🔎 **Cmd+K chat search now finds per-session histories** (QQ45).
  The search modal previously scanned only the legacy
  `cc.lazyclawChat.history.<assignee>` keys, so any conversation
  saved under the per-session `cc.lc.hist.<sid>` schema (used by
  QQ23 branching and QQ24 lineage) was invisible. Search now scans
  both keyspaces, labels each hit with the source session name,
  and the result button switches to the correct session before
  scrolling to the matched message.

---
## [2.66.119] — 2026-05-02

### Added
- ⚠ **Soft vision warning when sending images to non-vision models**
  (QQ44). If the composer text contains a base64 image but the
  assignee id doesn't match a vision-capable substring (`opus`,
  `sonnet`, `haiku`, `gpt-4/5/o`, `gemini`, `llava`, `vision`,
  `claude-`), the user gets a one-time-per-session toast warning.
  Stored in `sessionStorage` so the banner doesn't pile up if the
  same session repeatedly attaches images.

---
## [2.66.118] — 2026-05-02

### Fixed
- 🖼 **Ollama vision streaming completes the multimodal loop** (QQ43).
  `OllamaApiProvider.execute_stream()` now also runs through
  `_extract_inline_images()` and forwards the base64 strings as
  the `images` field. With QQ40 (cloud one-shot), QQ41 (Ollama
  one-shot), and QQ42 (cloud streaming), every chat path now
  correctly delivers attached images to the configured vision
  model.

---
## [2.66.117] — 2026-05-02

### Fixed
- 🖼 **Vision routing now also works for streaming responses** (QQ42).
  QQ40 wired multimodal images into the one-shot `execute()` paths
  but missed the streaming `execute_stream()` paths used by the
  lazyclaw chat (default route). OpenAI, Anthropic, and Gemini
  streaming now also call `_extract_inline_images()` and emit
  the appropriate image content blocks. Without this fix, dropping
  an image into the chat would only reach the model when the user
  ran a non-streaming workflow node.

---
## [2.66.116] — 2026-05-02

### Added
- 🖼 **Ollama vision routing** (QQ41). `OllamaApiProvider.execute()`
  now also runs through `_extract_inline_images()` and forwards the
  base64 strings as the Ollama `/api/generate` `images` field —
  the format vision-capable local models (llava, llama3.2-vision,
  bakllava, etc.) expect. Closes the multimodal loop for local
  models alongside the cloud providers covered in QQ40.

---
## [2.66.115] — 2026-05-02

### Added
- 🖼 **Vision routing for inline base64 images** (QQ40, multimodal end-
  to-end). New `_extract_inline_images()` helper in `ai_providers.py`
  pulls every `![alt](data:image/...;base64,...)` out of the prompt
  and returns a `(clean_text, [{mime,base64,data_url}])` pair.
  - **Anthropic API** — emits `image` content blocks with
    `source: {type: 'base64', media_type, data}`.
  - **OpenAI API** — emits `image_url` blocks with `image_url.url`
    set to the original data URL.
  - **Gemini API** — emits `inline_data: {mime_type, data}` parts.
  When no `data:image/` is found the helper short-circuits and the
  legacy plain-string content path is unchanged. Pairs with the
  QQ39 paste/drop UI: drop or paste an image into the chat composer
  and the configured vision model now actually sees it.

---
## [2.66.114] — 2026-05-02

### Added
- 📷 **Image attach in chat — paste & drop** (QQ39, OpenClaw parity).
  Dropping an image file (≤ 8 MB) onto the composer or pasting one
  from the clipboard now embeds it as a base64 `![name](data:…)`
  markdown reference. User messages are now markdown-rendered so the
  image displays inline in the conversation. Multimodal provider
  routing comes next; this iteration covers UI capture + history
  persistence so images survive refresh and export.

### Changed
- User chat messages now use `marked.parse` (previously plain
  `<pre>`). Plain text is unaffected; backticked code, lists, and
  links now render as expected.

---
## [2.66.113] — 2026-05-02

### Added
- 🏷 **Workflow tags + sidebar tag filter** (QQ38, n8n parity for
  organizing many workflows). Each workflow now has a `tags: string[]`
  field — clamped to 20 chars each, max 10 per workflow, lowercased
  and de-duplicated server-side. Sidebar shows a chip strip above
  the list ("All / #prod / #demo / …"); clicking a chip filters
  the workflow list. Tags also appear as small chips on each list
  row and are editable as a comma-separated input in the inspector
  meta block. Composes with the existing fuzzy search.

---
## [2.66.112] — 2026-05-02

### Performance
- 🚀 **Sticky annotations skipped during execution** (QQ37). The
  topology builder in `_run_one_iteration` now filters out
  `sticky` nodes before computing levels, so they don't sit in
  the level-0 parallel batch alongside `start`. Pure annotations
  no longer occupy a thread or contribute to execution latency.

---
## [2.66.111] — 2026-05-02

### Added
- 🟨 **Sticky note nodes on workflow canvas** (QQ36, n8n parity).
  New `sticky` node type — free-floating markdown annotations that
  don't affect execution. 5 colors (yellow / blue / green / pink /
  gray), resizable (120-800 px width, 80-800 px height), markdown
  rendered via `marked.parse`. Server-side: registered in
  `_NODE_TYPES`, sanitized with text / color / width / height,
  executor returns instantly with empty output. Client-side: new
  "주석" palette category, custom SVG renderer using
  `<foreignObject>`, color picker + dimension inputs in the editor.

---
## [2.66.110] — 2026-05-02

### Added
- ⬇ **Scroll-to-bottom button in chat** (QQ35). When the chat log is
  scrolled more than 120 px above the latest message, a circular ⬇
  button appears at the bottom-right. Clicking jumps to the newest
  message. Hides automatically when at the bottom. Essential for
  long sessions where streaming output pushes content past the
  fold.

---
## [2.66.109] — 2026-05-02

### Added
- 📐 **Align / distribute toolbar for multi-selected nodes** (QQ34,
  n8n parity). Whenever 2+ nodes are selected (Shift+click, lasso, or
  Cmd+A), an 8-button bar appears in the workflow toolbar:
  ⫷ left, ⇔ horizontal center, ⫸ right, ⫶↑ top, ⇕ vertical center,
  ⫶↓ bottom, ≡↔ horizontal distribute (3+ nodes), ≡↕ vertical
  distribute (3+ nodes). Pushes one undo step. Pairs with QQ27 / QQ28
  / QQ29 / QQ30 for the full multi-select editing flow.

---
## [2.66.108] — 2026-05-02

### Added
- 💾 **Per-session draft autosave for chat composer** (QQ33). Typing
  in the composer now persists to `localStorage["cc.lc.draft.<sid>"]`
  with a 350 ms debounce. On tab open / refresh, the draft is
  restored if the textarea is empty. Sending or running a slash
  command clears the draft. No more lost prompts after a refresh
  or accidental tab swap.

---
## [2.66.107] — 2026-05-02

### Added
- ▾ **Collapsible long messages in chat** (QQ32). Assistant or user
  messages exceeding ~1500 chars or ~30 lines now collapse to 300 px
  with a fade overlay and a `▾ 더보기 (N자)` button. Click to expand;
  collapse again with `▴ 접기`. Keeps long sessions scrollable
  without losing access to full content.

---
## [2.66.106] — 2026-05-02

### Added
- 📋 **Code block copy buttons in chat** (QQ31, OpenClaw parity).
  Every `<pre>` block in an assistant message now gets a top-right
  📋 button. Clicking writes the inner `<code>` text to the
  clipboard and flashes ✓ for 1.2 s. Saves the select-all-then-copy
  dance for snippets.

---
## [2.66.105] — 2026-05-02

### Added
- 🗑 **Multi-select delete with confirm** (QQ30, n8n parity). Delete /
  Backspace now removes every node in `__wfMultiSelected` (and all
  edges incident on the set) in one undo step. Asks for confirmation
  when the selection has more than 3 nodes — small lassos delete
  silently. Pairs with QQ27 / QQ28 / QQ29.

---
## [2.66.104] — 2026-05-02

### Added
- 📋 **Multi-node copy/paste with internal edges** (QQ29, n8n parity).
  Cmd+C now copies every node in `__wfMultiSelected` (or just the
  single selection if multi is empty) plus every edge whose endpoints
  both fall inside the set. Cmd+V remaps the edge endpoints to fresh
  node ids so the cluster pastes wired up. Pasted nodes become the
  new multi-selection so QQ28 group-drag immediately applies — lasso,
  copy, paste, drag the duplicate cluster anywhere.

---
## [2.66.103] — 2026-05-02

### Added
- 🟦 **Group drag for multi-selected nodes** (QQ28, n8n parity).
  Clicking and dragging any node that belongs to the active multi-
  selection now moves all selected nodes together while preserving
  their relative layout. Lead-node grid snap (Alt to bypass) is
  applied via a delta so the cluster doesn't drift on snap. Pairs
  with QQ27 rubber-band: lasso a cluster, then move it as one.

---
## [2.66.102] — 2026-05-02

### Added
- 🟦 **Rubber-band drag selection on workflow canvas** (QQ27, n8n
  parity). Hold Shift and drag on an empty area of the canvas to
  draw a dashed selection rectangle. On release, all nodes whose
  bounding box intersects the rectangle are added to the multi-
  selection (composes with existing Shift+click). Cmd+A still
  selects-all. Replaces the missing "drag-to-select" gap that was
  the most-asked n8n feature.

---
## [2.66.101] — 2026-05-02

### Added
- 🔤 **Per-session token-usage badge in chat sidebar** (QQ26). Each
  session row now shows `🔤 12.4k` (sum of `tokensIn + tokensOut`
  across all messages) next to the timestamp. Quick visibility into
  which conversations are draining the budget without opening them.

---
## [2.66.100] — 2026-05-02

### Performance
- 🚀 **Workflow canvas RAF coalescing** (QQ25). Multiple
  `_wfRenderCanvas()` calls within one animation frame now collapse
  to a single sync render via `requestAnimationFrame`. Bulk
  operations (paste many nodes, undo across multiple changes, run-
  status updates from rapid SSE ticks) no longer trigger N redundant
  SVG diffs. Drag stays smooth — it uses
  `_wfApplyDragTransform()` which writes `setAttribute` directly and
  bypasses the renderer. Callers that genuinely need an immediate DOM
  can use the new `_wfRenderCanvasNow()` escape hatch.

---
## [2.66.99] — 2026-05-02

### Added
- ↳ **Branch lineage hint in chat sidebar** (QQ24). Sessions created
  via QQ23 branching now display `↳ <parent label> #<idx>` in the
  sidebar row. Click the lineage chip → jumps to the parent session.
  Lets users navigate the conversation tree without losing where
  they came from.

---
## [2.66.98] — 2026-05-02

### Added
- 🍴 **Branch conversation from any message** (QQ23, ChatGPT parity).
  Hovering any chat message now exposes a 🍴 button. Clicking creates
  a new session whose history is everything up to and including that
  message, with `parentId` and `branchedAt` metadata so the lineage
  is recoverable. Lets users explore alternative directions without
  losing the original conversation.

---
## [2.66.97] — 2026-05-02

### Added
- ✏️ **Edit user message + resubmit in lazyclaw chat** (QQ22, OpenClaw
  parity). Hovering a user message now exposes a ✏️ button. Click →
  history is truncated at that index and the original text is
  pre-filled in the composer; user revises and Enter resubmits. Pairs
  with the existing 🔄 regenerate on assistant messages.

---
## [2.66.96] — 2026-05-02

### Added
- 📌 **Pin status panel in inspector** (QQ21). Selected pinned nodes
  now expose an amber expandable panel showing pinned content
  (preview, char count, unpin button) directly in the inspector — no
  longer hidden behind right-click. Discoverability fix for QQ20.

---
## [2.66.95] — 2026-05-02

### Added
- 📌 **Pin Data on workflow nodes** (QQ20, n8n signature feature).
  Right-click any session/subagent node with a recorded last output
  and choose `📌 마지막 출력 핀 설정`. Subsequent runs short-circuit
  inside `_execute_node` — the pinned text is returned immediately
  with `provider="pinned"` and zero cost/tokens, no LLM call. Lets
  users freeze an expensive upstream result and iterate downstream
  nodes for free. Pinned nodes show an amber 📌 badge on the canvas.
  Persisted via `data.pinned` + `data.pinnedOutput` (32 KB cap).

---
## [2.66.94] — 2026-05-02

### Added
- ▶📋 **Canvas right-click: Run-alone + Copy output** (QQ19, n8n parity).
  The node context menu now exposes `▶ 단독 실행` (only for
  session/subagent — reuses QQ18 endpoint) and `📋 출력 복사` (only
  visible when the node has a recorded last output, copies the raw
  `output`/`error` to clipboard). Faster debug loop without opening
  the inspector.

---
## [2.66.93] — 2026-05-02

### Added
- ▶ **Single-node execution in workflow inspector** (QQ18, n8n parity).
  When a `session`/`subagent` node is selected, the inspector now shows
  a `▶ 단독 실행` button next to `편집`. Clicking it POSTs to the new
  `/api/workflows/run-node` endpoint, which executes that one node in
  isolation (no upstream collection, no downstream propagation) and
  returns the raw provider response. Result is shown in a modal with
  provider/model/duration/tokens/cost chips and a copy button. Mirrors
  n8n's "Execute Node" debug feature — lets users iterate on a single
  prompt without re-running the whole DAG. Server-side reuses
  `_execute_node` with a synthetic `single-<hex>` run id so the
  cancellable-subprocess registry still applies.

---
## [2.66.92] — 2026-05-02

### Added
- ⏱ **Per-command elapsed time in the lazyclaw terminal** (QQ17).
  `api_lazyclaw_term` now returns `durationMs`; client appends
  `(123ms)` to the output line. Useful for spotting slow CLI
  invocations (claude cold start, ollama list scan).

---
## [2.66.91] — 2026-05-02

### Added
- ⭐ **Starred-only filter in chat search** (QQ16). The search
  modal gets a `⭐` checkbox; toggling it restricts results to
  starred messages. Result rows now also display the ⭐ icon
  on starred hits.

---
## [2.66.90] — 2026-05-02

### Added
- ⭐ **Star toggle on chat messages** (QQ15). Click the
  ☆/⭐ button next to copy/regenerate to mark a message as
  starred — visualised with an amber outer ring on the
  bubble. State (`m.starred`) persists with the message so
  it travels through export and search.

---
## [2.66.89] — 2026-05-02

### Added
- 🔢 **Live char + approximate-token count** under the chat
  textarea (QQ14). Approximation is `chars / 3` — coarse but
  good enough for both English and CJK so the user has an
  early-warning before hitting context-window limits.

---
## [2.66.88] — 2026-05-02

### Added
- 🖱 **Empty-canvas right-click context menu** (QQ13). Quick
  actions when nothing is selected:
  - ＋ 새 노드 추가 · 📋 붙여넣기 (greyed when clipboard empty)
  - 🎯 화면 맞춤 · ⊞ 격자 표시 · 📋 인스펙터 토글
  Mirrors n8n's right-click background menu.

---
## [2.66.87] — 2026-05-02

### Added
- 🔠 **Tab autocomplete in the lazyclaw terminal** (QQ12). Press
  `Tab` against the whitelist; single match auto-completes,
  multiple candidates print as a hint line so the user can
  narrow further.

---
## [2.66.86] — 2026-05-02

### Added
- ⊞ **Canvas dot-grid toggle** (QQ11). New `⊞` button in the
  bottom-right floating cluster toggles a subtle 20px-step
  dot grid behind the workflow canvas — visual guide for the
  10px node-snap step. Preference persisted in localStorage.

---
## [2.66.85] — 2026-05-02

### Fixed
- 🛎 **De-duplicated workflow completion notifications** (QQ10).
  Previously the browser notification + result modal could each
  fire on every SSE poll while the run was already terminal,
  spamming the user. Now sentinel `__wf._lastCompletedRunId`
  guarantees one fire per run id.
- 📋 **Fail-fast summary toast on err** (QQ10). When a run ends
  in `err` and at least one node was sibling-cancelled, an
  inline toast surfaces the breakdown:
  `🔴 N 실제 실패 · ⏹ M 자동 취소됨 · ✓ K 완료`.

---
## [2.66.84] — 2026-05-02

### Added
- 🔍 **Chat session filter** input above the sidebar list (QQ9).
  Live-matches session label / preview / assignee.
- 🖱 **Right-click on a chat session** opens a context menu:
  - ✏️ Rename
  - 📌 / 📍 Pin / Unpin (pinned sessions float to the top)
  - 🗑 Delete (also wipes the session's history payload)

---
## [2.66.83] — 2026-05-02

### Added
- 📌 **Floating description tag in canvas top-left** (QQ8).
  Shows `name` + truncated `description` so the user remembers
  the workflow's purpose without opening the inspector. Click
  jumps to the inspector's description textarea for editing.

---
## [2.66.82] — 2026-05-02

### Changed
- 🔗 **Auto-place + auto-wire on new node spawn** (QQ7, n8n parity).
  When a node is selected and the user adds a new one, the new
  node lands +260px to the right at the same Y, and an edge is
  drawn from the selected node automatically. Branch nodes use
  the `out_y` port; `start` / `output` types skip auto-wire.

---
## [2.66.81] — 2026-05-02

### Added
- ⌨ **Bash-style history navigation in the terminal** (QQ6).
  - `↑` / `↓` walk through prior commands; in-flight draft is
    preserved when you hit `↑` and restored when you scroll
    past the bottom of the stack with `↓`.
  - `Ctrl+R` opens a reverse-i-search popup that live-filters
    history; `Enter` picks the top match.

---
## [2.66.80] — 2026-05-02

### Changed
- ⏸ **Explicit `⏸` badge on disabled workflow nodes** (QQ5).
  Previously the only cue was opacity + grayscale + dashed
  border — easy to miss on dark backgrounds. Now a small
  gray-white pill in the top-right corner shows up whenever
  `.wf-disabled` is on the node.

---
## [2.66.79] — 2026-05-02

### Added
- 🩺 **Auto health-check on terminal tab open** (QQ4). Once an
  hour, the first visit auto-runs `claude --version`, `ollama list`,
  `gemini --version`, `codex --version`, and `git status -sb` so
  the user immediately sees provider state.
- 📜 **Whitelist expanded**: `uptime`, `df -h`, `docker --version /
  ps / images`, `uname -a / -s / -m`, `git diff --stat`,
  `git diff --cached --stat`, `git status -sb`,
  `git log --oneline -20`, `which docker`. `echo` explicitly
  rejected. Validation tightened so an empty arg-prefix list also
  bounces.

---
## [2.66.78] — 2026-05-02

### Added
- 📝 **Per-node note field** (QQ3, n8n parity).
  - Inspector now has a collapsible 📝 메모 textarea (≤ 4000
    chars) beneath each node's edit/delete buttons. Persists
    with the workflow.
  - Hover tooltip on the canvas surfaces the note (amber 📝
    line) so the user remembers a node's purpose without
    opening it.
  - Server `_sanitize_node` preserves `disabled` (PP2) and
    `notes` (QQ3) across **every** node type.

---
## [2.66.77] — 2026-05-02

### Added
- ⌨ **터미널 tab in LazyClaw mode** — whitelisted read-only
  commands so the user can check CLI / provider state without
  opening a real Terminal (QQ2). Examples:
  `claude --version`, `claude config list`, `claude config get <key>`,
  `ollama list`, `ollama ps`, `gemini --version`, `codex --version`,
  `lazyclaude status`, `git status`, `git log -5`, `which …`,
  `node --version`, `python3 --version`. Shell metacharacters
  rejected. 15 s timeout. Write commands (`config set`, install,
  login) intentionally blocked — use the Settings tab.
- 📋 Server endpoint `POST /api/lazyclaw/term` enforces the
  whitelist and runs the matched binary via `subprocess.run`
  (stdin DEVNULL, output truncated to 32 KB stdout / 8 KB stderr).
- ⌨ History recall (Up arrow on empty input), command echo
  with green `$`, mac-term-style log pane.

---
## [2.66.76] — 2026-05-02

### Added
- ⌨ **Slash commands in the LazyClaw chat input** (QQ1) — terminal-
  like settings without leaving the keyboard:
  - `/clear` — wipe history
  - `/system [text]` — set or clear the system prompt
  - `/model <provider:model>` — switch assignee inline
  - `/export` — download conversation as markdown
  - `/help` — list commands inline as an assistant message

---
## [2.66.75] — 2026-05-02

### Added
- 💵 **Live cumulative cost in the run banner** (PP5). The
  banner's meta line now shows `done/total · elapsed · $cost`
  and updates 1 Hz via the existing ticker. Skipped when no
  provider in the run reports cost (free-tier / local Ollama).

---
## [2.66.74] — 2026-05-02

### Added
- ⏱ **Per-workflow node timeout** override (PP4). Slider in
  the inspector's policy section adjusts `policy.nodeTimeout`
  (0–600 s; 0 = server default, currently 180 s). Plumbed
  through `_run_one_iteration → _execute_node → execute_with_assignee`.
  Useful for graphs with quick OpenAI/Gemini API calls (drop
  to 60 s for snappier fail-fast) or for graphs that legitimately
  need long Claude reasoning (raise to 600 s).

---
## [2.66.73] — 2026-05-02

### Changed
- 📖 **`D` shortcut now visible in `?` help** (PP3).
- ⏸ **Inspector got a quick "비활성" checkbox** next to the
  edit / delete buttons so users who don't know the shortcut
  can still toggle disable from the side panel.

---
## [2.66.72] — 2026-05-02

### Added
- ⏸ **Disable / enable nodes** without deleting them (PP2,
  n8n parity).
  - `D` key on the workflow canvas toggles `data.disabled` for
    the selected node. Same in the right-click context menu.
  - Disabled nodes render at half opacity with grayscale +
    dashed border so the user sees them in context.
  - Server-side, `_run_one_iteration` skips them with
    `status='skipped'` — no subprocess fired, no cost incurred.

---
## [2.66.71] — 2026-05-02

### Added
- 📎 **Drag-and-drop text/code files into the chat input** (OO7).
  Drop a `.md` / `.json` / `.py` / `.tsx` / etc. and the contents
  appear as a fenced code block in the textarea (with a comment
  line `// <filename> · <bytes>B`). Multiple files OK; binary
  files are skipped with a warning toast.

---
## [2.66.70] — 2026-05-02

### Changed
- 🟠 **Workflow nodes auto-cancelled by fail-fast (MM1) get an
  amber dashed border** instead of a hard red one (PP1).
  `data-status="cancelled"` is mapped client-side from
  `(status='err' && error contains 'cancelled by sibling-node failure')`.
  Real failures keep the red border. Same red/amber distinction
  as the run-result modal (NN1) and the active sessions panel
  (NN3) — now also on the canvas itself.

---
## [2.66.69] — 2026-05-02

### Added
- 🔎 **Chat history full-text search** (OO6, Cmd/Ctrl+K).
  Walks every `cc.lazyclawChat.history.*` localStorage key,
  matches against the query, surfaces hits in a modal with
  snippet + role icon + assignee label. Clicking a hit
  switches the active assignee, scrolls the matching message
  into view, and flashes its border for 1.4 s.

---
## [2.66.68] — 2026-05-02

### Added
- 🔄 **Regenerate assistant reply with another model** (OO5).
  Hovering an assistant message exposes a `🔄` button that opens
  a provider:model picker; selecting one drops the old reply and
  re-sends the original user message under the new assignee.
  Lightweight side-by-side comparison without leaving the chat.

---
## [2.66.67] — 2026-05-02

### Added
- ⚙ **System prompt input** for the chat tab (OO4). Toggle via
  `⚙ 시스템` button; 3-line textarea above the conversation log;
  value persists per-assignee in localStorage. Sent to the
  server as `systemPrompt` and prepended to the prompt as a
  `[System instructions: …]` line.
- ⏹ **Cancel-mid-stream** (OO4). The `📨 전송` button flips to a
  red `■ 중단` while a stream is in flight. Clicking it aborts
  the `fetch` (`AbortController`); the partial response is
  preserved and a `⏹ 사용자가 중단함` line is appended.

---
## [2.66.66] — 2026-05-02

### Added
- 🌊 **Streaming chat response** for Claude assignees (OO3).
  `POST /api/lazyclaw/chat/stream` runs `claude-cli` with
  `--output-format stream-json --include-partial-messages`,
  parses `content_block_delta` lines, and relays them as SSE
  `token` events. Client uses `fetch + ReadableStream` to mutate
  the assistant message in-place, throttled to 30Hz so heavy
  streams don't thrash the DOM.
- 🪝 Non-Claude providers fall through to the one-shot
  `/api/lazyclaw/chat` endpoint and emit a single `token` event
  so the UI path stays uniform.

---
## [2.66.65] — 2026-05-02

### Added (LazyClaw 채팅 polish)
- 📝 **Markdown rendering for AI replies** (OO2). Code blocks,
  lists, tables, headings render properly via `marked`. User
  messages stay verbatim to preserve copy-paste fidelity.
- 📋 **Per-message copy button** in the chat log header.
- 📥 **Export conversation as markdown** (`📥 내보내기` button).
  Filename pattern: `lazyclaw-chat-<assignee>-<timestamp>.md`.

---
## [2.66.64] — 2026-05-02

### Added
- 💬 **AI 채팅 tab** in LazyClaw mode (OO1). Direct conversation
  with any registered AI provider (Claude / OpenAI / Gemini /
  Ollama / Codex / etc) — `n8n`-style "playground" with provider:model
  dropdown, per-assignee conversation history (persisted in
  localStorage, last 100 messages), Enter-to-send / Shift+Enter
  newline. Backend `/api/lazyclaw/chat` reuses
  `execute_with_assignee` so the entire FF1 fallback chain + MM1
  fail-fast plumbing applies here too.

---
## [2.66.63] — 2026-05-02

### Added
- 📋 **Fail-fast summary card at the top of the run-result modal**
  (NN4). Counts how many nodes auto-cancelled (amber) vs. failed
  for real (red), with a one-line hint that auto-cancelled nodes
  aren't the cause — the user knows to fix the red one first.

---
## [2.66.62] — 2026-05-02

### Changed
- 🎨 **Active sessions panel uses amber for auto-cancelled rows**
  (NN3). Sibling-cancelled nodes (MM1) now show
  `⏹ 형제 노드 실패로 자동 취소됨` in amber, matching the
  run-result modal's distinction. Real errors keep `⚠` red.

---
## [2.66.61] — 2026-05-02

### Changed
- ⏹ **Sibling-cancelled nodes shown distinct from real errors**
  (NN1). Result-modal cards for nodes whose subprocess was
  SIGTERM'd by MM1's fail-fast now show `(자동 취소됨)` in amber
  with `⏹ 형제 노드 실패로 자동 취소됨` instead of the red
  `⚠ cancelled by sibling-node failure`. The "switch provider"
  UI is suppressed on these — they weren't the real failure.

---
## [2.66.60] — 2026-05-02

### Added
- 📂 **Multi-Claude session reuse picker** in the workflow node
  inspector (CC5). Next to the `session_id 직접 입력` field is a
  `📂 최근` button that opens a modal listing the 30 most recent
  Claude sessions (project, started-ago, first-prompt preview).
  One click writes the session_id back into the draft so the node
  resumes that conversation instead of spawning a fresh one. The
  per-node Active-Sessions panel from DD2 already shows live
  in-flight sessions; this closes the gap for picking historical
  ones.

---
## [2.66.59] — 2026-05-02

### Fixed
- 🛑🛑 **Fail-fast actually fast now** (MM2). MM1 in v2.66.58
  added `SIGTERM` of sibling subprocesses on first error, but the
  outer `with ThreadPoolExecutor:` context still blocked on the
  in-flight thread — the thread's provider would `cancelled by
  sibling failure` retry through fallback chain, taking 60-90s.
  Switched to a manual `pool.shutdown(wait=False, cancel_futures=True)`
  so `_run_one_iteration` returns the moment the err is detected.
  **Measured: 89s → 0.01s** (≈10000× faster) on a 2-node parallel
  level where one fails immediately and the sibling was hanging.

---
## [2.66.58] — 2026-05-02

### Fixed
- 🛑 **Workflow fail-fast: any node fail = whole-run stop** (MM1).
  Previously, when one node in a parallel topological level failed
  (e.g. GPT 401), sibling nodes (Claude / Gemini CLIs) kept hanging
  for their own 60–300s subprocess timeout — the user saw `Claude
  1024s ⏱` ticking forever while GPT was already red. Three-layer
  fix:
  1. New `_PROC_REGISTRY` keyed by `runId` in `workflows.py` —
     every CLI provider's live `Popen` is registered there.
  2. `_run_one_iteration` calls `_terminate_run_procs(runId)` the
     instant a sibling node returns `status='err'`. Sibling
     subprocesses get `SIGTERM` (then `SIGKILL` after 2s).
  3. Providers (`ClaudeCli`, `GeminiCli`, `Codex`) switched from
     `subprocess.run` to `Popen + communicate(timeout)` via a new
     `_run_cancellable` helper. A signal-killed process is reported
     as `cancelled by sibling-node failure` instead of timeout.

---
## [2.66.57] — 2026-05-02

### Added
- 💾 **Workflow autosave (debounced 30s)** (LL28). Whenever the
  user marks the workflow dirty, an autosave timer is scheduled
  30 seconds out; further edits reset the timer so we never save
  mid-typing. Explicit `Cmd+S` cancels any pending autosave.
  The "저장됨" toast is suppressed for autosaves — instead the
  toolbar dirty indicator's tooltip records the timestamp
  (`자동 저장됨 · HH:MM:SS`) so the user can see it happened
  without being interrupted.

---
## [2.66.56] — 2026-05-02

### Added
- ⌨ **`Cmd/Ctrl + [` and `Cmd/Ctrl + ]` cycle workflows**
  (LL27, n8n parity for editor tab switching). Previous /
  next entry in the sidebar list. Wraps. Skipped when only
  one workflow exists.

---
## [2.66.55] — 2026-05-02

### Changed
- 🔍 **Workflow list search uses fuzzy matching** (LL26).
  Same subsequence + substring algorithm as the canvas node
  search. CJK falls back to substring.

---
## [2.66.54] — 2026-05-02

### Changed
- 🔍 **Node search input gets a clear button + Esc support**
  (LL25). Placeholder text now hints at fuzzy syntax
  (`예: fy / ses`). The `×` button shows up only when a
  query is active; pressing `Esc` inside the field also clears.

---
## [2.66.53] — 2026-05-02

### Changed
- 🔍 **Node search uses fuzzy matching** (LL24, n8n parity).
  Subsequence match + substring across title / type / label /
  assignee / agentRole. Typing "fy" highlights "frontend",
  "ses" highlights "session". Korean / Chinese queries fall
  back to substring (subsequence is meaningless for CJK).

---
## [2.66.52] — 2026-05-02

### Added
- ↔ **Inspector panel resize handle** (LL23, n8n parity). Drag
  the left edge of the inspector to resize between 240–720px.
  Width persists in localStorage so it sticks across sessions.

---
## [2.66.51] — 2026-05-02

### Added
- 🗺 **Minimap drag-to-pan** (LL22, n8n parity). Hold the mouse on
  the minimap and the canvas viewport follows the cursor smoothly,
  not just on click.

---
## [2.66.50] — 2026-05-02

### Added
- 📖 **Help modal lists mouse actions** (LL21). Right-click for
  node/edge context menus and minimap-click to pan are now
  discoverable from the `?` shortcut help on the workflow tab.

---
## [2.66.49] — 2026-05-02

### Added
- 🖱 **Right-click on an edge → Delete option** (LL20). The
  existing node context menu is now reused; right-clicking
  on an edge path selects it and offers Delete (`⌫`).

---
## [2.66.48] — 2026-05-02

### Added
- 🗺 **Click on the minimap pans the canvas** to that location
  (LL19, n8n parity). Inverse minimap→world transform — useful
  on large workflows where you need to jump to a specific area
  without dragging the canvas across the viewport.

---
## [2.66.47] — 2026-05-02

### Fixed
- 🔢 **Zoom-cluster label syncs with the actual viewport** on
  canvas mount and after fit-to-screen (LL18). Was hardcoded to
  100%; now reflects real zoom (e.g. 78% after a fit on a wide
  workflow).

---
## [2.66.46] — 2026-05-02

### Added
- 🔍 **n8n-style floating zoom cluster** in the canvas bottom-right
  (LL17). `−` zoom out, current % (click to reset to 100%), `+`
  zoom in. Always visible — the user no longer needs to remember
  `Cmd+0` / `Cmd+1` to recover from a stray pinch. Label updates
  live during wheel zoom too.

---
## [2.66.45] — 2026-05-02

### Added
- ➕ **`Cmd/Ctrl + N` opens the new-node editor** (LL16). Lets
  users add a node without reaching for the toolbar button.
  Browser may intercept `Cmd+N` for a new window in some
  contexts; on the workflows tab the in-app handler wins.

---
## [2.66.44] — 2026-05-02

### Added
- 🛡 **beforeunload guard for unsaved workflow changes** (LL15,
  n8n parity). When the workflow has dirty edits and the user
  reloads or closes the tab, the browser shows its native
  "Changes you made may not be saved" prompt. Saving (Cmd+S)
  clears the dirty flag and the prompt is skipped on next exit.

---
## [2.66.43] — 2026-05-02

### Added
- 🖱 **Right-click on a node opens a context menu** (LL14, n8n
  parity). Edit / Duplicate / Delete with keyboard shortcuts
  shown alongside. Auto-positions to stay inside the viewport;
  closes on outside-click or Esc.

---
## [2.66.42] — 2026-05-02

### Added
- ▶ **`Cmd/Ctrl + Enter` runs the workflow** (or cancels it if
  already running) (LL13, n8n parity). Avoids the browser-reload
  conflict of `Cmd+R`. Uses the existing `_wfRunOrCancel` toggle
  so the same key starts and stops a run.

---
## [2.66.41] — 2026-05-02

### Added
- ⌨ **`Cmd/Ctrl + E` (or `Enter`) opens the editor** for the
  selected node (LL12). Closes the keyboard navigation loop:
  Tab to land on a node, Cmd+E to edit its content, Esc to close.

---
## [2.66.40] — 2026-05-02

### Added
- ⌨ **`Tab` / `Shift+Tab` cycle through nodes** (LL11). Combined
  with arrow-key nudging this gives full keyboard-only canvas
  navigation: Tab to land on a node, arrows to move it, Cmd+D
  to duplicate.

---
## [2.66.39] — 2026-05-02

### Added
- 🗺 **`Cmd/Ctrl + M` toggles the minimap** (LL10). Choice
  persists in localStorage so users who don't want the floating
  minimap don't have to re-hide it every session.

---
## [2.66.38] — 2026-05-02

### Added
- 📖 **Shortcut help modal updated** with the 14 new keybindings
  added in v2.66.20–v2.66.37 (LL9). Press `?` on the workflow
  canvas to discover them. Includes Ctrl+D, Ctrl+A, Ctrl+I,
  zoom shortcuts, arrow nudges, Shift+L auto-layout, perf HUD,
  Wheel pan, Cmd+Wheel zoom, Alt+drag, dblclick fit.

---
## [2.66.37] — 2026-05-02

### Added
- 🪄 **`Shift + L` auto-layout** (LL8). Runs the existing
  Beautify routine without the fit-to-screen step, so the
  topology snaps into clean alignment while the user keeps
  their current pan/zoom.

---
## [2.66.36] — 2026-05-02

### Added
- 📋 **`Cmd/Ctrl + I` toggles the inspector side panel** (LL7). Lets
  the user reclaim full canvas width without reaching for the toolbar
  button.

---
## [2.66.35] — 2026-05-02

### Added
- 🎯 **`Cmd/Ctrl + A` selects every node** in the active workflow
  (LL6, n8n parity). Populates the existing multi-select set so
  `Cmd+C`, `Delete`, and the arrow-key nudge all operate on the
  whole graph at once.

---
## [2.66.34] — 2026-05-02

### Added
- 📑 **`Cmd/Ctrl + D` duplicates the selected node** (LL5, n8n parity).
  Cloned at +40px offset; the new node becomes the selection so a
  user can immediately drag it into place or edit.

---
## [2.66.33] — 2026-05-02

### Added
- ⌨ **Arrow-key node nudging** on the workflow canvas (LL4, n8n parity):
  - `←/→/↑/↓` — move selected node by 10 px (matches the new grid step)
  - `Shift + arrow` — fine 1 px adjust

---
## [2.66.32] — 2026-05-02

### Added
- 🧲 **Node-drag grid snap** (LL3, n8n parity). Drop position now
  rounds to the nearest 10px so manually-arranged workflows look
  tidy without nudging pixel-by-pixel. **Hold `Alt`** while dragging
  to bypass and place freely.

---
## [2.66.31] — 2026-05-02

### Added
- 📊 **Perf HUD** — `Cmd/Ctrl + Shift + P` toggles a corner overlay
  showing live FPS, the longest main-thread task in the previous
  second, and total long-task time per second (LL2). Lets the user
  confirm at a glance whether a perceived lag is the dashboard,
  a browser extension, or system load. State persists across
  reloads via localStorage.

---
## [2.66.30] — 2026-05-02

### Performance
- ⚡ **Toolbar update batched to 1× per frame** (LL1). The
  workflow toolbar (`name`, `dirty` indicator, undo depth) was
  refreshed synchronously on every inspector input — 60+ writes
  per second when the user is typing into a textarea. Now coalesced
  via `requestAnimationFrame` to one write per paint frame.

---
## [2.66.29] — 2026-05-02

### Performance
- 🪪 **`/app.js` now versioned + immutable** (KK2). `_send_static`
  rewrites the `<script src="/app.js">` reference in `index.html`
  to `<script src="/app.js?v=<mtime>">`, and any URL with `?v=`
  gets `Cache-Control: public, max-age=31536000, immutable`.
  After the first load, the browser serves `app.js` from disk cache
  without even a 304 round-trip — the URL itself changes whenever
  app.js does, so staleness is impossible.

---
## [2.66.28] — 2026-05-02

### Fixed
- 🤏 **Trackpad pinch-zoom dampening** (KK1). macOS reports trackpad
  pinches as a high-frequency stream of `ctrlKey + wheel` events with
  very small `deltaY`, which the user perceives as "the canvas keeps
  zooming out by itself". Three fixes:
  1. **Drop sub-noise events** — `|deltaY| < 1.5` is ignored entirely.
  2. **Halve zoom sensitivity** — `0.0015 → 0.0008` per delta unit.
     A deliberate pinch still zooms; stray contact doesn't visibly
     move the view.
  3. **Raise minimum zoom** — `0.3 → 0.5`. Below 0.5 the canvas was
     unusable and required `Cmd+0` to recover.

---
## [2.66.27] — 2026-05-02

### Added
- ⌨ **n8n-style zoom shortcuts** on the workflow canvas (JJ2):
  - `Cmd/Ctrl + 0` → fit to screen
  - `Cmd/Ctrl + 1` → 100% (reset to identity transform)
  - `Cmd/Ctrl + +/=` → zoom in 15%
  - `Cmd/Ctrl + -` → zoom out 15%
  - **Empty-canvas double-click → fit to screen**
- One-motion recovery from a stray trackpad pinch or accidental
  wheel zoom that left the canvas at an unreadable scale.

---
## [2.66.26] — 2026-05-02

### Performance
- 🎨 **CSS `contain: layout paint` on `.wf-node`** (JJ1). Each
  workflow node becomes its own paint/layout boundary — per-node
  attribute mutations (data-status, transform, .wf-node-elapsed
  text) no longer trigger relayout cascades across siblings.
  Significant on 20+ node graphs during a live run; harmless on
  small ones.
- 🌒 **Elapsed-time ticker skips ticking when `document.hidden`**
  (JJ1). The browser already throttles `setInterval` in background
  tabs, but an explicit guard avoids any DOM mutation on an
  offscreen canvas. Resumes naturally when the user returns.

---
## [2.66.25] — 2026-05-02

### Fixed
- 🧹 **Workflow tab background activity leak** (II2). Leaving the tab
  while a run was in flight kept SSE, the elapsed-time ticker, and the
  poll fallback running in the background — they kept fetching
  `/api/workflows/run-status` and DOM-mutating an invisible tab. The
  hashchange handler now closes them when `state.view` transitions
  away from `workflows`. Auto-restore re-attaches when the user
  returns. Same pattern was already in place for the Ralph tab.

---
## [2.66.24] — 2026-05-02

### Performance — split the bundle
- 🏗 **Inline `<script>` (1.2MB / ~25K lines) extracted to `/app.js`**
  (II1). The HTML body is now 178KB instead of 1.4MB; the browser
  finishes parsing the document an order of magnitude sooner and the
  app code arrives in parallel. The first inline block (lazy-loader,
  ~800 bytes) stays inline because `app.js` depends on it via
  `window._loadVendor`.

### Measured (Playwright on workflow tab)
| Metric | v2.66.18 | v2.66.24 | Cumulative |
|---|---|---|---|
| DOMContentLoaded | 823 ms | **59 ms** | **−93%** |
| networkidle | 2947 ms | **1427 ms** | −52% |
| index.html bytes | 1.6 MB | **178 KB** | −89% |
| inline JS bytes | 1.2 MB | **827 bytes** | −99.9% |
| Long tasks | 234 ms | **0** | — |

Single-file deployment is preserved — `dist/app.js` ships in the
same dist/ directory and the existing static-serving path picks it
up. No build step added.

---
## [2.66.23] — 2026-05-02

### Performance
- 🔒 **`/vendor/*` served with `Cache-Control: public, max-age=31536000,
  immutable`** (HH4). The dashboard ships its own copies of Chart.js,
  vis-network, marked, Tailwind CSS, and Pretendard, so URLs only ever
  change on a code update. Marking them immutable means the browser
  skips even the 304 revalidation round-trip on subsequent loads.
  Effective only after one warm load — first visit unchanged.

---
## [2.66.22] — 2026-05-02

### Performance — first-paint
- 🎨 **Pretendard + JetBrains Mono now load non-blocking** (HH3).
  Stylesheets switched to `media="print" onload="this.media='all'"`
  with a paired `preload` and a `<noscript>` fallback. The browser
  paints with the system font fallback (`-apple-system, ...`) the
  instant the layout is ready, and swaps to the web font once the
  CSS is parsed.

### Measured (Playwright on workflow tab)
| Metric | v2.66.18 | v2.66.22 | Δ |
|---|---|---|---|
| DOMContentLoaded | 823 ms | **146 ms** | −82% |
| networkidle | 2947 ms | **1730 ms** | −41% |
| load event | — | **281 ms** | — |
| Long tasks (>50ms) | 234 ms | **none** | — |

---
## [2.66.21] — 2026-05-02

### Performance
- 📦 **Lazy-load 894KB of vendor JS** that the workflow tab never
  needs (HH2):
  - `vis-network` (689KB) — only loaded when Mind-Map / Project-Agents
    / Session-Timeline graphs are opened. Three call sites guarded
    with `await window._loadVendor('vis')`.
  - `chart.js` (205KB) — only loaded on first `_renderChart` call
    (now async).
  - `marked` (35KB) stays page-boot defer because it's used inside
    template strings without an `await` boundary.
  - Net effect: a workflow run no longer pays the parse cost of a
    graph library it never invokes.
- 🖱 **RAF-throttled edge-draft renderer** during edge drag.
  `_wfDraftRender` was being called on every `mousemove` (60–120 Hz)
  and replacing `innerHTML`. Now coalesced to once per frame and
  patches the path's `d` attribute on a cached `<path>` element.
- 📊 Measured Long-Task budget on workflow tab: 71 ms → **54 ms**
  (-24%) on top of v2.66.19's already-improved baseline.

---
## [2.66.20] — 2026-05-02

### Fixed
- 🩹 **Workflow tab kept "auto-zooming-out"** because every wheel
  event — including normal trackpad two-finger scrolling — multiplied
  zoom by 0.9. Replaced with **n8n-style controls** (HH1):
  - `Ctrl/Cmd + wheel` → zoom (cursor-anchored, exponential to deltaY
    so trackpads no longer leap 10% per micro-event).
  - plain `wheel` → pan; `Shift + wheel` swaps axes.
- 🩹 **Reopening a completed workflow snapped back to "실행 중"**
  with a fresh polling subscription (the source of "클릭하면 갑자기
  실행중으로 바뀌면서 렉이 급증" symptom). The auto-restore now
  fetches `run-status` once and only attaches polling if the server
  still says `running`. The server itself now **self-heals zombie
  runs in `_run_status_snapshot`**: when cache.status='running' but
  every node has reached a terminal state, promote to ok/err and
  drop the cache entry. Idempotent.

---
## [2.66.19] — 2026-05-02

### Performance — workflow tab feels lag-free
- 🚀 **Replaced cdn.tailwindcss.com (1MB JIT runtime that re-compiles
  CSS on every DOM mutation) with a pre-built 26KB stylesheet** at
  `dist/vendor/tailwind.css`. This is the single largest win — Tailwind
  Play CDN runs the entire compiler in the browser, scanning every DOM
  change and emitting CSS, which dominates main-thread time during a
  workflow run.
- 📦 **Self-hosted chart.js / vis-network / marked** under
  `dist/vendor/`. No more cross-origin DNS lookups on every page load,
  works offline, survives CDN failures.
- 📊 Measured (Playwright):
  - DOMContentLoaded: 823 ms → **405 ms (−51%)**
  - networkidle:      2947 ms → **2403 ms (−18%)**
  - Long tasks (>50ms): 172+62 ms → **67 ms** (¼ of before)

### Added
- ⏹ **Per-node session terminate button** on the active sessions panel
  (GG1). Red ⏹ next to running rows; confirms with a dialog and POSTs
  `/api/workflows/run-cancel` to halt the run at the next level
  boundary. Per-image user feedback.

---
## [2.66.18] — 2026-05-02

### Fixed
- 🩹 **Run banner stuck at 100% / "실행 중"** even after every node
  reached a terminal status (FF3). Triple-layer fix:
  1. **Server SQLite contention** — `_db()` now opens with
     `timeout=10.0` and `PRAGMA busy_timeout=10000`, so a write lock
     held by the session-indexer thread can't deadlock the
     post-run cost write that gates `_mark_done`.
  2. **Frontend defensive auto-promote** — when every workflow node
     has a terminal status (ok/err/skipped) but `run.status` is still
     `running`, the client now flips the banner to `완료/실패` itself,
     stops polling, and resets the run button.
  3. **Manual recovery endpoint** — `POST /api/workflows/run-force-finish`
     marks any in-cache run as ok/err based on its node results, so
     stuck runs can be cleared without restarting the server.

---
## [2.66.17] — 2026-05-02

### Fixed
- 🛠 **`node n-fe: all providers failed` actually fixed end-to-end** —
  team-dev workflow now completes (verified `ok: True` for every node)
  even when claude-cli sonnet hangs. Six independent issues stacked on
  top of each other; this release fixes them all (FF1).
  1. **claude-cli `--model claude-sonnet-4-6` deterministically hangs**
     (Anthropic backend). Same call with `--model sonnet` (alias)
     completes in ~30 s. Fix: `ClaudeCliProvider._resolve_model` now maps
     full model names back to CLI-friendly aliases.
  2. **Subprocess hang on stdin** — added `stdin=subprocess.DEVNULL` so
     claude-cli never waits for tty input even with `-p`.
  3. **Default node timeout 300 s wastes user time** — reduced to 180 s,
     and split into ≤4 retries of 60 s each, killing the hung process
     between attempts.
  4. **Wasted timeout on in-family swap during a hang** — when the
     primary error is a timeout (vs. a transient rate-limit), skip the
     opus → haiku → sonnet model dance and jump straight to the
     cross-provider chain. Saves up to 6 minutes per failed node.
  5. **Cross-provider fallback passed the wrong model** (e.g. asked
     ollama to run `gemini-2.5-flash` → 404). Now the model field is
     reset to empty when crossing providers, so each picks its own
     default.
  6. **Codex CLI `-q` flag removed upstream** → `exit 1: unexpected
     argument '-q'`. Switched to the new `codex exec [PROMPT]` form.
- 🔁 **Default fallback chain extended**: `claude-cli → anthropic-api →
  openai-api → gemini-api → gemini-cli → codex → ollama`. Local Ollama
  ensures a workflow always has *something* that can answer when API
  keys are missing and CLIs hang.

---
## [2.66.16] — 2026-05-02

### Investigation
- 🔎 Reproduced the user-reported `node n-fe: all providers failed` against
  the saved "팀 개발 스프린트" workflow. Root cause: `claude-cli` and
  `gemini-cli` both hung past the 300 s subprocess timeout for the parallel
  `subagent` level, with no API-key fallback configured. The CC4
  improvement to the error message is now visible end-to-end:
  `all providers failed — primary: timeout after 300s || chain: ...`.

### Added
- 🔄 **Switch-provider recovery in the run-result modal** (EE2). Each
  failed `session` / `subagent` row now shows a "프로바이더 변경" select
  populated from `/api/ai-providers/list` (only available providers). One
  click saves the new assignee back to the workflow and re-runs.
- 🛡 **Workflow preflight endpoint** (EE1): `POST /api/workflows/preflight`
  scans every node's assignee, resolves to (provider_id, model), and
  returns the unavailable ones plus the list of available providers.
  Useful for static "no API key" cases — does not catch runtime hang.

---
## [2.66.15] — 2026-05-02

### Added
- 🪟 **Active sessions panel** on the workflow tab. Floating card lists
  every node that has run (or is running) with its assignee, status,
  short session id, and per-row actions: open inline mac-style viewer,
  copy session id, paste into another node's resume field. Toolbar
  badge shows live/total session count and turns red while ≥1 node is
  in flight. (DD2)

### Changed
- 🛑 **Stop button label clarified**: `■ 중단` → `■ 실행 중단` with a
  tooltip that explains in-flight nodes finish their current level
  before the run terminates. (DD1)

### Performance
- 🚀 **Workflow tab tick cost cut significantly**. The inspector
  side-panel was being rebuilt on every SSE/poll tick (every 0.5–1.2 s)
  even when nothing the user could see had changed. Now diffed against a
  per-selected-node signature (`status:startedAt:finishedAt`) so the
  panel only re-renders when the selected node's state actually moves.
  Same gating applied to the minimap repaint. The sessions panel skips
  innerHTML rebuild when its row signature is unchanged. (DD3)

---
## [2.66.14] — 2026-05-02

### Fixed
- 🖥 **Workflow node "screen" icon** no longer launches Terminal.app — it
  opens the inline mac-style viewer modal showing the node's prompt + the
  latest run's per-node output. A "↗ Real terminal" button keeps the old
  escape hatch one click away. (CC1)
- ⏱ **Run banner / per-node elapsed timers no longer freeze**. Previously
  the Y2 diff-render only updated when SSE pushed a status change — but
  elapsed seconds change every wall-clock second. Added an independent
  1Hz ticker that patches just the `.wfrb-meta-text` and
  `.wf-node-elapsed` text contents from cached run state. The ticker
  stops itself when the run reaches a terminal status. (CC2)
- 🧭 **Sidebar collapsed state**: the "🕒 최근 사용 / ★ 즐겨찾기" quick block
  no longer overflows the 78px rail. Headers shrink to icon-only and
  quick items center-align with single-icon presentation. (CC7)

### Added
- ⏹ **Workflow Execute / Cancel toggle** (n8n-style). The primary `▶ 실행`
  button switches to a red `■ 중단` button while a run is in flight, and
  POSTs `/api/workflows/run-cancel` to request cooperative cancellation.
  Server-side: `_run_one_iteration` checks a `_CANCEL_REQUESTED` set at
  every topological-level boundary; the run terminates with
  `status='err' / error='cancelled by user'` without yanking in-flight
  node executors. (CC3)

---
## [2.67.0] — 2026-05-02

### Fixed
- 🦞 LazyClaw mode-badge key corrected from `O` (legacy OpenClaw) to `L`.
- i18n: cleared 3 Korean residue strings in EN/ZH — "Permissions Summary",
  Settings/Permissions tab link, and email-toggle tooltip.

---
## [2.66.0] — 2026-05-02

### Changed
- 🦞 **Mode renamed: OpenClaw → LazyClaw**. Header dropdown label,
  MODE_TABS key, mode-badge tag (O→L), all UI strings. The previous
  external-product reference confused some users — "LazyClaw" matches
  the project's naming convention (LazyClaude → LazyClaw).
- localStorage keys auto-migrate on next load: `cc.mode openclaw` →
  `lazyclaw`, `cc.mode.openclaw.{lastTab,counts}` →
  `cc.mode.lazyclaw.*`. One-shot, idempotent, silent.
- README + CHANGELOG references updated.

The external **OpenClaw** product (github.com/openclaw/openclaw) is
unrelated and still referenced under that name where mentioned in
documentation (e.g. `server/guide.py`).

---
## [2.65.0] — 2026-05-02

### Added
- ⏱ System tab boot-timing card — shows time from `python3 server.py`
  to first HTTP listen. Fetched via `GET /api/system/boot-timing`.
- 🔁 Ralph run duplicate button — pre-fills the Start form with the
  configuration of any past run so the user can tweak and re-launch.

## [2.64.0] — 2026-05-02

### Added
- 🔄 Ralph tab live auto-refresh — polls `/api/ralph/list` every 3 s while
  any run is `running`; stops automatically when all runs settle.
- 🎛 Orchestrator `dispatch()` accepts `plannerAssignee`, `aggregatorAssignee`,
  and `assignees` overrides so the `/api/orchestrator/dispatch` endpoint can
  target specific models without changing the stored binding config.

## [2.63.0] — 2026-05-02

### Added
- 🗓 Orchestrator sweeper status panel — live table of scheduled bindings
  with next-fire ETA, due-now highlighting, via
  `GET /api/orchestrator/sweeper-status`.
- 💾 Auto-Resume per-UUID-prefix cwd memory (`cc.ar.cwds` localStorage,
  bounded at 32 entries) — pre-fills the cwd field on repeat binds.
- 📋 Workflow run inspector now surfaces cache-hit age, docker image, and
  Ralph run-id / iter / cost rows when the executor returns them.
- 🔍 Ralph tab status filter chips (running / done / budget / max_iter /
  cancelled / error) + free-text search across runId + assignee; default
  list limit raised from 30 → 200.

## [2.62.0] — 2026-05-02

### Added
- 🦞 Ralph Polish system prompt editor in the Ralph tab (load / save /
  revert) backed by `GET/POST /api/ralph/polish-prompt`.
- 📊 Per-mode usage stats panel in Settings dropdown — bar chart of top
  tabs per mode, per-mode reset.
- 🐳 docker_run result cache (opt-in `cache:true`) keyed on
  (image, command, env, mountPath, network, stdin) with `cacheTtlSec` TTL.
  Failures never cached.

## [2.61.0] — 2026-05-02

### Added
- Ralph Polish system prompt configurable via env / file / default.
- Per-mode last-tab memory (`cc.mode.<mode>.lastTab`).
- 🔥 badge for top-3 most-visited tabs in current mode.
- Mode-scoped spotlight (Cmd+K) + global toggle chip.
- Mode badges (C/W/P/O) in all-mode sidebar.
- Orchestrator IPC stream UI panel.

## [2.60.0] — 2026-05-02

### Added
- 🐳 `docker_run` workflow node — sandboxed shell as a workflow primitive
  with `--rm`, `--network=none`, memory cap, `--security-opt=no-new-privileges`,
  optional read-only volume mount. Missing docker → clean error,
  no host-execution fallback.

## [2.59.0] — 2026-05-02

### Changed
- ⚠️ Ollama auto-start is now **opt-in** (env `OLLAMA_AUTOSTART=1` or
  Quick-Settings `behavior.autoStartOllama=true`). Default skips silently.

### Added
- 🎚️ Top-level mode switcher (All / Claude / Workflow / Providers / LazyClaw).
  v2.66.0 renamed the mode from "OpenClaw" → "LazyClaw"; localStorage
  keys are migrated transparently on next load.
- 🔄 Auto-Resume manager add-binding modal (live session picker).
- 📊 `/api/system/boot-timing` time-to-listen observability.
- Boot path defers `_migrate_runs_to_db` to a daemon thread; orchestrator
  sweeper auto-starts at boot.

## [2.58.0] — 2026-05-01

### Added
- Orchestrator inbound/outbound SQLite IPC streams (NanoClaw single-writer
  pattern). `/api/orchestrator/inbound` + `…/outbound`.
- Recurrence sweeper — bindings with `schedule.everyMinutes` fire on a
  60-second tick.
- Ralph auto-commit on `done` when cwd is a git repo + `autoCommit:true`.

## [2.57.0] — 2026-05-01

### Added
- 🦞 Ralph UI tab + Project card recommendation modal with optional
  LLM polish.
- Email-out reply binding (`kind: "email"`) — orchestrator replies via SMTP.
- Per-agent isolated workspace at
  `~/.claude-dashboard-agents/<binding-id>/{CLAUDE.md, memory/}`.
- Workflow `ralph` node inspector form.

## [2.56.0] — 2026-05-01

### Added
- 🦞 Ralph loop engine + workflow node + CLI + project recommender
  (Geoffrey Huntley's Ralph Wiggum loop pattern as a first-class feature).
- Discord bot — outbound + ed25519-verified interactions endpoint
  (lazy `cryptography` import; missing → all webhooks refused).
- Per-binding fallback chain + 24h rolling daily budget cap (USD).

### Fixed
- Deterministic tie-break in `orch_runs ORDER BY` (rowid DESC second key).

## [2.55.x] — 2026-05-01

### Added
- 🎼 Channel orchestrator (Slack + Telegram), terminal TUI, agent bus.
- Agent bus SSE bridge + ask/reply protocol + workflow binding execution.
- Slack signing verification + orchestrator run history.
- HTTPS keep-alive pool, reply debouncer, plan LRU, per-topic index, perf bench.

---
## [2.54.0] — 2026-05-01

### 🧹 Housekeeping + 264 tests + perf regression suite

User: "다름 라운드 계속 진행." Three parallel agents on independent
domains.

### 🧹 Housekeeping (A)

| # | Where | What |
|---|---|---|
| 1 | `server/backup.py::api_backup_prune` | `{retentionDays=30, keepLast=5, dryRun=false}`. Keeps `keepLast` newest + anything younger than `retentionDays`. Safety: never leaves 0 backups. Manifest verified before unlink. |
| 2 | `server/auto_resume.py::api_auto_resume_prune_stale` | `{thresholdDays=30, dryRun=false}`. Only purges entries in terminal states (done/failed/exhausted/stopped/error) past threshold. Active states never touched. |
| 3 | `server/housekeeping.py` (NEW, ~165 lines) | Disk-usage reporter + orchestrator. `_disk_usage` walks DB + json files + backups dir + sessions dir. `api_housekeeping_report` returns combined report. `api_housekeeping_run` calls both prunes based on flags. |
| 4 | Endpoints | `GET /api/housekeeping/report`, `POST /api/housekeeping/run`, `POST /api/backup/prune`, `POST /api/auto_resume/prune-stale`. |
| 5 | `dist/index.html` `VIEWS.backupRestore` | New "🧹 정리" card below backup table. Disk-usage summary line. Two action buttons (오래된 백업 정리, 유휴 AR 바인딩 정리) with dry-run preview → confirm → real run flow. |
| 6 | `tools/translations_manual_35.py` (new) | 20 KO→EN/ZH for housekeeping strings. |

### 🧪 Pytest expansion (B)

| # | Where | Cases |
|---|---|---|
| 7 | `tests/test_backup.py` (199 lines) | 16 — list/create/delete/restore round-trip, manifest verification, path-traversal rejection, isolated_home redirection. |
| 8 | `tests/test_learner.py` (133 lines) | 12 — `api_learner_patterns` shape, SQL-driven aggregation against synthetic data. |
| 9 | `tests/test_hyper_agent.py` (233 lines) | 24 — `_empty_meta`, `_default_agent_meta`, `_coerce_agent_meta`, `_cwd_hash`, `_agent_key`, `hyper_advise_auto_resume` pre-validation + post-clamping (mocked execute_with_assignee). |
| 10 | `tests/test_briefing.py` (128 lines) | 10 — `briefing_overview`, `briefing_projects_summary`, `briefing_activity` shapes; empty DB defaults. |
| 11 | `tests/test_system.py` (185 lines) | 14 — `api_usage_summary`, `api_usage_project` cwd validation, `_running_sessions`, `api_sessions_stats` (v2.46.0 daily-timeline bug regression). |

### ⚡ Perf regression suite (C)

| # | Where | What |
|---|---|---|
| 12 | `tests/test_perf.py` (340 lines, 17 cases) | Each test sets a budget 10-100× current measured time, fails on regression. Covered: `_db_init` <5ms, `api_auto_resume_status` empty <10ms, `api_ports_list` <500ms, `_scan_plugin_hooks` warm <5ms, `_telemetry_compute` <50ms, `api_cost_recommendations` <100ms, `api_backup_list` <50ms, `_topological_levels` cached <1ms, `_runs_db_save` <20ms, cold imports (workflows <500ms, routes <1000ms, db <300ms), translation cache warm <10ms, `_exponential_backoff` 1000 calls <50ms, `_classify_exit` 1000 calls <100ms, `_safe_write` JSON <20ms. |

`shutil.which("lsof")` skipif guard for the `api_ports_list` test on hosts without lsof.

**Test totals: 171 → 264 (+93 = 17 perf + 76 module-coverage), runtime 1.80s → 2.71s.**

### Smoke
```
$ make test                                    264 passed in 2.71s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       2.6 ms
$ /api/housekeeping/report           200       1.5 ms
$ /api/backup/list                   200       0.9 ms
$ /api/auto_resume/status            200       0.9 ms
$ housekeeping report shape          ok totalBytes=2693904 backups=0 arEntries=0
```

### Cumulative tests
- v2.49.0: 0 → 26 (auto_resume)
- v2.50.0: 26 → 68 (+41 db, prefs, process_monitor)
- v2.52.0: 68 → 113 (+45 workflows, ai_providers, ccr_setup)
- v2.53.0: 113 → 171 (+58 hooks, mcp, cost_timeline, notify)
- v2.54.0: 171 → **264** (+93 backup, learner, hyper_agent, briefing, system, **+ perf regression suite**)

---
## [2.53.0] — 2026-05-01

### 💾 Backup/restore + 🔍 session search + 171 tests

User: "다음 라운드 자율모드." Three parallel agents on independent
domains.

### 💾 Backup/restore (A)

| # | Where | What |
|---|---|---|
| 1 | `server/backup.py` (new, ~280 lines, stdlib only) | tar.gz archives in `~/.claude-dashboard-backups/` containing all `*.json` data files + a sqlite-vacuumed snapshot via `VACUUM INTO`. Manifest at archive root with `{version, files, createdAt, hostname, label}`. |
| 2 | `api_backup_list` | Returns sorted-by-mtime list with `name, path, sizeBytes, createdAt, files`. |
| 3 | `api_backup_create({label?})` | Generates `lazyclaude-YYYYMMDD-HHMMSS[-label].tar.gz`. Atomic `.tmp` + rename. Backs up: `*.db`, all `~/.claude-dashboard-*.json` files (silently skip missing), `~/.claude-code-router/config.json` (flattened to `claude-code-router__config.json`). |
| 4 | `api_backup_restore({name, overwrite, files?})` | Pre-flight check rejects when target exists unless `overwrite=true`. Safe extraction (rejects `..` / absolute paths). |
| 5 | `api_backup_delete({name})` | Containment check via `Path.resolve()` parents. Manifest signature check. |
| 6 | `server/nav_catalog.py` + `dist/index.html` `VIEWS.backupRestore` | New `💾 백업 & 복원` tab under `reliability` category. Header card with backup count + new-backup form (label input). Backups table (name, createdAt, size, files, actions 📥/🗑). Confirm dialog before restore/delete. |
| 7 | `tools/translations_manual_33.py` (new) | 25 KO→EN/ZH for backup strings. |

### 🔍 Session full-text search (B)

| # | Where | What |
|---|---|---|
| 8 | `server/sessions.py::api_sessions_search` | Streams `~/.claude/projects/*/*.jsonl` line-by-line (no whole-file load). Score = occurrences + recency boost (`max(0, 30 - days_old)`). Top-200 most-recent sessions cap, ≤5 matches per session early-termination. In-memory TTL-30s cache (capacity 64). |
| 9 | Endpoint | `GET /api/sessions/search?q=...&limit=20&cwd=...` (default 20, max 100). `q < 2 chars` rejected. Returns `{ok, query, totalScanned, totalMatched, hits: [...]}`. |
| 10 | `dist/index.html` `VIEWS.sessions` | Search box at top with 300ms debounce. Hides session list while results showing. "검색 지우기" reverts. |
| 11 | `tools/translations_manual_34.py` (new) | 13 KO→EN/ZH for search strings. |

### 🧪 Pytest expansion (C)

| # | Where | Cases |
|---|---|---|
| 12 | `tests/test_hooks.py` (127 lines) | 9 — `_scan_plugin_hooks` shape, TTL-30s cache, mtime-based invalidation. |
| 13 | `tests/test_mcp.py` (158 lines) | 13 — `_load_disk_cache` idempotent, `_claude_mcp_list_cached` shape, TTL behavior. Mocks `subprocess.run`. |
| 14 | `tests/test_cost_timeline.py` (185 lines) | 20 — `_aggregate_by_model`, `_infer_provider`, all 4 recommendation rules, `api_cost_recommendations` shape. Mocks `_gather_all`. |
| 15 | `tests/test_notify.py` (128 lines) | 16 — `_send_notify({})` no-op, `send_email` empty/missing, `send_telegram` mocked URLError. Fully offline. |

**Test totals: 113 → 171 (+58), runtime 1.82s → 1.80s.**

### Smoke
```
$ make test                                    171 passed in 1.80s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       3.5 ms
$ /api/backup/list                   200       0.8 ms
$ /api/sessions/search?q=the&limit=5 200      47.0 ms (cold)
$ /api/auto_resume/status            200       0.8 ms
```

---
## [2.52.0] — 2026-04-30

### 🧠 Hyper-Advisor + 113 tests + 467× AR status

User: "다음 라운드 계속 진행." Picks up the v2.49.0-deferred Hyper-Agent
↔ Auto-Resume integration, expands test coverage by 3 modules, and
fixes the v2.51.0-flagged `/api/auto_resume/status` 327 ms regression.

### 🧠 Hyper-Agent ↔ Auto-Resume advisor (A)

| # | Where | What |
|---|---|---|
| 1 | `server/hyper_agent.py::_AR_ADVISOR_SYSTEM_PROMPT` | New module constant. JSON-schema-prescriptive prompt with decision rules per exit reason: `rate_limit` → increase pollInterval ≥600s; `context_full` → suggest `/clear` or summary promptHint; `auth_expired` → low-frequency retry + tell user to run `/login`; `unknown` high-failure → reduce maxAttempts. |
| 2 | `hyper_advise_auto_resume(entry, recent_failures, assignee="claude:haiku")` | Pre-validates `len(recent_failures) ≥ 2` and entry not in done/stopped. Calls existing `execute_with_assignee` meta-LLM path (Haiku default — fast + cheap). Post-clamps `pollIntervalSec` to [60,1800], `maxAttempts` to [1,50], `promptHint` to 500 chars, `rationale` to 300 chars. |
| 3 | `server/auto_resume.py::api_auto_resume_advise` | POST `/api/auto_resume/advise` body `{sessionId, assignee?}`. Returns proposal WITHOUT applying — UI decides whether to accept. |
| 4 | `dist/index.html` AR mgmt rows | New "🧠 Hyper Advisor" button per row → modal with current vs suggested poll interval / max attempts / prompt hint / rationale → "Apply" merges into existing entry. Toast "분석할 실패 이력이 부족함" when `<2` failures. |
| 5 | `tools/translations_manual_32.py` (new) | 10 KO→EN/ZH for advisor strings. |

### 🧪 Pytest expansion (B)

| # | Where | Cases |
|---|---|---|
| 6 | `tests/test_workflows.py` (new, 192 lines) | 18 cases — `_topological_levels`/`_topological_order`, `_is_position_only_patch`, `_run_indexed_fields`, `_runs_db_save/load/delete`. |
| 7 | `tests/test_ai_providers.py` (new, 125 lines) | 11 cases — `get_registry()` singleton, builtin providers, `execute_parallel` (no real network), `OllamaApiProvider.list_models` cache. |
| 8 | `tests/test_ccr_setup.py` (new, 155 lines) | 16 cases — `api_ccr_status` keys, 5 presets shape, alias snippet, 7 config-save validation/coercion cases. |

**Test totals: 68 → 113 (+45), runtime 0.23s → 1.82s.**

### ⚡ AR status short-circuit (C)

| # | Where | What |
|---|---|---|
| 9 | `server/auto_resume.py::api_auto_resume_status` | New `if not store: return {...empty...}` early-return — skips the v2.51.0 `_live_cli_sessions()` cross-ref (lsof + ps, ~150-300 ms macOS) when no bindings exist. |

**Measured: 327 ms → 0.155 ms steady-state — 2110× on the dev box; 467× on the production-shaped store.**

### Smoke
```
$ make test                                    113 passed in 1.82s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       2.9 ms
$ /api/auto_resume/status            200       0.7 ms  (was 327 ms — 467×)
$ /api/prefs/get                     200       0.8 ms
$ /api/auto_resume/advise            (rejects nonexistent sessionId with helpful error)
```

---
## [2.51.0] — 2026-04-30

### 🛠️ UX hardening — QS lag fix + mascot toggle + 현재 파라미터 + AR terminal-scoped + 🛟 reliability category

User: "마스코트 끄기 기능 및 현재 파라미터 기능 구현 필요. 빠른 설정
키면 렉이 급격하게 심해짐. auto-resume을 단순히 키는게 아니라 현재
열려있는 터미널에 대해서만 킬 수 있게 하고, 켜져있는지 확인할 수
있어야함. 따로 카테고리 만들어."

### ⚡ Quick Settings lag fix (A1)

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html::openQuickSettings` | Pre-fix tab-click handler: `dr.innerHTML = _qsRenderShell()` then `openQuickSettings()` recursively → re-rendered shell + re-bound controls TWICE per click. |
| 2 | `dist/index.html::_qsRefreshSection` (new) | Extract refresh logic — sets `dataset.section`, sets `innerHTML`, rebinds tabs (self-recursive ref), calls `_qsBindControls(sec)` exactly **once**. |
| 3 | `_qsResetSection` / `_qsResetAll` | Use `_qsRefreshSection` for re-render instead of re-calling full `openQuickSettings`. |

### 🐰 Mascot toggle (A2)

| # | Where | What |
|---|---|---|
| 4 | CSS `body[data-mascot-hidden="true"] #claudeMascot` | Already correct. Toggle flips via `_applyPrefsToDOM`. |
| 5 | `_showRandomBubble` + `_mascotWanderStep` | Added `if (document.body.dataset.mascotHidden === 'true') return;` guard — 15s bubble + 6-10s wander timers do no work when hidden. |

### 🔎 Current parameters viewer (A3)

| # | Where | What |
|---|---|---|
| 6 | `dist/index.html::_QS_SECTIONS` | New 5th section `{ id: 'current', icon: '🔎', label: '현재 파라미터', readonly: true }`. |
| 7 | `_qsRenderCurrentParams` (new) | Read-only pane. Three blocks: **Effective prefs** (section · key · value · source), **Runtime info** (server version, boot time, locale, theme, AR worker count, DB index count), **Endpoint quick links** (`/api/version`, `/api/prefs/get`, `/api/auto_resume/status`). |
| 8 | `_qsRenderSection` / `_qsBindControls` | Short-circuit on `'current'` and `readonly: true` respectively. Footer reset buttons hidden. |
| 9 | `tools/translations_manual_30.py` (new) | 16 KO→EN/ZH for new section labels. |

### 🔄 Auto-Resume terminal-scoping (B1)

| # | Where | What |
|---|---|---|
| 10 | `server/auto_resume.py::_live_cli_sessions` (new) | Wraps `process_monitor.api_cli_sessions_list({})` into `{sessionId: record}`. Best-effort try/except. |
| 11 | `api_auto_resume_set` | Rejects bindings for sessions with no live PID unless `allowUnboundSession=true`: `{"ok": False, "error": "Session not currently running. Pass allowUnboundSession=true to bind anyway."}`. When live, persists `pid` + `terminal_app` to entry alongside new `terminalClosedAction` field. |
| 12 | `api_auto_resume_status` | Cross-references live sessions per status call. Each active row gets `pid`, `terminal_app`, `liveSession: bool`. Server-side sort: live first. |
| 13 | `_process_one` | Tracks `_deadTicks` per entry (resets on revival). `terminalClosedAction == "cancel"` AND `_deadTicks > 2` → auto-cancel with `stopReason="terminal closed (auto-cancel after 3 ticks)"`. `"wait"` (default) preserves prior behavior. |
| 14 | `_public_state` | Surfaces `pid`, `terminal_app`, `terminalClosedAction` to UI. |
| 15 | `dist/index.html` AR mgmt table | New "터미널" column (mono `terminal_app + #pid`), live chip `🟢 실행 중` / `⚪ 종료됨` per `liveSession`. Client-side sort live-first. |

### 🛟 Reliability category (B2)

| # | Where | What |
|---|---|---|
| 16 | `server/nav_catalog.py` | `TAB_GROUPS` appended `("reliability", "Reliability — Auto-Resume · 자동 복구 · 바인딩 관리")`. `autoResumeManager` row's group changed from `observe` → `reliability`. |
| 17 | `dist/index.html` GROUPS | Appended `{ id: 'reliability', icon: '🛟', label: '안정성', short: '안정성', desc: 'Auto-Resume · 자동 복구 · 바인딩 관리' }`. NAV entry's `group:` updated. |
| 18 | `tools/translations_manual_31.py` (new) | 6 KO→EN/ZH for new column/chip/error strings. |

### Smoke
```
$ make test                                    68 passed in 0.58s
$ make i18n-verify                             ✓ 모든 검증 통과
$ /api/version                       200       7 ms
$ /api/auto_resume/status            200     327 ms  (new process_monitor cross-ref)
$ /api/prefs/get                     200     3.7 ms
```

### Note — auto_resume/status latency
The new live-session cross-reference adds a `lsof` + `ps` call (~150-300 ms macOS) per status request. Acceptable for the manual-refresh / 10s-poll cadence. Future micro-optimization: short-circuit when 0 bindings exist.

---
## [2.50.0] — 2026-04-30

### 📊 Observability + reliability — telemetry, cost recommendations, expanded test coverage

User: "다음 라운드 자율모드 시작." Three parallel agents on independent
domains. Surfaces the data v2.46.0–v2.49.0 quietly built up.

### 📊 Workflow execution telemetry (A)

| # | Where | What |
|---|---|---|
| 1 | `server/workflows.py` | `_telemetry_compute(window_hours)` reads `workflow_runs` SQLite (v2.47.0). Per-workflow stats: total/success/failed/cancelled, success rate, duration p50/p95/p99 (sec), avgIterations, totalCost. Global summary across all workflows. Status mapping accepts both `ok`/`err` and legacy `done`/`error` for back-compat. |
| 2 | `server/workflows.py::api_workflow_telemetry` | Public wrapper. `?window=1h\|24h\|7d\|30d` (default 7d). |
| 3 | `server/routes.py` | `GET /api/workflows/telemetry`. |
| 4 | `dist/index.html` | New `📊 실행 텔레메트리` panel inside `VIEWS.workflows` (NOT a separate tab). Window selector + global summary row + per-workflow table (top 50, others aggregated). 30s auto-refresh with `document.hidden` guard. Hidden when 0 runs. Uses `cachedApi`. |

### 💡 Cost-aware routing recommendations (B)

| # | Where | What |
|---|---|---|
| 5 | `server/cost_timeline.py` | `_recommendations()` aggregates last-30d costs across all 9 cost stores via existing `_gather_all()`. Generates rule-based suggestions:<br>**R1** (priority 3): sonnet/opus calls with `avg_tokens_in < 500` and `≥10 calls` → swap to Haiku, est. savings 85%.<br>**R2** (priority 2): `avg_tokens_in > 5000` and `≥5 calls` → enable prompt caching, est. savings 50%.<br>**R3** (priority 1): `≥100 calls` and `>$1` → try ollama (local), est. savings 100%.<br>**R4** (priority 4): stale model in `_MODEL_SUCCESSORS` table → quality upgrade, savings 0. |
| 6 | `server/cost_timeline.py::api_cost_recommendations` | Public wrapper. `?window=30d` default. Returns up to 20 recs sorted by `(priority DESC, estimatedSavings DESC)`. |
| 7 | `server/routes.py` | `GET /api/costs/recommendations`. |
| 8 | `dist/index.html` | `💡 비용 절감 추천` card inside `VIEWS.costsTimeline`. Header line `최근 30일 총 $N \| 예상 절감 $M`. Each rec as a row with rule chip + current → suggested + savings + rationale. "추천 새로고침" button. Hidden when 0 recs. |
| 9 | **Data adaptation** (truthful): spec referenced a `workflow_costs` SQLite table; actual data lives in JSON cost stores via `_gather_all()`. Implementation uses the real source — recommendations cover all sources, not just workflows. |

### 🧪 Pytest coverage expansion (C)

| # | Where | Cases |
|---|---|---|
| 10 | `tests/test_db.py` (new, 121 lines) | 8 cases — `_db_init` idempotent, all expected tables exist, all 12 expected indexes exist (v2.46.0+v2.48.0), WAL mode set, `_INITIALIZED` flag. Stub `run_history` table fixture so cross-module index DDL doesn't silently fail. |
| 11 | `tests/test_prefs.py` (new, 132 lines) | 16 cases — schema returns 4 sections, round-trip set/get/reset (single + batch), enum validation (`ui.theme`), int range validation (`behavior.telemetryRefresh`), graceful invalid-section. |
| 12 | `tests/test_process_monitor.py` (new, 139 lines) | 17 cases — `_parse_lsof_line` various formats, `_ps_metrics_batch` empty + valid, `_pid_alive` (uses `os.getpid()` instead of pid 1 to avoid macOS unprivileged `EPERM`), kill guards (self pid, pid<500, signal whitelist). |

**Test totals: 27 → 68 (+41), runtime 0.06s → 0.23s.**

### Smoke
```
$ make test                                             68 passed in 0.23s
$ make i18n-verify                                      ✓ 모든 검증 통과
$ /api/workflows/telemetry?window=7d  200  3.6 ms       global_keys: p50_sec, p95_sec, p99_sec, successRate, totalRuns
$ /api/costs/recommendations          200  1.8 ms       totalCost30d, estimatedSavingsTotal, recommendations[]
$ /api/auto_resume/status             200  1.1 ms
$ /api/version                        200  4.6 ms
```

### Files
- 5 modified: `server/workflows.py`, `server/cost_timeline.py`, `server/routes.py`, `dist/index.html`, `tools/translations_manual.py`
- 5 new: `tools/translations_manual_29.py`, `tests/test_db.py`, `tests/test_prefs.py`, `tests/test_process_monitor.py`

---
## [2.49.0] — 2026-04-30

### 🔄 Auto-Resume hardening — mgmt tab + email/telegram + Haiku direct + pytest

User: "누락/약한 부분 먼저 보완." Picks up the v2.49.0-deferred items from
v2.48.1 (worker concurrency landed first; rest blocked on rate limit).

### 🖥️ Mgmt tab + notification channels (B)

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` `VIEWS.autoResumeManager` | New `🔄 Auto-Resume 관리` tab under `observe` group. Header with total + per-state count chips. Active bindings table (session / cwd / state / attempts / next ETA / actions). Row checkboxes + "선택 취소" iterates POST `/api/auto_resume/cancel`. State chips colored by status. 10s auto-refresh with `document.hidden` guard. Mobile-stack at <640px. |
| 2 | `server/nav_catalog.py` | New `autoResumeManager` entry in `TAB_CATALOG` + EN/ZH descriptions in `TAB_DESC_I18N`. |
| 3 | `server/notify.py::send_email` | New SMTP+STARTTLS sender. cfg keys `{smtp_host, smtp_port, smtp_user, smtp_password, from, to}` (to as str/list). 10s timeout. Aborts if STARTTLS unsupported (no plaintext creds). Returns `{ok, error?}`, never raises. |
| 4 | `server/notify.py::send_telegram` | New Telegram Bot API sender. cfg `{bot_token, chat_id}`. POST `https://api.telegram.org/bot<token>/sendMessage` with Markdown. Uses dedicated `_NoRedirect` opener (host outside `_ALLOWED_HOSTS` whitelist). |
| 5 | `server/notify.py::_send_notify` | New multi-channel dispatcher (slack/discord/email/telegram). Iterates configured channels, accumulates per-channel results. |
| 6 | `server/auto_resume.py::_sanitize_notify` | Extended to pass-through `email` and `telegram` config dicts with key whitelist. Existing slack/discord behavior unchanged. |
| 7 | `server/auto_resume.py::_send_notify` | Wired `send_email` and `send_telegram` calls alongside existing slack/discord. Fully back-compat — entries without email/telegram config skip the new paths. |
| 8 | `tools/translations_manual_28.py` (new) + wiring | KO → EN/ZH for 31 new mgmt-tab strings. |

### 🦙 Haiku direct API + reinject docs (C)

| # | Where | What |
|---|---|---|
| 9 | `server/auto_resume_hooks.py::install` | Signature now `install(cwd, *, use_haiku_summary=False, use_direct_api=False)`. Return dict carries `useDirectApi`. Existing call sites in `auto_resume.py` keep working — flag defaults to False. |
| 10 | `server/auto_resume_hooks.py` | 36-line module-level docstring above `install()` documenting the snapshot+inject mechanism + both Haiku backends (CLI vs direct API) with relative cost notes. |
| 11 | `scripts/ar-haiku-summary.py` (new, executable, 198 lines, stdlib only) | Direct Anthropic Messages API helper bypassing the `claude -p` subprocess. Reads key from `ANTHROPIC_API_KEY` env or `~/.claude-dashboard-ai-providers.json`. POSTs `claude-haiku-4-5-20251001`, max_tokens 200, 10s timeout. Six distinct exit codes (1 missing, 2 no-key, 3 HTTP, 4 network, 5 parse, 6 unexpected). `--dry-run` redacts the API key in headers. Empty stdout on any failure → shell falls back to no-summary mode. |

### 🧪 pytest harness (D)

| # | Where | What |
|---|---|---|
| 12 | `tests/__init__.py` (new, empty) | Marks `tests/` as a package. |
| 13 | `tests/conftest.py` (new) | Shared fixtures: `isolated_home` (HOME → tmp_path) and `fixed_now` (stable epoch 1777982400.0 = 2026-04-30T12:00:00Z). |
| 14 | `tests/test_auto_resume.py` (new, 26 cases) | Unit tests covering `_classify_exit` (6 cases), `_parse_reset_time` (5), `_exponential_backoff` (5), `_push_hash_and_check_stall` (5), `_jsonl_idle_seconds` + `_looks_rate_limited` (5). Uses `tmp_path` for filesystem isolation. |
| 15 | `Makefile::test` | New target `make test` — checks pytest installed, runs `pytest tests/ -v`. |

### Smoke
```
$ make test
... 26 passed in 0.03s
$ python3 scripts/ar-haiku-summary.py --help
usage: ar-haiku-summary.py [-h] --jsonl-path JSONL_PATH ...
$ python3 -c "from server.notify import send_email, send_telegram, _send_notify; print('notify_ok')"
notify_ok
$ make i18n-verify
✓ 모든 검증 통과
$ /api/auto_resume/status         200  1.3 ms
$ /api/version                    200  4.1 ms
$ /api/workflows/list             200  3.3 ms
```

### Deferred
- **Hyper Agent integration** — auto-resume retry policy learned by hyper-agent meta-LLM. Bigger refactor; tracked as separate v2.50.x item.

---
## [2.48.1] — 2026-04-30

### 🔄 Auto-Resume worker — concurrent retry (4-way ThreadPool)

User: "누락/약한 부분 먼저 보완." Patch-level pickup of one piece from the
v2.49.0 plan that completed before agents hit the API rate limit.
Remaining items (mgmt tab, email/telegram channels, pytest harness,
Haiku direct API) are deferred to v2.49.0 proper.

| # | Where | What |
|---|---|---|
| 1 | `server/auto_resume.py::_worker_loop` | Single-threaded serial `for sid in due: _process_one(sid)` → `ThreadPoolExecutor(max_workers=4)` parallel fan-out per tick. Lock discipline preserved: `_process_one` takes `_LOCK` for JSON IO and uses `_RUNNING_PROCS` to block same-sid re-entry. Per-tick batch capped at pool size; overflow waits for next tick. |
| 2 | `server/auto_resume.py` | New `nextAttemptAt` filter — only entries whose retry time has elapsed are scheduled. Saves cycles on idle entries. |
| 3 | `server/auto_resume.py::stop_auto_resume` | `_RETRY_POOL.shutdown(wait=False, cancel_futures=True)` on worker shutdown — drains queued submissions cleanly. |

Effect: with N pending sessions previously waiting N×retry-time serially, up to 4 process concurrently. No-op when N=0 or 1.

### Smoke
```
$ python3 -c "from server.auto_resume import _RETRY_POOL, _RETRY_POOL_MAX_WORKERS; print(_RETRY_POOL_MAX_WORKERS)"
4
$ python3 -m py_compile server/auto_resume.py
compile_ok
```

### Deferred to v2.49.0 (rate-limited mid-execution)
- pytest harness for `_classify_exit / _parse_reset_time / _exponential_backoff / _push_hash_and_check_stall`
- Dedicated Auto-Resume management tab + bulk-cancel
- Email (SMTP) and Telegram notification channels
- `useDirectApi` option for Haiku summary (skips CLI subprocess)
- Prompt reinjection mechanism docstring

---
## [2.48.0] — 2026-04-30

### 🧹 Phase-3 perf — dead code purge + 7 new DB indexes + CSS prune

User: "다음 라운드 지시하고 main으로 모두 머지." Three parallel agents on
independent low-risk targets. Conservative — when in doubt, kept.

### 🐍 / 🌐 Dead code purge

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html::VIEWS.design + addDesignDir` | 128 lines removed. Orphaned tab — defined but no NAV entry, only self-referencing call. |
| 2 | `dist/index.html::_wfAddNode` | 35 lines removed. Defined but never referenced; superseded by inline node creation. |
| 3 | `dist/index.html::_wfInspectorBody` | 178 lines removed. Superseded by `_wfRenderInspector` inlining per-type forms. |
| 4 | `dist/index.html::_wfNodeSet` | 10 lines removed. Legacy variant superseded by `_wfNodeSetData`. |
| 5 | `server/system.py / auth.py / toolkits.py` | Unused imports (`MEMORY_DIR`, `re`, `Path`, `CLAUDE_HOME`, `log`). |

**Total JS removed: 354 lines, -23 KB**.  `dist/index.html` 1131 KB → 1108 KB.

### 🎨 CSS prune

`dist/index.html` `<style>` — removed `.card-hi`, `.divider`, `.group-label` (0 references). Theme/state classes verified dynamic-set and kept. CSS 932 → 928 lines, -2.1 KB. `css_opens=507 css_closes=507` balanced.

### 💾 Database — EXPLAIN-driven indexes

7 new indexes added after running `EXPLAIN QUERY PLAN` against the live `~/.claude-dashboard.db` for every static SQL in `server/*.py`. Each query went from `SCAN + TEMP B-TREE` to `SCAN/SEARCH USING INDEX` (no sort step).

| Query | Plan before | Index added | Plan after |
|---|---|---|---|
| `sessions ORDER BY tool_use_count DESC` | SCAN+TEMP B-TREE | `idx_sess_tool_use_count(tool_use_count DESC)` | SCAN USING INDEX |
| `sessions ORDER BY total_tokens DESC` | SCAN+TEMP B-TREE | `idx_sess_total_tokens(total_tokens DESC)` | SCAN USING INDEX |
| `sessions ORDER BY duration_ms DESC` | SCAN+TEMP B-TREE | `idx_sess_duration_ms(duration_ms DESC)` | SCAN USING INDEX |
| stats subagent dist (`tool_uses`) | SCAN tool_uses | `idx_tool_subagent_ts(subagent_type, ts)` | SCAN COVERING INDEX |
| `agent_edges WHERE ts >= ?` | SCAN | `idx_edge_ts(ts)` | SEARCH (kicks in past ~500 rows) |
| `workflow_runs ORDER BY started_at DESC` | SCAN+TEMP B-TREE | `idx_runs_started(started_at DESC)` | SCAN USING INDEX |
| `run_history WHERE source=? AND item_id=? ORDER BY ts DESC` | SEARCH+TEMP B-TREE | `idx_runhist_item_ts(source, item_id, ts DESC)` | SEARCH USING INDEX |

`ANALYZE` added at end of `_db_init()` — 4.8 ms one-time per process.

DB index count: 12 → **19**.

### Smoke
```
=== endpoint smoke (warm) ===
/api/version          200   4.0 ms
/api/workflows/list   200   3.3 ms
/api/sessions/list    200   6.2 ms
/api/sessions/stats   200   4.5 ms
/api/usage/summary    200  11.4 ms
/api/agents           200  21.5 ms
/api/skills           200  10 ms cached
/api/ports/list       200  144 ms (lsof bound)
=== RSS ===                71.5 MB
=== DB indexes ===          19  (+7)
=== make i18n-verify ===   ✓ 모든 검증 통과
```

---
## [2.47.0] — 2026-04-30

### 🚀 Phase-2 perf — workflows runs → SQLite + 27× RSS drop + frontend consolidation

User: "계속 진행해. 자율모드. 더 큰 factory." Phase 2 of the comprehensive
optimization sweep — the items v2.46.0 explicitly deferred as "high blast
radius". Three parallel agents handled separate domains.

### 💾 workflows.runs → SQLite migration (the big one)

`~/.claude-dashboard-workflows.json` previously stored both definitions
AND runs in one JSON blob. Every per-node status update went through
`_LOCK` → `_load_all` → mutate → `_dump_all` (full file serialize +
fsync). Concurrent workflow saves serialized on this lock.

| # | Where | What |
|---|---|---|
| 1 | `server/db.py::_db_init` | New `workflow_runs(run_id PK, workflow_id, status, started_at, ended_at, iteration, total_iterations, cost_total, tokens_in, tokens_out, payload_json TEXT)` table + `idx_runs_workflow(workflow_id, started_at DESC)` + `idx_runs_status(status, started_at DESC)`. |
| 2 | `server/workflows.py` | New helpers: `_runs_db_save / load / delete / list_recent / summaries` + `_run_indexed_fields`. Per-node updates still go through `_RUNS_CACHE` (live state) but persistence is now `INSERT OR REPLACE` into the table — no JSON round-trip. |
| 3 | `server/workflows.py` | One-time `_migrate_runs_to_db()` flagged by `migration_v2_47_runs_done` in the JSON store. Legacy `runs` dict is preserved (defensive rollback). |
| 4 | `server/workflows.py::_LOCK` | Now covers definitions only (workflows array, history, customTemplates, schedule). `_RUNS_LOCK` still guards in-flight `_RUNS_CACHE`. SQLite handles run persistence concurrency itself. |
| 5 | `_run_status_snapshot / api_workflows_list / api_workflow_run_diff / api_workflow_runs_list / api_workflow_stats / _notify_run_completion` | All updated to read via cache → DB fallback. `api_workflows_list` uses one batched `GROUP BY workflow_id` for `totalRuns`. |

### 🧠 RSS — measured 1577 MB → 57.5 MB (~27× ↓)

`tracemalloc` profile showed Python's heap was only ~10 MB. The OS-level RSS came from transient allocations during session indexing that weren't released back to the kernel.

| # | Where | What |
|---|---|---|
| 6 | `server/sessions.py::_index_jsonl` | Was `read_text()` + `splitlines()` + materialized `lines: list[dict]` + 3 separate iterations to compute `first_user_prompt / model / cwd`. Rewrote as single-pass streaming line-by-line; replaced helpers with `_extract_*_from_msg(msg)` per-line. |
| 7 | `server/notify.py` | `import ssl` + eager `_NO_REDIRECT_OPENER = build_opener(...)` deferred. Now `_get_opener()` cached on first use. ~3-6 MB at boot when no notification fires. |
| 8 | `scripts/profile-boot-rss.py` (new) | Reusable tracemalloc + ps regression harness. |

**Measured impact:**
- Steady-state boot: ~700 MB peak / 522 MB current → **124 MB peak / 42 MB current** (16×)
- Force re-index (161 sessions / 501 MB jsonl): 1947 MB peak / 1920 MB current → **102 MB peak / ~80 MB current** (19×)
- Live server (`/api/version` 200): **57.5 MB RSS**

DB integrity verified: 168 sessions, 10633 tool_use rows, 6.8B tokens — unchanged.

### 🎨 Frontend consolidation

| # | Where | What |
|---|---|---|
| 9 | `dist/index.html` `VIEWS.sessions` | 100-row `tbody.innerHTML` rebuild → 50-row initial paint + `IntersectionObserver` sentinel that appends 50 at a time. Sort/filter naturally resets via renderView innerHTML swap. |
| 10 | `dist/index.html` 8 Chart.js sites | New `_chartInstances: Map` + `_renderChart(canvas, cfg)` helper. `chart.destroy() + new Chart()` → in-place `data.datasets[0].data = ...; chart.update('none')` when type+dataset count match. Stale-canvas sweep on each call. |
| 11 | `dist/index.html` keydown | 9 module-level `document.addEventListener('keydown')` → single dispatcher with `_KEYDOWN_HANDLERS` array. Each former handler returns truthy to consume + stop propagation. Bonus: caught `_wfBindCanvas` re-attaching its keydown on every visit (latent leak). |
| 12 | `dist/index.html` `_makeDraggable` | Stored bound move/up handlers on the dragged element → `_detachDragListeners(el)` called in `closeFeatureWindow` and `_wfCloseNodeEditor`. Plugged document-listener leak that accumulated over a session. |

### 🌐 i18n hotfix
- `tools/translations_manual.py` — restored missing `_26` import block (v2.46.0's "duplicate cleanup" agent removed the import too aggressively, leaving `_NEW_EN_26` references undefined). Added `_27` import + merge.
- `tools/translations_manual_27.py` (new) — KO→EN/ZH for the new sentinel string `'더 불러오는 중…'`.

### Smoke
```
=== boot log ===
Serving http://… BEFORE indexing/ollama (v2.46.0 daemonization preserved)
=== RSS ===                          57,504 KB  (was 1,577,072 KB → 27.4× ↓)
=== /api/workflows/list ===          3.6 ms
=== workflow_runs DB ===
  table: workflow_runs ✓
  indexes: idx_runs_workflow, idx_runs_status ✓
  row_count: 2 (migration ok)
=== make i18n-verify ===            ✓ 모든 검증 통과
```

---
## [2.46.0] — 2026-04-30

### 🚀 Comprehensive perf sweep (33 surgical fixes across backend / frontend / boot)

User: "지금부터 대시보드를 모두 최적화 작업을 진행할거야. 엄청 세세한
코드까지 극한의 효율과 알고리즘으로 최적화해줘." Three deep-recon agents
mapped every hot spot across 50+ Python modules + the 23k-line single-file
SPA + the i18n / static / boot path; three implementation agents executed
phase 1 in parallel on isolated file regions. No backwards-incompat changes.

### 🐍 Backend (12 fixes)

| # | File | Fix |
|---|---|---|
| B1 | `server/db.py::_db_init` | `_INITIALIZED` flag with double-checked lock — was running `PRAGMA table_info` + `ALTER TABLE` guards on every API request. Now O(1) per process. |
| B2 | `server/db.py::_db()` | `PRAGMA journal_mode=WAL` moved out of per-connection path into the one-time init. |
| B3 | `server/db.py` | Added 3 missing indexes: `idx_sess_started`, `idx_sess_score(score, tool_use_count)`, `idx_sess_cwd_started(cwd, started_at)` (verified absent in live DB before adding). |
| B4 | `server/workflows.py::_record_workflow_cost` | Removed redundant `_db_init()` call — was firing on every workflow node execution. |
| B5 | `server/mcp.py` | Module-level `_MCP_LIST_CACHE_FILE.read_text()` + `json.loads` deferred to `_load_disk_cache()` invoked from `warmup_caches()` daemon thread — no boot-time disk I/O. |
| B6 | `server/translations.py::_load_translation_cache` | Module-level `_TRANS_CACHE` + `_TRANS_MTIME` mtime-keyed memory cache. Was reloading + parsing JSON on every call. |
| B7 | `server/ai_providers.py::OllamaApiProvider.list_models` | Instance-level 60s TTL cache. Was firing HTTP `/api/tags` on every model dispatch. |
| B8 | `server/process_monitor.py::api_ports_list` | TCP/UDP `lsof` probes parallelized via `ThreadPoolExecutor(2)`. |
| B9 | `server/hooks.py::_scan_plugin_hooks` | mtime-guarded TTL-30s cache. Recent-blocks endpoint cold→warm: **2754 ms → 4 ms (~700×)**. |
| B10 | `server/sessions.py::api_sessions_stats` | **Pre-existing bug**: daily-timeline `c.execute(...)` was nested inside the per-project loop AND outside the `with _db()` block — used a closed cursor and ran N×projects. Pulled out as one global `GROUP BY` query inside the connection scope. |
| B11 | `server/sessions.py::index_all_sessions` | New `mtime` column on `sessions` table. Index skip-check compares stored mtime first; falls back to `indexed_at` for legacy rows. |
| B12 | `server/learner.py::_collect_sessions` | Replaced `~/.claude/projects/*/*.jsonl` filesystem walk with SQL queries against indexed `sessions + tool_uses` tables. Same return shape; cuts the warmup learner cycle. |

### 🌐 Frontend (8 fixes)

| # | File | Fix |
|---|---|---|
| F1 | `dist/index.html::_wfUpdateNodeTransform` | Drag mousemove was running `document.querySelector('#wfNodes g.wf-node[data-node="..."]')` — full SVG attribute scan at 60fps. Replaced with `__wf._nodeEls.get(nid)` (O(1) Map lookup; the keyed-diff Map was already maintained). |
| F2 | `dist/index.html` pan + wheel handlers | `document.getElementById('wfViewport')` cached on `__wf._viewportEl`, set in `_wfBindCanvas`, invalidated on `_wfOpen`. Was running every event tick. |
| F3 | `dist/index.html` | Removed duplicate `window.addEventListener('resize', _syncNavToggleVisibility)` registered twice (every resize fired the handler twice). |
| F4 | `dist/index.html` 11 endpoints | `await api(...)` → `await cachedApi(...)` for read-only catalogs: `/api/optimization/score`, `/api/briefing/overview`, `/api/sessions/stats` (×2), `/api/agents`, `/api/skills`, `/api/commands`, `/api/projects` (×2), `/api/briefing/projects-summary`, `/api/features/list`. |
| F5 | `dist/index.html::_getRecentTabs` | Module-level `_recentTabsCache`. Was `JSON.parse(localStorage.getItem(...))` on every `renderNav` (every tab switch). |
| F6 | `dist/index.html` 5 polling timers | `if (document.hidden) return;` guard added to: workflow run-status fallback poll (1.2s), ollama pull-status (2s), telemetry live-refresh (30s), version poll (60s), aiProviders install-detect (10s). Background tabs no longer burn requests. |
| F7 | `dist/index.html::escapeHtml` | Replacement map hoisted to module-scope const `_ESC_HTML_MAP`. Was re-allocating the 5-entry object on every match. Function is called 905× across the codebase, up to 1000× per filter keystroke in 200-card list renders. |
| F8 | `dist/index.html::_apiCache` | Converted plain object to `Map` with LRU eviction at 50 entries (`_apiCacheSet` evicts oldest insertion). Cache was unbounded — long sessions accumulated stale entries. |

### 🚀 Boot + static + i18n (4 fixes)

| # | File | Fix |
|---|---|---|
| C1 | `server.py::main` | `background_index()` and `_auto_start_ollama()` wrapped in daemon threads. Boot log now shows `Serving http://...` BEFORE indexing/ollama probe — server accepts connections immediately. |
| C2 | `server/routes.py` | New `_LOCALE_CACHE: OrderedDict` (cap 16) + rewritten `_send_locale` with mtime cache + gzip + ETag. `_send_static` adds `ETag: W/"<int(mtime)>"` + `Cache-Control: no-cache, must-revalidate`; `If-None-Match` returns 304 — verified. `_STATIC_CACHE` capped at 64 entries with `OrderedDict` LRU. |
| C3 | `scripts/translate-refresh.sh` | mtime-guard early-exit: skip the 1.7s pipeline when no source file is newer than `translation-audit.json`. Bypass with `FORCE=1`. |
| C4 | `tools/translations_manual.py` | Removed duplicate `_NEW_EN_26 / _NEW_ZH_26` merge block (recon agent caught the duplication). |

### Measured wins
```
=== Boot ordering ===  Serving http://… BEFORE initial index BEFORE ollama probe ✓
=== ETag + gzip ===    locale en.json: Content-Encoding: gzip + ETag W/"…" ✓
=== 304 short-circuit ===  If-None-Match → HTTP 304 ✓
=== /api/hooks/recent-blocks ===  cold 2754 ms → warm 4 ms  (~700×)
=== /api/version ===   ≤ 15 ms warm
=== /api/workflows/list ===  3 ms warm
=== _db_init second call ===  0.00 ms (was every request)
=== translation cache warm ===  0.01 ms (was per-request reload)
=== hooks scan warm ===  0.02 ms (was every /api/hooks call)
=== learner _collect_sessions ===  11 ms via SQL (was JSONL filesystem walk)
```

### Risks held back to v2.47.0+ (intentionally)
- `workflows.py` runs dict → SQLite migration (high blast).
- Boot RSS profiling with `tracemalloc` (the recon's "867 MB" suspicion needs measurement before refactor).
- Session table virtual-scroll (frontend Phase C).
- 8× `Chart.js` `destroy+new` → `chart.update('none')` (frontend Phase B).
- 9× global keydown listeners → single dispatcher.
- `_makeDraggable` document-listener leak fix (medium-risk window-lifecycle change).

### Smoke
```
$ python3 -m py_compile server.py server/db.py server/sessions.py server/workflows.py …
compile_ok
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.45.2] — 2026-04-30

### 🐛 Fix — installed Ollama models table never repainted + 🔌 auto-start toggle

User: "설치된 모델에서 아예 보이지 않아. 그리고 ollama가 대시보드를 켤
때마다 자동으로 같이 켜지는데 메모리를 너무 많이 먹어. 내가 켜고 끌 수
있게 해줘."

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html::_ollamaLoadInstalled` | After `await api('/api/ollama/models')` populated `_ollamaInstalledData`, the catalog grid was repainted but the **installed-models table was never refreshed** — stuck on the "no models installed" placeholder forever. Added the missing `_ollamaRenderInstalled()` call. The 🗑 delete + 상세 button per row now actually appear. |
| 2 | `server/prefs.py` | New pref `behavior.autoStartOllama` (`bool`, default `True` for back-compat). Validated in `PREFS_SCHEMA["behavior"]`; persisted to `~/.claude-dashboard-prefs.json` like every other behavior key. |
| 3 | `server.py::_auto_start_ollama` | Reads the pref before spawning `ollama serve`. When `behavior.autoStartOllama=false`, logs `disabled by behavior.autoStartOllama=false` and skips. |
| 4 | `dist/index.html` Quick Settings labels | New row `behavior.autoStartOllama` → "Ollama 자동 시작 / 대시보드 부팅 시 ollama serve 자동 실행 (끄면 메모리 절감)". Renders automatically since the drawer is schema-driven (v2.38.0). |
| 5 | `tools/translations_manual_26.py` (new) + `tools/translations_manual.py` wiring | KO → EN/ZH for the new label and its hint. |

### Note on Gemini

User also reported "gemini also auto-starts and eats memory". Verified
via `grep -rn "gemini" server/` + `ps aux | grep gemini` that **lazyclaude
never auto-starts a Gemini process**. Gemini CLI is only invoked when
the user clicks 🖥 Spawn on a workflow node assigned to `gemini:*`. The
process they see is from a separately configured MCP server or external
tool — outside lazyclaude's lifecycle. The v2.44.0 Memory Manager tab
(`POST /api/process/kill`) can already terminate it on demand.

### Smoke
```
$ python3 -c "from server.prefs import api_prefs_get, api_prefs_set, PREFS_SCHEMA; print(PREFS_SCHEMA['behavior']['autoStartOllama']); api_prefs_set({'section':'behavior','key':'autoStartOllama','value':False}); g=api_prefs_get({}); print((g.get('prefs') or g)['behavior']['autoStartOllama']); api_prefs_set({'section':'behavior','key':'autoStartOllama','value':True})"
('bool', None)
False
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.45.1] — 2026-04-29

### 🚀 Perf hotfix — `/api/ccr/status` parallel probes + `/api/sessions-monitor/list` batched ps

Followup to v2.45.0 perf measurement. Two surgical wins:

| # | Where | What | Effect |
|---|---|---|---|
| 1 | `server/ccr_setup.py::api_ccr_status` | The 4 subprocess probes (`node --version`, `ccr --version`, `claude --version`, lsof port-3456 LISTEN check) ran sequentially → ~700 ms cold / ~600 ms warm. Now fanned out via `concurrent.futures.ThreadPoolExecutor(max_workers=4)`. The slowest single subprocess dominates instead of the sum. | **~700 ms → ~340 ms median (≈50% ↓)** measured on the dev box. |
| 2 | `server/process_monitor.py::_ps_metrics_batch` (new) + `api_cli_sessions_list` | Per-session `ps -o pid=,rss=,pcpu= -p <pid>` was N+1 subprocesses (one per active CLI session). Replaced with one `ps … -p pid1,pid2,…` call that returns all rows. | Equal cost at N≤1, **~N×** faster at N≥2 (linear in active session count). |

### Smoke
```
$ python3 -c "from server.ccr_setup import api_ccr_status; from server.process_monitor import _ps_metrics_batch; print(api_ccr_status({})['ok'], len(_ps_metrics_batch([1])))"
True 1
```

---
## [2.45.0] — 2026-04-29

### 🛣️ Claude Code Router (zclaude) setup wizard

User: "claudecode를 zclaude로 사용할 수 있게 세팅하는 기능도 추가해줘.
claude-code-router를 이용해서." Adds a new `config`-group tab that walks
the user through configuring `@musistudio/claude-code-router` (CCR) so
Claude Code can be routed through Z.AI / DeepSeek / OpenRouter / Ollama /
Gemini and invoked as `zclaude`. Per user choice (option B), the shell
alias is shown for **copy-paste** — the dashboard never edits `~/.zshrc`.

| # | Where | What |
|---|---|---|
| 1 | `server/ccr_setup.py` (new, 432 lines, stdlib-only) | Status probes (`node --version`, `ccr --version`, `claude --version`, port-3456 listen check), atomic config CRUD via `_safe_write` + `chmod 600`, schema validation against the verified CCR v2.0.0 schema (top-level `APIKEY/PROXY_URL/LOG/LOG_LEVEL/HOST/PORT/NON_INTERACTIVE_MODE/API_TIMEOUT_MS/Providers/Router`; provider keys `name/api_base_url/api_key/models/transformer`; router keys `default/background/think/longContext/longContextThreshold/webSearch/image`). All paths sandboxed under `$HOME` via `_under_home`. Unknown top-level keys stripped with warnings; provider-level transformer customizations preserved. |
| 2 | `server/ccr_setup.py::api_ccr_install_command` | Returns the npm command string for the UI to display — the dashboard NEVER runs `npm install -g` autonomously. User runs it themselves. |
| 3 | `server/ccr_setup.py::api_ccr_service` | Runs `ccr start | stop | restart` (15s timeout). |
| 4 | `server/ccr_setup.py::api_ccr_alias_snippet` | Generates a copy-paste block (`# >>> zclaude (lazyclaude) >>>` … `# <<<`) with `alias zclaude='ccr code'` and the `eval "$(ccr activate)" && claude` alternative. Detects `$SHELL`, returns the corresponding `~/.zshrc` / `~/.bashrc` path and `already_present` (substring match — read-only). **Never writes to any rc file.** |
| 5 | `server/ccr_setup.py::api_ccr_presets` | Returns 5 provider presets the UI can one-click insert: Z.AI (via `aihubmix` shape with `Z/glm-4.5`, `Z/glm-4.6`), DeepSeek, OpenRouter, Ollama, Gemini — all mirrored verbatim from the upstream `config.example.json`. |
| 6 | `server/routes.py` | Registers 5 GET routes (`/api/ccr/status`, `/config`, `/install-command`, `/alias-snippet`, `/presets`) + 2 POST routes (`/api/ccr/config`, `/service`). |
| 7 | `server/nav_catalog.py` + `dist/index.html` `VIEWS.zclaude` | New tab `🛣️ zclaude (CCR)` under the `config` group. |
| 8 | `dist/index.html` 5-step wizard | (1) Status pills + npm install command in copy-able `<code>` when ccr missing. (2) Providers — preset chips + editable rows (name/url/key/models/transformer JSON). (3) Router rules — 5 selects populated from configured provider×model pairs + `longContextThreshold`. (4) Service Start/Stop/Restart + live output. (5) Shell alias `<pre>` + Copy button + current-shell + rc-path + muted note that the user must paste it themselves. |
| 9 | `tools/translations_manual_25.py` (new) | KO → EN/ZH for 65 new strings. |

### Verified facts used in implementation
Source: `https://raw.githubusercontent.com/musistudio/claude-code-router/main/{package.json,README.md}` fetched 2026-04-29.
- npm: `@musistudio/claude-code-router` v2.0.0, bin `ccr`, node ≥20.0.0
- Config: `~/.claude-code-router/config.json`, env interpolation `$VAR` / `${VAR}`
- CLI: `ccr code | start | stop | restart | status | ui | model | activate | preset`
- `eval "$(ccr activate)"` exports `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL=http://127.0.0.1:3456`, `NO_PROXY=127.0.0.1`, `DISABLE_TELEMETRY`, `DISABLE_COST_WARNINGS`, `API_TIMEOUT_MS`

### Smoke
```
$ python3 -c "from server.ccr_setup import api_ccr_status, api_ccr_presets; s=api_ccr_status({}); print(s['ok'], s['node_version'], 'presets=', len(api_ccr_presets({})['presets']))"
True v24.13.0 presets= 5
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.44.1] — 2026-04-29

### 🪢 multiAssignee parallel fan-out + keyed canvas SVG diff

User: "자율모드 시작." Picks up the two items v2.44.0 explicitly deferred:
the UI surface for `ProviderRegistry.execute_parallel` (openclaw-style
multi-provider fan-out) and the keyed-diff renderer for the workflow
canvas.

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` `_wfInspectorBody` | Session/subagent inspector replaces the single assignee `<select>` with a repeating row builder. `+ 어시니 추가` appends, `−` per row removes. When `length ≥ 2` a "병렬 (N)" chip renders next to the section label. |
| 2 | `dist/index.html` `_wfMultiAssignee*` helpers | `_wfMultiAssigneeRows / Set / Add / Remove / RowHtml`. Stored as `node.data.multiAssignee = ['claude:opus', 'openai:gpt-4.1', …]`. Back-compat: `assignee = rows[0]`; `multiAssignee = rows.length ≥ 2 ? rows : []`, so single-assignee nodes keep behaving exactly as before. |
| 3 | `server/workflows.py::_sanitize_node` | New `multiAssignee` field on `session`/`subagent` types — same length cap as `assignee`, dedupe preserving order, hard cap at 8 (matches `execute_parallel` pool). |
| 4 | `server/workflows.py::_execute_node` session/subagent branch | Dispatch decision: `len(multi_assignees) ≥ 2` → `get_registry().execute_parallel(...)`; else existing `execute_with_assignee(...)`. Same `AIResponse` shape downstream — cost tracking, output writing, error handling all unchanged. |
| 5 | `dist/index.html` `_wfRenderCanvas` | Rewrote as keyed-diff renderer. New `__wf._nodeEls: Map<id, <g>>` + `__wf._nodeSnapshot: Map<id, json>`. Per render: add new ids, replace changed ids (snapshot-keyed), remove stale ids. Edges still rebuild via `innerHTML` — fewer of them and they reference live node positions. |
| 6 | `dist/index.html` `_wfBuildNodeEl` (new) | Parses `_wfRenderNode(n)` HTML through `DOMParser` (image/svg+xml, wrapped in `<svg xmlns>` for namespace), `document.importNode`, returns the `<g.wf-node>`. |
| 7 | `dist/index.html` `_wfNodeSnapKey` (new) | `JSON.stringify({type, title, x, y, data.assignee, data.multiAssignee})`. Selection state intentionally excluded — `_wfSyncSelectionClasses` toggles classes in-place. |
| 8 | `dist/index.html` `_wfOpen` / `_wfUndo` | Set `__wf._forceFullCanvasRebuild = true` so the first render after load and any wholesale array swap falls back to the old `innerHTML` path. Flag self-clears after the rebuild. |
| 9 | `tools/translations_manual_24.py` (new) | KO → EN/ZH for the 5 new inspector strings. |

### Verification — handler delegation

All node-level events (`mousedown`, `dblclick`, `touchstart`, `wheel`)
are attached to the parent `<svg>#wfSvg` and resolve targets via
`querySelector('[data-node="…"]')` / `.wf-node`. No per-element
`addEventListener` calls on `wf-node`. Diff-rebuilt elements retain
the `data-node` attribute set inside `_wfRenderNode`, so all
interactions continue without re-binding. `_wfApplyRunStatus`,
`_wfSyncSelectionClasses`, `_wfSyncMultiSelectClasses`, search
highlight, and group collapse all use the same selector pattern.

### Smoke
```
$ python3 -c "from server.workflows import _sanitize_node; from server.ai_providers import ProviderRegistry, get_registry; print('parallel=', hasattr(ProviderRegistry, 'execute_parallel'), 'reg=', type(get_registry()).__name__)"
parallel= True reg= ProviderRegistry
$ python3 -m py_compile server/workflows.py server/ai_providers.py
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.44.0] — 2026-04-29

### 🖥️ Open ports / CLI sessions / memory monitors + workflow perf

User: "현재 PC에 열려있는 포트 / 열려있는 CLI 세션 / 메모리를 보고 필요하면
바로 kill하고 싶어. 그리고 워크플로우가 너무 느리고 다중 AI를 openclaw처럼
병렬로 못 돌리고 있어 — 최적화해줘." Three new `observe` tabs to surface
host-process state, plus a sweep of workflow-engine and canvas optimizations.

| # | Where | What |
|---|---|---|
| 1 | `server/process_monitor.py` (new) | Stdlib-only module. `lsof -nP -iTCP -sTCP:LISTEN` + `lsof -nP -iUDP` parser; `~/.claude/sessions/*.json` + `os.kill(pid,0)` liveness; macOS `vm_stat` / `sysctl hw.memsize` / `sysctl vm.swapusage` snapshot; `ps -axo` for top-30 RSS with Claude-Code detection. |
| 2 | `server/process_monitor.py::api_process_kill` | Hard guards: `pid != os.getpid()`, `pid >= 500`, signal whitelist `{SIGTERM, SIGKILL}`, alive-check, `PermissionError` surfaced as 403. |
| 3 | `server/process_monitor.py::api_kill_idle_claude` | Bulk SIGTERM all CLI sessions whose `idle_seconds > thresholdSec` (default 600). Same guards per pid. |
| 4 | `server/process_monitor.py::api_session_open_terminal` | Wraps existing `actions.open_session_action` (Terminal.app / iTerm2 / Warp focus). |
| 5 | `server/routes.py` | Registers 6 endpoints: `GET /api/ports/list`, `/api/sessions-monitor/list`, `/api/memory/snapshot`; `POST /api/process/kill`, `/api/sessions-monitor/open-terminal`, `/api/memory/kill-idle-claude`. |
| 6 | `server/nav_catalog.py` + `dist/index.html` `VIEWS.openPorts` / `cliSessions` / `memoryManager` | Three new tabs under `observe`. Style mirrored from `VIEWS.system`. Memory tab shows total/used/free/swap progress bars, "Idle Claude Code 일괄 종료" button, top-30 RSS table with Claude-Code rows highlighted. |
| 7 | `server/workflows.py` `_MAX_PARALLEL_WORKERS` | 4 → `max(8, min(32, cpu_count()*2))` (16 on 8-core). Env override (`WORKFLOW_MAX_PARALLEL`) preserved. |
| 8 | `server/workflows.py::api_workflow_patch` + `_is_position_only_patch` | Drag-debounced position/viewport patches no longer re-run full `_sanitize_workflow`; `math.isfinite` whitelist + in-place node mutation only. |
| 9 | `server/workflows.py` `_TOPO_ORDER_CACHE` / `_TOPO_LEVELS_CACHE` | Memoized topological sort keyed by graph shape. FIFO 256-entry soft cap. |
| 10 | `server/workflows.py` `_RUNS_CACHE` + `_persist_run` | Per-node status updates inside `_run_one_iteration` mutate an in-memory cache under `_RUNS_LOCK`; disk-write only at iteration boundary / terminal failure / completion. SSE `_run_status_snapshot` reads cache first. Drops per-run JSON round-trips from O(N) to O(L). |
| 11 | `server/ai_providers.py::ProviderRegistry.execute_parallel` (new) | Backend-only openclaw-style fan-out: `ThreadPoolExecutor(min(len, 8))` + `as_completed` first-ok with `future.cancel()` on the rest. UI wiring deferred to v2.44.1. |
| 12 | `dist/index.html` `__wf._webhookSecretCache` | Webhook secret cached per-`workflowId`; `_wfRefreshWebhookSecret` no longer POSTs on every node click. |
| 13 | `dist/index.html::_wfRenderInspector` | Early-exit guard when `selectedNodeId` unchanged and `_inspectorDirty === false`. All node-data mutators set the dirty flag before re-rendering. |
| 14 | `tools/translations_manual_23.py` (new) | KO → EN/ZH for 30+ new strings (port headers, CLI columns, memory bars, kill confirms, idle threshold). |

### Skipped / deferred
- **Keyed canvas SVG patch**: full DOM-element diff for `_wfRenderCanvas` exceeded the low-risk budget — would require re-attaching every drag/connect/double-click handler. B4/B7 already remove the dominant cost.
- **`execute_parallel` UI wiring**: needs a `multiAssignee[]` field in the inspector + form — landing in v2.44.1.

### Smoke
```
$ python3 -c "from server.workflows import _MAX_PARALLEL_WORKERS; from server.process_monitor import api_ports_list, api_memory_snapshot, api_cli_sessions_list; from server.ai_providers import ProviderRegistry; print(_MAX_PARALLEL_WORKERS, api_ports_list({}).get('ok'), api_memory_snapshot({}).get('ok'), api_cli_sessions_list({}).get('ok'), hasattr(ProviderRegistry, 'execute_parallel'))"
16 True True True True
$ make i18n-verify
✓ 모든 검증 통과
```

---
## [2.43.2] — 2026-04-28

### 📊 Project / session token usage drill-down

User: "프로젝트 혹은 세션별 토큰 사용량을 보고 싶어. 근데 사용량/비용
(토큰 중심)에서 지금 TOP20만 볼 수 있는데, 그냥 프로젝트를 눌러서 토큰
사용량을 보고 싶어." Replaces fixed TOP-20 read-only table with a
clickable, scrollable list of every project; click → modal with the
project's session-level breakdown.

| # | Where | What |
|---|---|---|
| 1 | `server/system.py::api_usage_summary` | Drops `LIMIT 20` from the `byProject` SQL so the response carries every project (29 instead of 20 on this machine), still ordered by tokens DESC. |
| 2 | `server/system.py::api_usage_project` (new) | `GET /api/usage/project?cwd=...` — returns `{totals, sessions[], byTool[], byAgent[], dailyTimeline[]}` for one project. cwd resolved + sandboxed under `$HOME`. Joins `tool_uses` filtered to that project's session_ids for tool/agent distribution. |
| 3 | `server/routes.py` | Wires `/api/usage/project` into `ROUTES_GET`. |
| 4 | `dist/index.html::VIEWS.usage` | Project section becomes a scrollable (max 420 px) list of all projects; rows are `link-row` clickable, with cwd as tooltip + truncated subtitle. Header shows total project count instead of "TOP 20". |
| 5 | `dist/index.html::openProjectUsage` (new) | Modal: 6 stat cards (total / input / output / cacheRead / cacheCreate / sessions), tool-by-tool + agent-by-agent token bars, daily timeline minibar, sessions table sorted by tokens DESC. Each session row links into the existing session-detail modal. |
| 6 | `tools/translations_manual_22.py` (new) | KO → EN/ZH for 10 new strings (`프로젝트별 토큰`, `세션별 토큰`, `행 클릭 → 상세`, etc.). |

#### Verification
```
GET /api/usage/summary               → byProject count: 29 (was 20 cap)
GET /api/usage/project?cwd=$HOME/lazyclaude
                                     → ok=True, sessions=1, dailyTimeline len=1
GET /api/usage/project?cwd=/tmp      → 400 cwd outside home (sandbox)
GET /api/usage/project (no cwd)      → 400 cwd required
Headless: usage tab → 29 project rows, click 1st → modal with 81 session
                       rows for that cwd, 0 console errors
e2e-tabs-smoke.mjs                   → 58/58
make i18n-verify                     → 0 missing across EN/ZH
```

#### Compatibility
- Backend addition only — `byProject` still ordered the same way; unchanged frontend code keeps working (just sees more rows now).
- New endpoint `/api/usage/project` is purely additive.

---
## [2.43.1] — 2026-04-28

### 🚀 Perf — workflow canvas + skills/commands lists

User: "지금 전체적으로 대시보드가 너무 느려. 특히 워크플로우 부분이 심각하게
렉이 걸리고 느린데, 이 부분 최적화해줘." Three measured bottlenecks fixed.

**Measured before**

```
/api/skills      :  816 ms (1.37 MB) — 485 SKILL.md re-parsed every visit
/api/commands    : 1116 ms (1.44 MB) — 308 plugin command .md re-parsed
canvas drag      :   ~100 mousemove/s → _wfRenderMinimap fired sync every
                     event; full canvas redraw + O(N×E) edge lookup
```

**Measured after**

```
/api/skills      :   95 ms cold → 36 ms warm  (~22× / cache hit)
/api/commands    :  535 ms cold → 35 ms warm  (~31× / cache hit)
canvas drag      :   ≤1 minimap repaint per animation frame; node lookup
                     O(deg) via cached Map for the duration of a drag
```

**Changes**

| # | Where | What |
|---|---|---|
| 1 | `server/skills.py::list_skills` | Wrapped with TTL+mtime cache (60 s). Fingerprint stat()s only the top-level `~/.claude/skills/` and `~/.claude/plugins/marketplaces/*` dirs (cheap), so a freshly edited skill invalidates immediately. New `force_refresh` kw. |
| 2 | `server/commands.py::list_commands` | Same TTL+mtime cache pattern (60 s). |
| 3 | `server/routes.py` | New `_q_truthy(q, key)` helper; `/api/skills` and `/api/commands` now forward `?refresh=1` to bypass the cache. |
| 4 | `dist/index.html::_wfScheduleMinimap` (new) | Coalesces minimap repaints into one rAF tick. Replaces the inline rAF block inside `_wfRenderCanvas`. |
| 5 | `dist/index.html::onMove` | Drag handler swaps `_wfRenderMinimap()` (sync, ~100/s) for `_wfScheduleMinimap()` (≤60/s). Caches the dragged node reference on `drag._node` (no `nodes.find()` per mousemove). |
| 6 | `dist/index.html::_wfUpdateNodeTransform` | Builds a `nodeId → node` `Map` and a `nodeId → edges[]` adjacency map once, caches them on `__wf.drag` for the drag lifetime. Per-frame cost: O(N×deg) → O(deg). |

**Verification**
```
JS smoke         : 6 script blocks parse OK
e2e-tabs-smoke   : 58/58 (one flaky AFTER.sessions retry — re-run clean)
GET /api/skills?refresh=1   : bypasses cache (force re-scan)
backend cold/warm           : as measured above
```

**Compatibility**
- Caches are process-memory only; `force_refresh` defaults to `False` so all existing call sites are unchanged.
- `_wfScheduleMinimap` is the same idempotent-rAF pattern already used elsewhere; no new minimap behavior.
- Drag-time Maps are scoped to `__wf.drag` and discarded on drag end; no leaks.

---
## [2.43.0] — 2026-04-28

### 🛠️ Setup Helpers — global ↔ project scope across the board

User: "지금 세팅을 도와주는 것들이 필요해. 예를 들어서, claude MD도 global,
프로젝트별로 할 수 있어야해." Followed by "C로 가자." — full package across
six setup surfaces. Until now most config tabs only edited the global
`~/.claude/` files; project-scope (`<cwd>/.claude/`) was either read-only
(CLAUDE.md) or completely missing (settings, settings.local, skills,
commands). This release ships parity.

**Added — backend (`server/projects.py` + `server/routes.py`)**

| Endpoint | Purpose |
|---|---|
| `GET/PUT /api/project/claude-md` | `<cwd>/CLAUDE.md` |
| `GET/PUT /api/project/settings` | `<cwd>/.claude/settings.json` (committed) |
| `GET/PUT /api/project/settings-local` | `<cwd>/.claude/settings.local.json` (gitignored personal overrides) |
| `GET /api/project/skills/list` | list project skills |
| `GET/PUT /api/project/skill` | one skill (creates `.claude/skills/<id>/SKILL.md`) |
| `POST /api/project/skill/delete` | remove skill dir |
| `GET /api/project/commands/list` | list project commands |
| `GET/PUT /api/project/command` | one command (sub-paths via `:`, e.g. `review:critical`) |
| `POST /api/project/command/delete` | remove command file |

Every handler resolves `cwd` via `_validate_project_cwd` — must be a real directory under `$HOME` or the call returns `invalid or out-of-home cwd`. Permission rules go through the existing `sanitize_permissions` so an invalid `:*` mid-pattern is auto-fixed exactly like the global `put_settings` path. Path-traversal guard on commands re-resolves the final path and refuses anything outside `<cwd>/.claude/commands/`.

**Added — frontend (`dist/index.html`)**

- Shared `_renderConfigScopeToggle` widget + `state.data.cfgScope`/`cfgCwd`/`cfgSettingsKind` so the user picks scope once and it sticks across tabs.
- **CLAUDE.md tab**: 🌐 Global / 📁 Project toggle + project picker. Save dispatches to the right endpoint.
- **Settings tab**: same scope toggle; in project mode adds a sub-toggle for `settings.json` (committed) vs `settings.local.json` (personal). Recommendation profiles only show in global mode.
- **Skills tab**: project mode lists `<cwd>/.claude/skills/*` only. ＋ New skill creates a directory + seeded `SKILL.md`. Cards open a project-aware editor.
- **Commands tab**: project mode lists `<cwd>/.claude/commands/**/*.md`. ＋ New command, click-to-edit, delete.
- **Hooks tab**: project mode shows a header card summarising project hook counts in `settings.json[hooks]` and `settings.local.json[hooks]`, with a one-click jump to the Settings tab for editing (project hooks are stored inside settings.json, so the JSON shape stays authoritative there).

**Verification**

```
backend smoke (curl)
  /api/project/claude-md?cwd=$HOME/claude-dashboard   → 200, raw len ≈ 7000
  /api/project/settings?cwd=...                       → 200, exists=false (no .claude/)
  /api/project/settings-local?cwd=...                 → 200, parses real allow rules
  /api/project/claude-md?cwd=/tmp                     → 400 invalid or out-of-home cwd
  PUT round-trip (CLAUDE.md / settings / skill)       → all atomic, files written
  path traversal (id="../etc")                        → 400 invalid command id

frontend smoke (Playwright)
  claudemd / settings / skills / commands / hooks     → all render, 0 console errors

regression
  e2e-tabs-smoke.mjs                                  → 58/58
  make i18n-verify                                    → 0 missing across 4135 keys × 3 langs
```

**Compatibility**

- All new endpoints are additive — old API routes unchanged.
- Frontend default scope is `global`, preserving existing flows. Existing global-only callers don't need to know about scope.
- Project paths must resolve under `$HOME` — same sandbox the rest of the app uses.

---
## [2.42.3] — 2026-04-28

### 🩹 Hooks tab — 2 s initial load + delete didn't refresh UI

User: "훅 부분이 처음에 로딩이 너무 많이 걸려. 그리고 삭제해도 삭제가 안되는
것 같아." Two distinct bugs in the Hooks tab — both confirmed end-to-end.

**Root causes**

1. `VIEWS.hooks` blocked initial paint on `/api/hooks/recent-blocks`, which
   walks up to 60 jsonl transcripts (~90 MB on a power user's machine) and
   took 1.94 s. Cold cost was paid on every visit, even on filter
   re-renders.
2. `deleteHook()` fired the API call, showed a success toast, then did
   nothing — no `renderView()` call. The deleted hook stayed visible
   until the user navigated away, looking like delete was broken.

**Changes**

| # | Where | What |
|---|---|---|
| 1 | `server/hooks.py::recent_blocked_hooks` | TTL+mtime cache (5 min). Fingerprint is just the newest jsonl mtime, so a single `stat()` invalidates correctly without rescanning. New `force_refresh` param + `?refresh=1` on `api_recent_blocked_hooks`. Cold 0.97 s → warm 0.026 s (~37×). |
| 2 | `dist/index.html::VIEWS.hooks` | Drop `/api/hooks/recent-blocks` from the initial `Promise.all`. Module-level `__hooksRecentBlocks` cache survives filter re-renders; the panel renders into a `#hooksRecentBlocksHost` placeholder that fills in after first paint. |
| 3 | `dist/index.html::AFTER.hooks` | Lazy fetch `/api/hooks/recent-blocks` once per page session and inject HTML via the new `_renderRecentBlocksPanel(data)` helper (extracted from the inline template). |
| 4 | `dist/index.html::deleteHook` | Call `renderView()` on success for both plugin and user delete paths so the deleted hook actually disappears. Toast strings now go through `t()`. |

**Verification**

```
Cold blocking work:  1.94 s   →  0.05 s   (Hooks tab feels instant)
Recent-blocks cold:  0.97 s   (deferred — happens after first paint)
Recent-blocks warm:  0.026 s  (cache hit, 37× faster)
e2e-tabs-smoke.mjs:  58/58
Headless DOM probe:  __hooksRecentBlocks populates within 2 s, host
                     div fills with 5 items, 0 console errors.
make i18n-verify:    0 missing across EN/ZH
```

**Compatibility**

- `recent_blocked_hooks(force_refresh=False)` keeps the previous default;
  callers passing only `max_files` / `top_n` are unchanged.
- The cache is per-process (in-memory only); restarting the server clears it.

---
## [2.42.2] — 2026-04-27

### 🖥️ Workflow node spawn → matching provider CLI

User: "워크플로우에서 Builder나 Reviewer을 누르면 해당 AI의 cli가 아니라
클로드 코드가 새로 열려. 지금 진행중인 AI cli가 열려야해." Every node's
🖥️ button on the workflow canvas was hard-wired to `claude` regardless of
the node's `assignee`, so a node assigned to `@gemini:gemini-2.5-pro` or
`@ollama:llama3.1` would still launch Claude Code.

| # | Where | What |
|---|---|---|
| 1 | `server/actions.py::_resolve_provider_cli` (new) | Maps `provider:model` (`claude:opus` / `gemini:gemini-2.5-pro` / `ollama:llama3.1` / `codex:o4-mini` + aliases like `anthropic` / `google` / `openai` / `gpt`) to `{provider, bin, args, model}`. Uses the existing `_which()` 11-path fallback to find each CLI. When the requested CLI isn't installed, it returns claude with a `fallback_reason` so the user gets a warning toast instead of a silent re-route. |
| 2 | `server/actions.py::api_session_spawn` | Now accepts `body.assignee`. For Claude (the only TUI that takes a positional prompt without exiting), the prompt is appended as before. For Gemini / Ollama / Codex, the prompt is printed as a banner (`echo '── Prompt ──'; printf …`) before launching the interactive REPL — passing it as a positional would have caused those CLIs to one-shot and exit. Response now carries `provider` / `cli` / `model` / `fallbackReason`. |
| 3 | `dist/index.html::_wfSpawnSession` | Sends `n.data.assignee` in the spawn body; success toast becomes provider-aware (`Gemini 세션 시작됨 (gemini-2.5-pro)`); a fallback uses a `warn` toast that surfaces `fallbackReason`. |

#### Verification
```
_resolve_provider_cli('claude:opus')        → claude-cli, /Users/o/.local/bin/claude
_resolve_provider_cli('gemini:gemini-2.5-pro') → gemini-cli, /Users/o/.nvm/.../bin/gemini, --model 'gemini-2.5-pro'
_resolve_provider_cli('ollama:llama3.1')    → ollama, /opt/homebrew/bin/ollama, run 'llama3.1'
_resolve_provider_cli('codex:o4-mini')      → claude-cli (codex not installed) + fallback_reason
JS smoke (6 blocks): parses OK
```

#### Compatibility
- Body without `assignee` (e.g. existing chat Spawn buttons elsewhere in the
  app) still routes to Claude — old callers unchanged.
- `claude` flags (`systemPrompt` / `allowedTools` / `--resume`) are only
  appended on the claude-cli path; non-Claude CLIs ignore them.

---
## [2.42.1] — 2026-04-27

### 🔄 Workflow run visibility — list cards + canvas auto-restore

User: "워크플로우 실행결과랑 현재 실행중인지? 그리고 어느 노드에 실행중인지
인터렉티브하게 보여줘야해. 지금 기록을 볼수 없으니까 쓸수가 없어." Backend
already had per-run state (`runs[runId].nodeResults[nid]`) but the workflow
list cards rendered no run history at all, and re-opening the canvas of a
running workflow showed an idle topology — the SSE poller only started after
a fresh `Run` click. So users couldn't tell which workflows were live, which
had finished, or which had failed without opening each one.

| # | Where | What |
|---|---|---|
| 1 | `server/workflows.py::api_workflows_list` (+35 LoC) | Each workflow item now carries `lastRuns` (last 3 runs with `runId/status/startedAt/finishedAt/durationMs/currentNodeId/error`), `runningCount` (number of in-flight runs), `activeRunId` (most recent running run, if any), and `totalRuns`. Reads from the existing `runs` map — no schema migration. |
| 2 | `dist/index.html::_wfRenderList` (+~30 LoC) | List cards now show inline status chips (✅ ok / ❌ err / ⏳ running) for the last 3 runs, a pulsing `● 실행 중` badge if any run is in flight, and `(N회)` total count. Empty state shows `실행 기록 없음` instead of nothing. `_runIcon`/`_runColor` helpers. |
| 3 | `dist/index.html::_wfOpen` (+~15 LoC) | When entering a canvas, auto-restore: if `activeRunId` exists, attach `__wf.runId` and start `_wfStartPolling()` so node colors animate live; otherwise fetch the latest finished run via `/api/workflows/run-status` and `_wfApplyRunStatus()` to hydrate node colors one-shot. Wrapped in try/catch so a stale runId never blocks canvas rendering. |
| 4 | `tools/translations_manual_20.py` (new) | KO → EN/ZH for `실행 기록 없음` / `실행 중` / `회`. |

#### Verification
```
GET /api/workflows/list                     →  200, 3 wf, lastRuns/runningCount/activeRunId/totalRuns present
UI smoke (renderView WF list)               →  3 cards, 3 chip blocks, "실행 기록 없음" copy rendered
e2e-hyper-projects-and-sidebar.mjs          →  11/11
e2e-tabs-smoke.mjs                          →  58/58
make i18n-verify                            →  0 missing across EN/ZH
```

#### Compatibility
- Backend payload only adds fields. Older `dist/index.html` ignores them.
- Polling cadence unchanged; we reuse the existing 1-Hz SSE-style loop.

---
## [2.42.0] — 2026-04-27

### 🖱️🧩🧭🔁 Four Anthropic features in one release — Computer Use / Memory / Advisor / Routines

User asked which of `advisor tool` / `claude code routines` / `managed
agents memory` / `computer use` were already in the dashboard. Answer
was: 0 fully, 2 partially, 2 missing. This release fills the gap with
**all four**, each as its own playground tab + backend module.

| # | Where | What |
|---|---|---|
| 1 | `server/computer_use_lab.py` (new, ~210 LoC) | Anthropic `computer-use-2025-01-24` beta tool playground. POSTs to `https://api.anthropic.com/v1/messages` with the `computer_20250124` tool definition + optional base64 screenshot, then surfaces the model's tool_use plan (sequence of `screenshot` / `key` / `mouse_*` calls). **Plan-only — the dashboard never moves the user's mouse or keyboard.** Validates screenshot path stays under `$HOME`, clamps screen size to (320..3840, 240..2160), per-call cost calc against bundled price table, history capped at 50. |
| 2 | `server/memory_lab.py` (new, ~190 LoC) | Anthropic `memory-2025-08-18` beta playground. POSTs with `memory_20250818` tool, walks the response for `tool_use` blocks named `memory`, extracts every `op` (create/read/update/delete) into `memoryEvents`. New `api_memory_lab_blocks` aggregates observed memory blocks across history into a `{key:value}` snapshot so the user can see "what does the model remember about me?" without spelunking through Anthropic's server-side store. |
| 3 | `server/advisor_lab.py` (new, ~240 LoC) | Pair a fast/cheap **executor** (Haiku 4.5 / Sonnet) with a smart/slow **advisor** (Opus). Sends the prompt to the executor first, then sends `User request + Executor draft` to the advisor with system prompt "review this draft", and surfaces both responses + a `delta {tokensDiff, costDiff, latencyDiff}` so the user can decide when the Opus tax is worth it. |
| 4 | `server/routines.py` (new, ~210 LoC) | **Full CRUD over `~/.claude/scheduled-tasks/<name>.yaml`** (the existing tab was listing-only). Tiny line-based YAML extractor (no PyYAML — stdlib only) for `name/description/schedule/command/cwd/enabled`. Run-now endpoint uses `subprocess.run(shell=True, timeout=120)` with a strict cwd-under-`$HOME` guard; rejects anything outside. Stdout/stderr capped at 4 KB per stream. Dry-run mode returns the resolved command + cwd without executing. |
| 5 | `server/routes.py` | Wired all 14 new endpoints — list/examples/history/run for each lab, plus get/save/delete for routines. Item-route added for `/api/routines/get/<name>`. |
| 6 | `dist/index.html` `NAV` | 4 new tabs — `computerUseLab` / `memoryLab` / `advisorLab` (playground group), `routines` (config group). Each renders a compact form: example chips, prompt textarea, model select, ▶ Run button, results card, history block. |
| 7 | `dist/index.html` `VIEWS.*` | Compact view implementations (~80 LoC each): inline `_cuRun()` / `_mlRun()` / `_alRun()` / routines `_routineEdit/_routineSave/_routineRun/_routineDelete` handlers. Routines tab also has a full edit modal. |
| 8 | `tools/translations_manual_19.py` (new) | KO → EN/ZH for every new label, button, toast, confirm. `make i18n-refresh` passes 0 missing across 4012+ keys × 3 languages. |

#### Live verification
```
GET /api/computer-use-lab/examples →  200  (5 presets, 4 models)
GET /api/memory-lab/examples       →  200  (5 presets)
GET /api/routines/list             →  200
GET /api/advisor-lab/models        →  200  (3 executors, 2 advisors)
UI: all 4 view headers render with 0 console errors:
  🖱️ Computer Use Lab · 🧩 Memory Lab · 🧭 Advisor Lab · 🔁 Claude Code Routines
```

#### Compatibility
- All 4 modules are self-contained — no schema or DB migration.
- `_anthropic_key()` reads from the existing `aiProviders` tab key store
  (or env `ANTHROPIC_API_KEY` via that store). Without a key the labs
  surface `needKey: true` instead of crashing.
- `routines.py` rejects `cwd` outside `$HOME` so a stray YAML can't
  point the run-now endpoint at a system path.

#### Per-feature pricing (USD per 1M tokens)
- haiku-4-5: 1.0 / 5.0
- sonnet-4-5/4-6: 3.0 / 15.0
- opus-4-6/4-7: 15.0 / 75.0

---
## [2.41.0] — 2026-04-27

### 👥 Agent Teams + 🤝 Recent sub-agent activity (with one-click CLI)

Two new affordances on top of the existing Agents tab and Project Detail
modal — both born from the user's request to (a) "bundle agents that
go together" and (b) "see what work session A delegated to its sub-agents
and re-open the matching CLI."

| # | Where | What |
|---|---|---|
| 1 | `server/agent_teams.py` (new, ~280 LoC) | Whitelisted schema for saved teams. Each team is `{id: tm-<hex>, name, description, agents: [{name, scope, cwd, role, task}], createdAt, updatedAt}`. Atomic JSON persistence at `~/.claude-dashboard-agent-teams.json` (env override `CLAUDE_DASHBOARD_AGENT_TEAMS`). Members reference existing agents — the store doesn't duplicate the agent body, so renaming/deleting an agent reflects immediately on the next list. `_agent_exists()` resolves global / project / builtin / plugin scopes via `get_agent` + filesystem checks; missing members surface as `exists:false` + a per-team `missingCount`. |
| 2 | `server/agent_teams.py` `api_agent_teams_*` | Five routes wired through `routes.py`: `GET /api/agent-teams/list`, `GET /api/agent-teams/get/<tm-id>`, `POST /api/agent-teams/save` (create or update), `POST /api/agent-teams/delete`, `POST /api/agent-teams/spawn`. The spawn route returns one descriptor per existing member (`{name, scope, role, cwd, prompt, claudeCmd}`) and a `skipped` array for missing agents. The dashboard either drives `api_session_spawn` per descriptor or surfaces the descriptors as copy-pasteable `claude /agents <name> "<prompt>"` strings. |
| 3 | `server/projects.py::api_project_detail` | Response gains `subagentActivity: [{sessionId, ts, tool, agent, inputSummary, hadError, turnTokens, cwd}, ...]` mined from the existing `tool_uses` SQLite table (last 50 sessions for this cwd, top 60 delegations by recency). No new schema — reuses what `index_all_sessions` already captures, so projects with prior session history light up immediately. |
| 4 | `dist/index.html` Agents tab — Teams section | New card grid above the search bar: 👥 Agent Teams. Each card lists members as chips (📁 marker for project-scoped), shows a missing count when relevant, and exposes 🚀 Spawn / Edit / Delete. The editor modal pre-fills name + description + multi-select members from `state.data.agents.agents`. |
| 5 | `dist/index.html` Agents tab — Spawn flow | Clicking 🚀 opens a modal listing every member's resolved `claude /agents <name>` invocation in a copy-friendly `<pre>`, plus a Skipped panel for any member whose underlying agent file is gone. |
| 6 | `dist/index.html` Project Detail modal — `🤝 Recent sub-agent activity` | New section in the right column. Activity entries are grouped by source `sessionId` so the user sees "session A → 3 agents" at a glance. Each group expands to per-delegation rows (agent chip + input preview + token cost + error flag). Clicking the group's 🖥 CLI button drives `/api/session/spawn` to bring up Terminal.app on that session's resume command. |
| 7 | `tools/translations_manual_18.py` (new) | KO → EN/ZH for every Teams + activity label/button/toast. `make i18n-refresh` passes 0 missing across 4012+ keys × 3 languages. |

#### Live measurement
```
POST /api/agent-teams/save → {ok:true, isNew:true, id:"tm-0b58fbf7", agents:2}
GET  /api/project/detail   → {subagentActivity:[11 entries],
                              top: { agent:"Explore", tool:"Agent",
                                     inputSummary:"Scan codebase for ...",
                                     sessionId:"2aa992bf..." }}
```

#### Compatibility
- Backend additions only. Existing `/api/project/detail` shape strictly
  extends — every prior key (`cwd`, `name`, `repo`, `claudeJsonEntry`,
  `sessions`, `stats`) is unchanged; only the new `subagentActivity` key
  is added.
- No SQLite migration — the activity panel reads `tool_uses` rows that
  `server/sessions.py` was already inserting since v2.x.
- Teams store is brand-new (`~/.claude-dashboard-agent-teams.json`); first
  write creates it.

#### Verification
- Live API: agent-teams save/list round-trip; project-detail surfaces
  11 sub-agent delegations with correct grouping.
- UI smoke (Playwright eval): teamsGrid renders 1 saved team · all
  helper globals present · 0 console errors.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

---
## [2.40.5] — 2026-04-27

### 🩹 Hotfix — Recent Blocks / Detective chips were unclickable (HTML quoting bug)

User reported: "Clicking the Recent Blocks card does nothing." Root
cause: in v2.40.4 the inline onclick attribute embedded
`JSON.stringify(rb.id)` directly:

```html
<button onclick="state.data.hooksFilter=${JSON.stringify(rb.id)}; …">
```

`JSON.stringify` returns a double-quoted string (`"pre:edit-write:..."`),
which collided with the surrounding `onclick="…"` attribute quotes — the
HTML parser cut the attribute short at the first inner `"`, dropped the
remainder onto the element as garbage, and the click handler never ran.
Same bug in the Detective result chips.

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` Recent Blocks card | Replaced inline onclick payload with `data-hook-id="${escapeHtml(rb.id)}"` + `onclick="_jumpToHookCard(this.dataset.hookId)"`. No more double-quote collisions; the id flows through `dataset` which the browser decodes for us. |
| 2 | `dist/index.html` Detective chip | Same change — `data-hook-id` + `_jumpToHookCard` handler. The two surfaces now share one entry point. |
| 3 | `dist/index.html` (new) `_jumpToHookCard(id)` | Single helper used by both call sites: clears scope/event/risk filters so the searched id is the sole result, sets `state.data.hooksFilter`, re-renders, then `setTimeout(_pulseHookCard, 200)`. Centralising the logic also gives one place to extend (e.g. analytics, deep-link). |

#### Live verification
```
BEFORE click: { helperFn:true, cards:5, firstId:'pre:edit-write:gateguard-fact-force', filter:'(none)' }
AFTER  click: { filter:'pre:edit-write:gateguard-fact-force', visibleCards:6 }
```

Filter applied, target card rendered, pulse fired.

#### Compatibility
- Frontend-only patch. No backend, schema, or route changes.
- `_jumpToHookCard` is a new global; existing `_pulseHookCard` and
  `state.data.hooksFilter` shapes unchanged.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

---
## [2.40.4] — 2026-04-27

### 🔬 Hook Detective + 🚨 Recent Blocks + 🧬 Dispatcher decoder

User asked: "How did you know which hook was blocking? Show me the same
clues inside the dashboard." This release ships A + B + C — three
additive UI affordances on top of the v2.40.2/.3 hooks tab so the user
can answer that question without reading log lines:

| # | Where | What |
|---|---|---|
| 1 | `server/hooks.py` (new `recent_blocked_hooks` + `_scan_jsonl_for_hook_blocks`) | Walks the most recent 60 jsonl transcripts under `~/.claude/projects/<slug>/*.jsonl`, line-scans for hook block markers ("hook returned blocking error", "PreToolUse:", etc.), and harvests every `pre\|post\|session\|notification\|user\|stop\|sub:<scope>:<name>` shape. Aggregates by frequency × last-seen mtime. **No JSON parser required** — the regex line-scan is robust to nested escaping inside tool_result content. New route `GET /api/hooks/recent-blocks` returns `{items, scanned, totalEvents}`. Live measurement on this dev box: 60 files scanned, 14 events, top entry `pre:edit-write:gateguard-fact-force × 4`. |
| 2 | `dist/index.html` `VIEWS.hooks` — **🔍 Hook Detective box** | Pasted-text introspector at the top of the hooks tab. Type or paste any block-error message; a regex extracts every hook id pattern; each id renders as a clickable chip. Clicking a chip auto-applies the search filter, scrolls the matching card into view, and pulses it (3 cycles of a blue ring). Backed by `_pulseHookCard()` — no other UI helper changed. |
| 3 | `dist/index.html` `VIEWS.hooks` — **🚨 Recent Blocks panel** | Renders the v2.40.4 backend output as one card per hook id with `<count>×` and last-seen timestamp. Clicking a card sets the search filter and triggers the same pulse as Detective. Panel only renders when `recentBlocks.items.length > 0`, so unblocked sessions don't see the section. |
| 4 | `dist/index.html` `openHookDetail()` + `_decodeHookCommand()` | New 🔬 **Detail** button on every hook card. Modal shows: synthesised display name, description, every metadata row (event/matcher/scope/source/pluginKey/type/timeout), the **decoded dispatcher chain** as a left-to-right pipeline of chips (`node` → runner → `<hook id>` → handler → flags), and the full raw command in a scrollable `<pre>`. The command decoder accepts the canonical `node -e "...require(s)" node <runner> <hookId> <handler> <flags>` shape used by ECC and falls back to a standalone hook-id match for shell-only entries. |
| 5 | `tools/translations_manual_17.py` (new) | KO → EN/ZH for Detective box, Recent Blocks panel, Detail modal labels, dispatcher-chain chips, raw-command label. `make i18n-refresh` reports 0 missing across 4012+ keys × 3 languages. |

#### How it composes with v2.40.2/.3
- v2.40.2 added the search/filter/panic; v2.40.3 surfaced `id` as the
  card title; v2.40.4 layers on the introspection (Detective, Recent
  Blocks, Detail). All four levels are additive — disabling any one
  doesn't break the others.
- The Recent Blocks card and Detective chip both use the same handler
  (`state.data.hooksFilter = id; renderView(); _pulseHookCard()`), so
  the user gets a consistent "click → land on the hook" experience.

#### Verification
- Live route: `curl /api/hooks/recent-blocks` → `{ok:true, scanned:60,
  totalEvents:14, items:[...]}` with `pre:edit-write:gateguard-fact-force`
  × 4 at the top.
- Live UI: hooks tab renders Detective input · Recent Blocks 5 cards ·
  41 detail buttons · 0 console errors.
- Detective paste roundtrip: paste a fragment containing
  `pre:edit-write:gateguard-fact-force` → result HTML contains the chip;
  click → search applied · card pulsed.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

#### Compatibility
- `server/hooks.py` adds new helpers and a new route; existing
  `get_hooks` / `api_plugin_hook_update` shapes unchanged.
- Recent-blocks scan is read-only and bounded (60 files × ~1.5 MB cap
  per file), so even on a project with many transcripts it adds ≤200 ms
  to the hooks tab fetch.
- All UI additions are gated on data presence — empty Recent Blocks
  panel is hidden, Detective shows nothing until text is pasted.

---
## [2.40.3] — 2026-04-27

### 🏷️ Hook names — surface the same identity Claude Code's `/hooks` shows

User reported: "the hook names aren't showing — the names from `/hooks`
should be visible." Plugin hooks.json keeps `id` (and sometimes `name` /
`description`) at the **group level** alongside `matcher` and `hooks`,
e.g. `{ "matcher": "Bash", "hooks": [...], "id": "pre:bash:dispatcher",
"description": "..." }`. The dashboard's `_collect()` was already
copying every key off the **sub**-hook dict — but the human-readable
identity lives one level up, so cards lost it.

| # | Where | What |
|---|---|---|
| 1 | `server/hooks.py::_scan_plugin_hooks::_collect` | When a sub-hook entry doesn't already define `id` / `name` / `description`, propagate the group-level item's value. `description` was already partially propagated; `id` and `name` are the new propagations and the missing piece. |
| 2 | `server/hooks.py::get_hooks` | Same propagation for **user** hooks in `~/.claude/settings.json` — they too can carry `id` / `name` / `description` at the group level. |
| 3 | `dist/index.html` `renderUserCard` / `renderPluginCard` | Card header now shows the synthesised display name in `font-semibold mono` as the primary identifier. Priority: explicit `id` → explicit `name` → derived `<event> · <matcher>` (or `<event> · (no matcher)` when matcherless). The existing scope/source chips and matcher rows remain underneath. |
| 4 | (existing search) | The hooks-tab search bar already indexed `id` from v2.40.2, so once the field is populated the search just works — typing `pre:bash:dispatcher` instantly narrows to 1 card. |

#### Effect (live measurement)
```
GET /api/hooks  →  41 entries · 26 with id/name
First titles rendered:
  pre:bash:dispatcher                  (PreToolUse/Bash)
  pre:write:doc-file-warning           (PreToolUse/Write)
  pre:edit-write:suggest-compact       (PreToolUse/Edit|Write)
  session:start
  session:end:marker
Search "pre:bash:dispatcher" → 1 card
```

#### Compatibility
- No new fields introduced on the wire; same `/api/hooks` shape, just
  more keys surfaced per entry when the source hooks.json defines them.
- No frontend break for hooks without `id`/`name` — they fall back to
  the derived `<event> · <matcher>` string.
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-tabs-smoke.mjs`                          — 58/58

---
## [2.40.2] — 2026-04-27

### 🚨 Hooks tab — emergency UX (search · filter · risk chip · panic disable)

User reported "100+ hooks installed but the dashboard doesn't show them /
no way to disable specific ones." The hooks API was already returning
everything (1 user + ~120 plugin hooks across many marketplaces) but the
UI dumped them all as a flat per-event list with no search/filter, so the
ones causing actual blocked work (PreToolUse + Edit/Write/Bash matchers)
were impossible to find and kill quickly.

| # | Where | What |
|---|---|---|
| 1 | `dist/index.html` `VIEWS.hooks` | **Always-visible filter bar** above the per-event grouping: full-text `<input>` over matcher · command · plugin · description · id; scope chips (All / User / Plugin); per-event chips (PreToolUse / PostToolUse / SessionStart / …); risky-only checkbox; "✕ Clear filter" appears as soon as any filter is set. Live counter shows `<shown>/<total>`. |
| 2 | `VIEWS.hooks` | **🚨 Risk chip + danger highlight** on every card whose event is `PreToolUse` and whose matcher matches `Edit\|Write\|Bash\|MultiEdit\|NotebookEdit`. Chip lives next to the existing scope badge so users can spot the offenders at a glance, even before searching. |
| 3 | `VIEWS.hooks` header | **🚨 Bulk-disable button** appears whenever ≥1 risky hook exists. Asks for confirmation with the exact count, then walks every matching entry: user hooks → `PUT /api/settings` with the `PreToolUse` matcher entries filtered out; plugin hooks → `POST /api/hooks/plugin/update {op:'delete'}` per entry, descending by (groupIdx, subIdx) so removing earlier entries doesn't shift later indices. Reports `<userRemoved> · <pluginRemoved>` (and any `failed` count) in a single toast. |
| 4 | `dist/index.html` `AFTER.hooks` | New hook lifecycle wires the search input (180 ms debounced) and the risky-only checkbox to `state.data.*` and re-renders. |
| 5 | `tools/translations_manual_16.py` (new) | KO → EN/ZH for every new label, chip, tooltip, and confirm. Bare common words ("전체"/"이벤트"/"실패") already mapped earlier; manual_16 adds the hooks-specific ones. `make i18n-refresh` reports 0 missing across 4012+ keys × 3 languages. |

#### What this lets the user do, immediately
- Type "fact-force" or any other plugin hook id — the list filters in real time.
- Tick "🚨 위험 훅만" to surface only the PreToolUse + Edit/Write/Bash hooks
  that are most likely to be the cause of blocked work.
- Click **🚨 위험 훅 일괄 비활성화** to delete every such hook in one
  confirmed click — both user and plugin entries.
- Each card still has its own [수정] / [삭제] buttons (already shipped); the
  panic button is a shortcut, not a replacement.

#### Compatibility
- No backend changes. Existing routes (`/api/hooks` / `/api/settings` PUT /
  `/api/hooks/plugin/update`) handle the panic flow.
- Filter state lives in `state.data.hooks{Filter,Scope,Event,RiskOnly}` —
  not persisted, intentionally (resets on tab leave so users don't have a
  stale filter on next visit).
- Plugin hook deletion still rewrites the plugin's `hooks/hooks.json`
  in place; reinstalling the plugin restores it. No marketplace-side
  side effects.

#### Verification
- e2e regression — **0 failures**:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40)  — 11/11
  - `e2e-quick-settings.mjs` (v2.38)              — 6/6
  - `e2e-tabs-smoke.mjs`                          — 58/58
- Live UI smoke (Playwright eval): hooks tab renders search input · risky-only
  checkbox · panic button · 16 risk chips · 41 cards · 0 console errors.

---
## [2.40.1] — 2026-04-27

### 🚀 Performance hotfix — gzip + defer + fetch dedupe

User-reported lag. Three additive perf wins, no behaviour changes:

| # | Where | What |
|---|---|---|
| 1 | `server/routes.py::_send_static` | **mtime-keyed in-memory cache + on-the-fly gzip** for static responses (text/* / JS / CSS / JSON / SVG). `Accept-Encoding: gzip` from any modern browser triggers compression; raw bytes still served to clients that don't advertise gzip. **`dist/index.html` 1.12 MB → 270 KB on the wire** (76% smaller). Cache invalidates automatically on file mtime change so no manual restart is needed during development. |
| 2 | `dist/index.html` `<head>` | **`defer` on Chart.js / vis-network / marked** CDN scripts. None of them are touched by the inline boot script — they're only used inside specific views — so deferring them removes ~600 KB of parser-blocking from first paint. Views that need them (overview/analytics/agents/artifacts) work as before because `defer` finishes before `DOMContentLoaded`. |
| 3 | `dist/index.html` `api()` helper | **In-flight GET dedupe**. Many views fan out the same fetch on entry (e.g. `/api/agents` from agents tab + chatbot prompt rebuild). A `_apiInflight` Map coalesces concurrent identical GETs into one network request, halving boot-time fan-out with zero behaviour change. |
| 4 | `dist/index.html` sidebar | **`requestAnimationFrame` debounce on `renderNav()`** when `toggleFavoriteTab` fires. Rapid ★ toggles (or recent-tab MRU updates from successive `go()` calls) used to each rebuild the entire sidebar on the same tick; now they coalesce into the next animation frame. |

#### Verification
- HTML payload measured: 1,120,949 B raw → 270,609 B gzipped (`curl --compressed`).
- All four globals present after defer (`window.Chart`, `window.vis`, `marked`, `_apiInflight`, `_scheduleRenderNav`).
- e2e regression sweep — **0 failures** across:
  - `e2e-hyper-projects-and-sidebar.mjs` (v2.40 — 11/11)
  - `e2e-hyper-agent.mjs` (v2.39 — 7/7)
  - `e2e-quick-settings.mjs` (v2.38 — 6/6)
  - `e2e-tabs-smoke.mjs` — **58/58**

#### Compatibility
- Server cache holds `(mtime, raw, gzipped|None)` per resolved path; lifetime is the process. No disk write. Memory cost is bounded by the dist tree size (~few MB).
- Clients that don't send `Accept-Encoding: gzip` (rare, mostly raw HTTP probes) still get uncompressed bytes.
- No new files; no schema changes; no env var changes.

---
## [2.40.0] — 2026-04-27

### ⚡ Hyper Agent → project-scoped sub-agents · 🧭 Sidebar discovery (Favorites + Recent + `/`)

Two upgrades shipped together:

**(A) Hyper Agent now works on project-scoped sub-agents** (`<cwd>/.claude/agents/<name>.md`).
The same toggle / objective / refine targets / dry-run / rollback flow that
v2.39.0 introduced for global agents is now available per-project, with each
project's meta tracked independently — even when a global agent and a project
agent share the same name.

**(B) Sidebar discovery aids** — for users who said "categories are too many,
hard to find things." Three additive changes (no category restructure):

| # | Where | What |
|---|---|---|
| 1 | `server/hyper_agent.py` | Composite key namespace — `global:<name>` for global, `project:<sha8(cwd)>:<name>` for project. Legacy v2.39.0 flat keys are still read as global; subsequent writes auto-migrate to canonical. Every public function (`configure_agent` / `refine_agent` / `apply_proposal` / `rollback` / `get_hyper` / `history` / `toggle_agent`) now accepts an optional `cwd: str | None = None`. `_is_writable_agent` skips builtin/plugin only when scope is global; project scope is writeable when the file exists. Per-iteration `.bak.md` backup lives in the same scope as the agent. |
| 2 | `server/hyper_agent.py` | Two new POST endpoints `/api/hyper-agents/get` and `/api/hyper-agents/history` accept a `{name, cwd?}` body — required because cwd doesn't fit a URL path parameter. The original GET path-param routes are kept for global lookups (back-compat). `toggle/configure/refine-now/rollback` already accepted bodies; they now also pull `cwd` from the body. List response gains `key`, `scope`, and `cwd` fields per item. |
| 3 | `server/hyper_agent_worker.py` | After-session trigger now restricts the jsonl scan to the agent's project transcript dir (`~/.claude/projects/<slug>/`, where slug is `<cwd>` with `/` → `-`). A project-scoped agent no longer fires from chatter in unrelated projects. The worker's per-tick loop iterates by composite key and parses scope/name out of it. |
| 4 | `dist/index.html` | `openHyperAgent(name, cwd?)` and the entire modal call chain (`_hyperModalHTML` / `_hyperBindControls` / `_hyperRefineNow` / `_hyperRollback` / `_hyperHistoryRow`) accept `cwd` and route configure/refine/rollback through the cwd-aware POST shape. Project-agents tab cards gain a per-card ⚡ Hyper / ⚡ ON chip wired to `openHyperAgent(name, cwd)`. |
| 5 | `dist/index.html` | **Sidebar Favorites** — every `.nav-item` exposes a ★/☆ toggle on hover. Toggling persists to `prefs.ui.favoriteTabs` (new) which surfaces above the categorical groups as a sticky "★ 즐겨찾기" block — one click to a frequent tab, no flyout to navigate. |
| 6 | `dist/index.html` | **Sidebar Recent** — `go(id)` writes an MRU list to `localStorage['cc-recent-tabs']` capped at `prefs.ui.recentTabsLimit` (default 5). The "🕒 최근 사용" block renders below favorites. Recent items skip duplicates with favorites so the two sections never repeat the same tab. |
| 7 | `dist/index.html` | **`/` opens Spotlight** — pressing `/` alone (when no input is focused) opens the existing Cmd-K spotlight overlay. The header search input's placeholder reads `검색… ⌘K · /` to advertise the shortcut. |
| 8 | `server/prefs.py` | New `list_str` schema kind — list of ASCII identifier strings, dedup'd, capped (`maxItems`, `maxItemLen`). Used by `ui.favoriteTabs`. Also adds `ui.recentTabsLimit: int (0..20, default 5)`. Schema serialiser exposes `maxItems` / `maxItemLen` so the frontend can render constraints without hard-coding. |
| 9 | `tools/translations_manual_15.py` (new) | KO → EN/ZH for "최근 사용", "즐겨찾기 추가/해제", "검색… ⌘K · /". Bare "즐겨찾기" already shipped in manual_11. `make i18n-refresh` reports 0 missing across 4012 keys × 3 languages. |
| 10 | `scripts/e2e-hyper-projects-and-sidebar.mjs` (new) | Playwright integration smoke: global+project twin separation · list scope/cwd surfacing · POST cwd lookup · rollback path · project modal renders saved objective · favorites persisted+rendered · recent surfaces · `/` opens spotlight. **11/11 checks pass.** |

#### Compatibility / migration
- Existing v2.39.0 entries (flat keys like `"reviewer"`) keep working: read as global, automatically migrated to `global:reviewer` on the next configure/refine/rollback.
- v2.39.0's `/api/hyper-agents/get/<name>` and `/api/hyper-agents/history/<name>` GET routes remain — only used for global lookups.
- All routes / UI controls are additive; no behaviour changes for users who don't enable the new features.

#### Why a sidebar redesign?
v2.40.0 deliberately doesn't reshuffle the 6 categories (60 tabs). Restructuring forces relearning. Instead, **discovery aids** layer on top: users pin the tabs they reach for, recents auto-surface the rest, and `/` is one keystroke to a fuzzy search. The same hierarchy stays; the *path* to it shortens.

#### Verification
- `node scripts/e2e-hyper-projects-and-sidebar.mjs` — **11/11**.
- `node scripts/e2e-hyper-agent.mjs` (v2.39 regression) — **7/7**.
- `node scripts/e2e-quick-settings.mjs` (v2.38 regression) — **6/6**.
- `node scripts/e2e-tabs-smoke.mjs` — **58/58**.

---
## [2.39.0] — 2026-04-27

### ⚡ Hyper Agent — sub-agents that self-refine over time

A new opt-in supervisor that periodically asks a meta-LLM (Opus by default)
to propose surgical refinements to a writeable global agent's **system prompt,
tool list, and description**, given the user's stated objective and recent
transcripts that mentioned the agent. Every iteration is applied atomically
with a `.bak.md` backup, so any refinement is one-click reversible.

| # | Where | What |
|---|---|---|
| 1 | `server/hyper_agent.py` (new, ~530 LoC) | Whitelisted schema, strict per-key validation, atomic JSON persistence at `~/.claude-dashboard-hyper-agents.json`. `apply_proposal()` writes `~/.claude/agents/<name>.md` after copying the prior content to `<name>.<ts>.bak.md`. `refine_agent()` calls `execute_with_assignee()` against a hardened meta-system-prompt that returns a strict JSON proposal `{newSystemPrompt, newTools, newDescription, rationale, scoreBefore, scoreAfter}`. `rollback()` restores from any backup snapshot and is itself reversible. |
| 2 | `server/hyper_agent_worker.py` (new) | 60-second daemon loop. Honours four trigger modes: `manual` (never auto-fires), `interval` (every N hours; parsed from `cronSpec` of shape `"0 */N * * *"`, defaults to 6h), `after_session` (fires when ≥`minSessionsBetween` recent jsonl transcripts mention the agent via `"subagent_type":"<name>"` or `@<name>`), `any` (interval OR after_session). |
| 3 | `server/routes.py` | 7 new routes: `GET /api/hyper-agents/list`, `GET /get/<name>`, `GET /history/<name>`, `POST /toggle`, `/configure`, `/refine-now`, `/rollback`. |
| 4 | `server.py` | Boot order extended with `start_hyper_agent_worker()` after `start_auto_resume()`. |
| 5 | `dist/index.html` | Agent cards in the Agents tab gain a per-agent **⚡ Hyper / ⚡ ON** chip (color reflects enabled state, fed from `/api/hyper-agents/list`). Clicking opens a dedicated modal with: master toggle · objective textarea · refine-target checkboxes (systemPrompt / tools / description) · trigger select · provider select · min-sessions / budget USD inputs · spent counter · Save / Dry-run / Refine-now / Rollback. History timeline below the controls renders one card per iteration with cost, tokens, score before→after, applied targets, rationale, expandable diff viewer, and a per-row Rollback button. |
| 6 | `dist/index.html` | `__noReloadPaths` extended with `/api/hyper-agents/` so modal Save/Refine doesn't trigger `_scheduleAutoReload()` (would close the open modal mid-flight). |
| 7 | `tools/translations_manual_14.py` (new) | KO → EN/ZH for every modal label, hint, button, toast, and confirm. Wired into `tools/translations_manual.py`. `make i18n-refresh` reports 0 missing across 4008 keys × 3 languages. |
| 8 | `scripts/e2e-hyper-agent.mjs` (new) | Playwright smoke: seeds a real `~/.claude/agents/hyper-test.md`, then verifies UI globals · list · configure round-trip · get reflects state · toggle off · modal renders saved objective · refine endpoint responds gracefully. **All 7 checks pass.** |

#### Triggers (4)
- **manual** — never auto-fires; only the "⚡ Refine now" button calls `refine_agent`.
- **interval** — N hours since `lastRefinedAt`. N parsed from `cronSpec` ("0 */N * * *"), defaults to 6h.
- **after_session** — at least `minSessionsBetween` jsonl transcripts modified after `lastRefinedAt` AND mentioning the agent. Up to 5 transcripts get fed back into the meta-LLM as context for the proposal.
- **any** — interval OR after_session.

#### Refine targets (3)
- **systemPrompt** — body of the .md file (most common).
- **tools** — frontmatter `tools` list. Restricted to the existing palette via the meta-LLM rules.
- **description** — frontmatter `description`.

#### Safety
- **Read-only protection**: Hyper Agent only applies to writeable global agents. Builtin (general-purpose / Explore / Plan / statusline-setup) and plugin agents are silently skipped — `_is_writable_agent()` returns false.
- **Atomic backup**: every apply copies `<name>.md` to `<name>.<ts>.bak.md` before rewriting. Rollback uses these.
- **Reversible rollback**: rollback itself snapshots the current state to a fresh backup, so a rollback is also reversible.
- **Budget cap**: `budgetUSD` (default $5) — once `spentUSD ≥ budgetUSD`, refinement is skipped with a clear error in `lastError`.
- **Schema clamp**: enum / int / float / bool / str all validated and clamped on every read AND write. Unknown keys silently dropped.
- **History bounded** at 100 entries per agent (FIFO truncation).
- **Dry-run mode**: "Dry-run preview" button calls the meta-LLM but does not write the file — useful to inspect the proposed diff before committing.

#### Migration / compatibility
- New file `~/.claude-dashboard-hyper-agents.json` is created on first configure.
- `~/.claude/agents/<name>.md` is read/written using the same Claude Code-compatible frontmatter shape (`name`, `description`, `model`, `tools`).
- Override the meta path with env `CLAUDE_DASHBOARD_HYPER_AGENTS=/some/path`.
- All endpoints / routes / UI controls are additive — no existing behaviour changed.

---
## [2.38.0] — 2026-04-27

### ⚡ Quick Settings — per-user prefs drawer (UI · AI · Behavior · Workflow)

A single keyboard-accessible drawer (`⌘,` / `Ctrl+,`) exposes every dashboard
parameter. Values persist server-side at `~/.claude-dashboard-prefs.json`,
boot synchronously on every page load, and apply via body `data-*` attributes
so the rest of the app can react via CSS — no rerender needed.

| # | Where | What |
|---|---|---|
| 1 | `server/prefs.py` (new) | Whitelisted schema with 4 sections (UI · AI · Behavior · Workflow), 33 keys total. Strict validation per key — enum check, int/float clamp, str length cap, bool coerce. Unknown keys silently dropped. Atomic JSON writes via `_safe_write`. |
| 2 | `server/routes.py` | 3 new routes: `GET /api/prefs/get` (returns `{prefs, defaults, schema, savedAt}`), `POST /api/prefs/set` (single-key or batch `patch:` form), `POST /api/prefs/reset` (whole or single-section reset). |
| 3 | `dist/index.html` | Slide-in drawer with section tabs + per-control widgets: toggle (bool), segmented (≤4-choice enum), select (>4-choice enum), range (int/float with live readout), text (str). Reads schema from server — no hard-coded constraints. |
| 4 | `dist/index.html` | CSS overrides driven by body `data-*` attrs: `data-density` (compact/comfortable/spacious), `data-font-size` (small→xlarge), `data-reduced-motion` (animation kill switch), `data-accent` (5 alt accent colors), `data-mascot-hidden`. |
| 5 | `dist/index.html` | Existing `setTheme` / `setLang` are bridged so legacy dropdown toggles also persist to the prefs store (sendBeacon used pre-reload for lang). |
| 6 | `tools/translations_manual_13.py` (new) | Korean → EN/ZH manual overrides for every drawer label, hint, section description. Wired into `tools/translations_manual.py`. |
| 7 | `scripts/e2e-quick-settings.mjs` (new) | Playwright smoke: ⌘,/Esc keyboard, 4 tabs, bool toggle persistence, range slider value, server round-trip. Passes alongside the 58-tab smoke. |

#### Parameters covered (33 total)
- **UI (9):** theme, lang, density, fontSize, reducedMotion, accentColor, sidebarCollapsed, mascotEnabled, compactSidebar
- **AI (9):** defaultProvider, effort, temperature, topP, maxOutputTokens, thinkingBudget, extendedThinking, streamResponses, fallbackChain
- **Behavior (9):** autoResume, notifySlack, notifyDiscord, telemetryRefresh, confirmSpawn, autosaveWorkflows, liveTickerSeconds, soundOnComplete, openLastTab
- **Workflow (6):** defaultIterations, defaultRepeatDelaySec, dryRunByDefault, showMinimap, snapToGrid, gridSize

#### Why
The dashboard had ~30 user-tunable knobs scattered across modal dialogs, settings page, and localStorage. v2.38 centralises them behind one keyboard shortcut so a user can flip effort to high, lower autoResume polling, switch accent to purple, and turn the mascot off without leaving the current tab.

#### Migration / compatibility
- New file `~/.claude-dashboard-prefs.json` is created on first write — defaults are derived from `DEFAULT_PREFS` until then.
- Existing `cc-theme` / `cc-lang` localStorage / cookie remain authoritative for the boot path so no flash of wrong theme/lang on reload.
- Override the path with env `CLAUDE_DASHBOARD_PREFS=/some/path`.

### 🩹 Hotfix — Crew Wizard preview wiped form state (pre-existing bug)

While shipping v2.38.0, a long-standing bug was discovered: the global `api()`
helper auto-fires `_scheduleAutoReload()` after every successful POST that
isn't on the `__noReloadPaths` allow-list, then `renderView()` re-runs and
nukes the in-memory `__cw.form` state. Symptom: clicking 미리보기 in the
Crew Wizard loaded for ~1s then snapped back to an empty form.

`__noReloadPaths` was extended (`dist/index.html:1373-1382`):
- `/api/wizard/` — preview / create
- `/api/slack/` — slack config save / test (called inside the wizard step 3)
- `/api/obsidian/` — obsidian vault test
- `/api/prefs/` — Quick Settings (precautionary; would close the drawer otherwise)

Verification: scripted Crew Wizard flow (project + goal → click 미리보기) →
**0 reloads, form state preserved, preview rendered** (9 nodes · 10 edges · 3 cycles).

---
## [2.37.1] — 2026-04-27

### ✨ Auto-Resume v2.37 follow-on — CLI watch · Haiku snapshot · scheduled-tasks · live ticker

Five quality-of-life additions on top of v2.37.0:

| # | Where | What |
|---|---|---|
| 1 | `server/auto_resume_cli.py` | New `watch` subcommand — foreground supervisor: prints one status line every `--refresh` seconds, cancels cleanly on SIGINT, exits 0 on `done` / non-zero on `failed`/`exhausted`. No HTTP server needed. |
| 2 | `server/auto_resume_hooks.py` | New `SNAPSHOT_SH_BODY_HAIKU` template + `install(cwd, *, use_haiku_summary=True)` flag. Stop-hook now optionally pipes the jsonl tail through `claude --print --model haiku-4.5 --bare` for a tight ≤12-bullet "where you left off" markdown brief — falls back to raw tail if Haiku unavailable. |
| 3 | `server/auto_resume.py` | `useHaikuSummary` field forwarded from `api_auto_resume_set` and `api_auto_resume_install_hooks` to the hook installer. |
| 4 | `dist/index.html` | Live 1-second countdown ticker for the "다음 시도까지 Ns" chip — surgical DOM rewrite, no extra fetch. Full status re-fetch still on the existing 5-second cadence. |
| 5 | `server/system.py` | `/api/scheduled-tasks/list` now exposes an `autoResume` array of active worker entries so a future timeline view can stitch the two together. |

#### Verification

- Backend unit: hooks Haiku variant install/uninstall round-trip · default variant unchanged · CLI `--help` advertises `watch` · `api_scheduled_tasks` returns `autoResume` key.
- `npm run test:e2e:auto-resume` — 3/3 viewports PASS.
- `npm run test:e2e:smoke` — 58/58 tabs PASS, no regression.

#### Backwards compatibility

- `install(cwd)` signature is `install(cwd, *, use_haiku_summary=False)` — old callers see no change.
- `useHaikuSummary` is opt-in; default snapshot template is identical to v2.37.0.
- `/api/scheduled-tasks/list` still returns `tasks` and `dirExists` exactly as before; `autoResume` is additive.

---
## [2.37.0] — 2026-04-27

### ✨ Auto-Resume — inject a self-healing retry loop into a live Claude Code session

Open a session detail in the dashboard, click **🔄 Auto-Resume 주입**, and a
background worker now watches that session's transcript. When it gets killed
by a token / rate-limit, the worker spawns `claude --resume <id> -p "<prompt>"`
in the session's cwd — exactly like the user-supplied reference shell while-loop:

```bash
while true; do
  claude "$@"
  [[ $? -eq 0 ]] && break
  sleep 300
done
```

…but with seven extra mechanisms baked in:

| # | Mechanism | Where |
|---|---|---|
| 1 | **Exit-reason classification** — `rate_limit` / `context_full` / `auth_expired` / `clean` / `unknown` via stderr+stdout+jsonl-tail regex | `server/auto_resume.py::_classify_exit` |
| 2 | **Precise reset-time parsing** — `"resets at 11:30am"`, `"in 30 minutes"`, `"after 2 hours"` → exact next-attempt epoch_ms | `server/auto_resume.py::_parse_reset_time` |
| 3 | **Stop-hook progress snapshot** — every Claude response writes `<cwd>/.claude/auto-resume/snapshot.md` so we always have the latest state on disk | `server/auto_resume_hooks.py::install` |
| 4 | **SessionStart-hook injection** — resumed session gets the snapshot piped into context automatically (Claude Code's SessionStart-hook stdout contract) | `server/auto_resume_hooks.py::install` |
| 5 | **External wrapper restart loop** — supervisor classifies → waits → re-spawns; `--resume <id>` by default, `--continue` toggle available | `server/auto_resume.py::_process_one` |
| 6 | **Loop guards** — `maxAttempts` (default 12), exponential backoff (1m→2m→4m→8m→16m→30m cap) for `unknown`, snapshot-hash stall detect (3× identical halts the loop) | `server/auto_resume.py::_exponential_backoff`, `_push_hash_and_check_stall` |
| 7 | **Observable state file** — `~/.claude-dashboard-auto-resume.json` with `running`/`waiting`/`watching`/`done`/`failed`/`exhausted`/`stopped`/`error` state per session | `server/auto_resume.py::_dump_all` |

#### What's new

- **New module**: `server/auto_resume.py` (worker + state machine + classifier + parser + backoff + stall detect)
- **New module**: `server/auto_resume_hooks.py` (per-project Stop+SessionStart hook installer with backup + idempotent re-install + clean uninstall)
- **New endpoints** (all under `/api/auto_resume/`): `set`, `cancel`, `get`, `status`, `install_hooks`, `uninstall_hooks`, `hook_status`
- **New panel**: in the session-detail modal, with state chip, exit-reason chip, attempts/max progress bar, next-attempt countdown, snapshot preview, hook install/remove buttons, advanced settings (prompt, poll, idle, maxAttempts, --continue mode, install hooks)
- **Sessions list** now shows a `🔄 AR` badge on every session with an active binding
- **i18n**: 41 new keys in `ko/en/zh` (translations_manual_12.py)

#### Verification

- `npm run test:e2e:auto-resume` — 5 consecutive runs, 3 viewports each (375x667 / 768x800 / 1280x800) — **15/15 PASS**
- `npm run test:e2e:smoke` — **58/58 tabs PASS** (no regression)
- Backend unit tests cover all 7 mechanisms; round-trip of hook install/uninstall verified in tmp sandbox

#### Safety

- Default OFF; opt-in per session
- Never auto-injects `--dangerously-skip-permissions`
- Hook installation is project-local only; `~/.claude/settings.json` (global) is **never** touched
- Settings.json backup written to `<cwd>/.claude/settings.json.auto-resume.bak` before first mutation
- Cancel + uninstall are idempotent and reversible

---
## [2.36.3] — 2026-04-26

### 🩹 Project snapshot modal — scroll fix

User reported the project snapshot modal (Projects tab → click a project
card) wouldn't scroll to the bottom. Symptom: middle and lower content
was clipped, the inner `overflow-y-auto` region behaved as if its
height was zero.

#### Root cause
The modal is a flex-column with `max-height: 92vh` and `overflow:
hidden`. Inside it sat (in order):

1. Header `<div class="p-5 border-b ...">` — could be tall when chips
   wrapped over multiple rows.
2. `<div id="aiRecSlot">` — empty by default but balloons after the AI
   recommend button is pressed.
3. `<div id="projectAgentsSlot">` — populated after lazy load.
4. The body `<div class="flex-1 overflow-y-auto p-5 grid ...">`.

None of regions 1–3 had `flex-shrink-0`, and the body was missing
`min-h-0`. With even a moderately long aiRec result the body's flex
share got pushed below zero and `overflow-y-auto` silently stopped
scrolling (the children rendered at their natural height past the
modal edge but the scrollbar was attached to a 0-px container).

#### Fixes
- Header gets `flex-shrink-0` so it never compresses.
- A new `<div id="projectSnapshotBody" class="flex-1 min-h-0
  overflow-y-auto" style="overscroll-behavior: contain;">` wraps the
  three formerly-separate regions (`aiRecSlot`, `projectAgentsSlot`,
  the grid). Now the modal has exactly two flex children — header and
  body — and the body owns a single, predictable scroll container.
- The grid's two columns get `min-w-0` so wide content (long file
  paths, raw JSON dumps) wraps inside the cell instead of forcing the
  whole grid wider than the modal.
- `scrollToSessions()` now scrolls inside `#projectSnapshotBody`
  rather than calling `scrollIntoView()` on the page (which was
  scrolling the viewport behind the modal).
- Modal opens with `{ wide: true }` so the two columns have room on
  desktop.

#### Verification
- Playwright opens the modal, measures the body container:
  `clientHeight=625, scrollHeight=1062` (was effectively 0 on the bug
  path), `overflowY=auto`, `canScroll=true`.
- After `body.scrollTop = body.scrollHeight`, the bottom-of-content
  invariant `scrollTop + clientHeight ≈ scrollHeight` holds within
  4 px — the section history table at the bottom is now reachable.
- 0 console errors.

---
## [2.36.2] — 2026-04-26

### 🔄 Server-restart detector — auto-banner when the user is on a stale build

User reported v2.36.1 features (OMC/OMX cards, ECC discovery fix) **still
weren't visible** after the release. The code was correct on disk and on
`origin/main`, but the user's running server was still v2.35.x — the
`git pull` happened without restarting `python3 server.py`. The browser
was also caching the previous `index.html` despite `Cache-Control:
no-store`.

The dashboard had no way to surface this. v2.36.2 makes it self-healing:

#### Backend (`server/version.py`)
- Capture `_SERVER_STARTED_AT_MS = int(time.time() * 1000)` at module
  import. The value never changes for the life of the process.
- `/api/version` now returns `{version, changelog, serverStartedAt}`.

#### Frontend (`dist/index.html`)
- On first load, the dashboard remembers `__bootedAt = {version,
  serverStartedAt}` from the first `/api/version` call.
- A 60-second poll (`_scheduleVersionPoll`) compares the current
  `/api/version` response to the booted snapshot.
- Mismatch on either field pops a sticky bottom-of-screen banner with
  two buttons — **Reload now** (`location.reload()`) and **Later**
  (dismiss). The banner uses the gradient `--accent → purple` so it's
  visually unmistakable.

#### Why this also catches the cache-bust case

Even when the user's `git pull` is correct, browsers occasionally cache
the inline-everything `dist/index.html`. As long as they restart the
server, the version-mismatch banner fires within 60 s and offers a
one-click hard-reload. In the rare case where neither version nor PID
changed (server still running an old build), the user sees no banner —
which is correct, because in that case there really is nothing new.

### Verification

- `make i18n-refresh` + `scripts/verify-translations.js` — all 4 stages
  pass: 3,845 keys × 3 locales matched, 1,107 `t()` Korean call sites
  covered, 0 Korean residue.
- Live HTTP — `/api/version` returns the new `serverStartedAt` field;
  consecutive calls within the same process return the same value
  (1777200287684 → 1777200287684). Restarting the process produces a
  larger value, exactly the trigger the polling code looks for.

### What this means for the v2.36.1 issue

The user sees nothing **new** until they reload. After they reload once
(per the diagnosis), every subsequent server restart is auto-detected
within 60 s. The "I deployed but the user is on the old build" failure
mode is now self-correcting.

---
## [2.36.1] — 2026-04-26

### 🩹 Run Center didn't see ECC after install + Guide had no OMC/OMX card

User reported two related gaps after v2.36.0:

1. **"Guide & Tools에 OMC OMX가 없어. 어떻게 써?"** — Run Center had OMC/OMX cards but Guide & Tools only had ECC. Users couldn't tell where they came from or whether anything needed installing.
2. **"ECC 설치했는데 런센터에 안나와."** — After installing ECC from Guide & Tools, Run Center still showed 0 ECC items. Root cause: I scanned only `~/.claude/plugins/cache/ecc/ecc/` but `toolkits.py` installs as `everything-claude-code@everything-claude-code`, which lives at `~/.claude/plugins/cache/everything-claude-code/everything-claude-code/`. **My initial "181 + 79" verification was on my own machine where both ids happened to coexist; I didn't recognise the path-name dependency until the user surfaced it.**

#### Fixes

**Run Center backend (`server/run_center.py`)**
- Replaced single-root resolution with `_ecc_roots()` returning every detected install: (1) `installed_plugins.json` entries for `ecc@ecc` **and** `everything-claude-code@everything-claude-code` (authoritative), (2) cache glob over both package names, (3) marketplaces fallback. Items are deduped across roots.
- `_build_catalog()` now returns `(items, debug)` and the catalog API exposes that `debug` blob with per-root scan counts.
- Added `?refresh=1` query param to bust the 30 s cache so a freshly installed ECC shows up immediately.

**Run Center UI (`dist/index.html`)**
- New info banner at the top of the tab explaining where ECC / OMC / OMX come from and that OMC/OMX need no separate install.
- Manual `🔄` refresh button next to the search input.
- Sidebar ECC status now distinguishes 3 states with deep diagnostics:
  - ✓ ECC installed — shows skill + command counts.
  - ⚠ Path found but 0 items — collapsible JSON of every scanned root.
  - ✗ ECC not installed — link to Guide & Tools + scanned-paths diagnostic.

**Guide & Tools (`server/guide.py`)**
- Two new toolkit cards: `oh-my-claudecode` (OMC) and `oh-my-codex` (OMX). Each card explains:
  - What's already absorbed by LazyClaude (no install needed).
  - When the external CLI is still useful (in-session slash commands).
  - The npm install command if the user wants the external CLI anyway.
  - Which features are in LazyClaude only vs CLI only.

#### Verification

- `make i18n-refresh` + `scripts/verify-translations.js` — all 4 stages pass: 3,841 keys × 3 locales matched, 1,103 `t()` Korean call sites covered, 0 Korean residue.
- Live HTTP — `/api/run/catalog` returns 270 items (262 ECC + 4 OMC + 4 OMX) on a machine with both `ecc@ecc` and `everything-claude-code@everything-claude-code` installed; debug blob lists 4 roots with per-root counts.
- `/api/guide/toolkit` returns 5 toolkit cards (was 3): everything-claude-code, claude-code-best-practice, **oh-my-claudecode**, **oh-my-codex**, wikidocs-claude-code-guide.

#### What I got wrong in v2.36.0

The "181 skills + 79 slash commands" headline was true on my dev box. I should have flagged that it depends on which ECC plugin id was installed, and I should have run `_ecc_root()` against an environment that only had the `everything-claude-code` id (which is what most users get from the dashboard installer). Future audits will trace `installed_plugins.json` first, not glob the cache directly.

---
## [2.36.0] — 2026-04-26

### 🎯 Run Center + Workflow Quick Actions + Commands tab Run buttons

User asked for ECC, OMC, OMX features to be runnable directly from the
dashboard rather than only inside Claude Code sessions. Three additions
land here, all wired to the existing `execute_with_assignee` pipeline so
any provider (Claude / OpenAI / Gemini / Ollama) can serve the request.

#### 1. Run Center — new tab `runCenter` (Build group)

A unified search-and-run catalog over **268 entries** (verified against an
ECC v1.10 install):

- **ECC** — 181 skills + 79 slash commands, scanned from
  `~/.claude/plugins/cache/ecc/<version>/{skills,commands}/`. Every
  entry's frontmatter is parsed (`name` / `description` / `tools`) and
  auto-categorised (frontend / backend / testing / review / security /
  ops / ai / data / ml / mobile / general).
- **OMC** — 4 modes (`/autopilot` / `/ralph` / `/ultrawork` /
  `/deep-interview`). Each links to its matching `bt-*` built-in
  template so the user can hand off to a full workflow with one click.
- **OMX** — 4 commands (`$doctor` / `$wiki` / `$hud` / `$tasks`)
  exposed as one-shot prompts.

Surface:
- Left column — 5 source filters (All / ECC / OMC / OMX / Favorites)
  with live counts, 6 kind filters, category chips, ECC install status
  badge with deep-link to Guide & Tools.
- Top bar — search by name / description / category, total count.
- ⭐ Favorite row — first 8 favorited items as compact cards.
- Card grid — paginated at 200 cards for performance.
- Click a card → modal with goal input, model picker (uses existing
  `_wfAssigneeOptions` so Claude / GPT / Gemini / Ollama appear),
  timeout slider. Run executes through `execute_with_assignee` and
  reports tokens / cost / duration. "Save as prompt" pushes the result
  into the Prompt Library; "Convert to workflow" hands off either to
  the matching built-in template (OMC) or scaffolds a 1-node workflow
  (ECC) and switches to the Workflows tab.

Backend (`server/run_center.py`, ~480 lines):
- `GET  /api/run/catalog?source=&kind=&q=` — filterable, 30 s cached.
- `POST /api/run/execute` — synchronous, time-bounded one-shot.
- `GET  /api/run/history?limit=` — runs sorted by recency.
- `GET  /api/run/history/get?id=` — full row including output / error.
- `POST /api/run/favorite/toggle` — persisted to
  `~/.claude-dashboard-run-favorites.json`.
- `POST /api/run/to-workflow` — return template id (OMC) or draft DAG
  (ECC) for the Workflows tab to consume.
- New SQLite table `run_history` (idempotent migration).

#### 2. Workflow Quick Actions (Workflows tab header)

A row of 4 buttons above the workflow stats panel: 🚀 Autopilot / 🔁
Ralph / 🤝 Ultrawork / 🧐 Deep Interview. Click → modal asks for the
goal in one line → loads the matching `bt-*` template via
`/api/workflows/templates/<id>`, injects the user's goal into the
planner node's `description`, saves a new workflow with the goal
truncated into the name, navigates the canvas to it, and auto-runs.
Goes from "I want autopilot on this idea" to a running DAG in two
clicks.

#### 3. Commands tab — Run buttons + ECC tagging

Each card in the existing Commands tab now shows:
- An `ECC` chip when the command's path is under
  `~/.claude/plugins/cache/ecc/` (heuristic — also matches `scope ===
  'plugin'` for backwards compat).
- A `▶ Run` button. ECC commands route through the Run Center modal
  (full execution context). Non-ECC commands scaffold a 1-node
  workflow and open it in the Workflows tab — they don't have the
  rich invocation copy that ECC frontmatter provides, so a
  user-editable workflow is safer than a blind dispatch.

#### Files

- `server/run_center.py` (new, +480) — catalog, executor, history,
  favorites, to-workflow handoff.
- `server/routes.py` (+8) — three GET + three POST routes registered.
- `dist/index.html` (+~530) — Run Center view (tab, sidebar filters,
  card grid, modal), Workflow Quick Actions header + handler,
  Commands tab Run buttons + handler, all CSS.
- `tools/translations_manual_11.py` (new, ~80 keys × EN / ZH).
- `tools/translations_manual.py` — wires `_NEW_EN_11` / `_NEW_ZH_11`.

#### Verification

- `make i18n-refresh` + `scripts/verify-translations.js` — all 4 stages
  pass: 3,861 keys × 3 locales matched, 1,091 `t()` Korean call sites
  covered, audit covered, static DOM covered, 0 Korean residue.
- Live HTTP — `/api/run/catalog` returns 268 items with the expected
  4-source split (260 ECC + 4 OMC + 4 OMX), filters work, favorite
  toggle round-trips, `/api/run/to-workflow` resolves OMC →
  `bt-autopilot` and ECC → 1-node draft.
- Playwright e2e — Run Center renders 201 cards (cap 200 + 1 favorite
  row card) with 11 filters and 12 category chips, OMC filter narrows
  to 5 cards, card click opens the goal modal with the model picker
  and "/autopilot" title, Workflows tab shows all 4 Quick Action
  buttons, Commands tab gets 600 Run buttons + 600 ECC chips, 0
  console errors.

---
## [2.35.1] — 2026-04-26

### 🌐 i18n hotfix — 18 missing translations caught by CI

The v2.34.2 release missed 18 English/Chinese keys. The previous
`build_locales.py` missing-detector only flagged keys whose value still
contained Korean — it didn't enforce **exact-match between every
`t('…')` call site and the locale dictionary**, which is what the
canonical `scripts/verify-translations.js` checks. CI failed on the 4-stage
verifier with `t() 인자 번역 누락: en=18, zh=18`.

The 18 keys fell into three buckets:

1. **Multi-sentence strings** that the audit extractor truncates at the
   first period. The runtime calls `t()` with the full string but the
   dictionary only had each sentence separately. Examples:
   - `Slack Bot Token (xoxb-…) 이 필요합니다. https://api.slack.com/apps 에서 봇을 만들고 chat:write, reactions:read, channels:history 권한을 부여하세요.`
   - `Projects/<프로젝트>/logs/YYYY-MM-DD.md 에 사이클별로 append 됩니다. $HOME 하위만 허용.`
   - The full Crew Wizard "이게 뭐죠?" answer in the guide modal.
2. **Trailing-colon prefixes** used like `t('Slack 실패: ') + err`:
   `Slack 실패: ` / `Obsidian 쓰기 성공: ` / `Obsidian 실패: ` /
   `생성 실패: ` / `오류: `.
3. **Strings with embedded double quotes** that JSON-escape as `\"`:
   the Slack approval reply keyword sentences and two gotcha-tip lines
   starting with `"slack token not configured"` / `"vault path must
   resolve under $HOME"`.

**Fixes**
- `tools/translations_manual_10.py` — added all 18 keys with their
  exact full-string form (Python's mixed quote syntax + raw Korean +
  embedded double quotes).
- For Slack approval reply keywords, the EN/ZH translations now show
  only the language-appropriate keywords (`approve` / `ok` /
  `reject`). The KO source still lists `"승인"` / `"거부"` because
  the backend `wait_for_approval()` recognises both. Removing the
  Korean keyword strings from EN/ZH avoids the runtime KO-residue
  scanner flagging legitimate translations.

**Verification**
- `make i18n-refresh` — 0 한글 잔존 (was 6).
- `scripts/verify-translations.js` 4 stages — all pass: 3,763 keys
  matched across ko/en/zh, all 1,042 `t()` Korean call sites covered,
  audit covered, static DOM covered.

### Why this slipped past v2.34.2

I relied on `build_locales.py`'s loose missing-detector and never ran
`scripts/verify-translations.js`. The two tools answer different
questions: the former asks "are translations stored?", the latter asks
"are they reachable from every call site?". CI runs the latter and
caught the gap. Going forward, `make i18n-refresh` (which already
chains both) is the single source of truth before committing any new
`t('…')` strings.

---
## [2.35.0] — 2026-04-26

### 📦 Install LazyClaude as a real app (PWA + macOS .app bundle)

LazyClaude can now be installed as an app, both ways:

#### Option A — PWA (cross-platform: macOS / Windows / Linux / iOS / Android)

Open LazyClaude in any modern browser → click the install icon in the
URL bar (Chrome/Edge) or **Share → Add to Home Screen** (Safari iOS).
The dashboard launches in its own window with no browser chrome, has a
Dock/taskbar icon, and registers shortcuts (Workflows / Crew Wizard /
AI Providers) in the right-click context menu.

- `dist/manifest.json` — `display: standalone`, `display_override`
  fallback chain (`window-controls-overlay` → `standalone` →
  `minimal-ui`), 3 launch shortcuts.
- 4 PNG icons (192 / 512 / 512 maskable / 180 apple-touch) generated
  from `docs/logo/mascot.svg` via Playwright. Maskable variant uses a
  dark background so the orange mascot survives Android's adaptive
  icon mask.
- `apple-mobile-web-app-capable`, `theme-color` (dark + light media
  queries), `og:title` / `og:image` / `og:description` for previews.

#### Option B — macOS .app bundle (Spotlight-searchable, Dock-pinnable)

```bash
make install-mac     # builds + copies LazyClaude.app to /Applications/
```

Double-click in Finder, or open via Spotlight (`⌘Space → LazyClaude`).
The launcher:

1. Resolves the project directory: `$LAZYCLAUDE_HOME` env > `~/Lazyclaude`
   > `~/lazyclaude`. Shows a friendly dialog if none found.
2. Confirms `python3` is available.
3. Reuses an already-running server on port 8080 if one is up.
4. Otherwise starts `python3 server.py` in the background, logging to
   `~/Library/Logs/LazyClaude/server.log`.
5. Opens `http://127.0.0.1:8080` in the default browser.
6. Forwards Quit / SIGTERM to the server so it shuts down cleanly.

The bundle is **72 KB total** — no Python interpreter, no Electron, no
Node runtime. It depends on the system `python3`, matching LazyClaude's
stdlib-only philosophy.

#### New Make targets

| Target | What it does |
|---|---|
| `make pwa-icons` | regenerate PWA PNG icons from `docs/logo/mascot.svg` |
| `make app` | build `dist/LazyClaude.app` |
| `make install-mac` | build + copy to `/Applications/` (replaces existing) |
| `make uninstall-mac` | remove `/Applications/LazyClaude.app` |

#### Files

- `dist/manifest.json` (new)
- `dist/icons/{icon-192, icon-512, icon-maskable-512, apple-touch-180}.png` (new)
- `dist/favicon.svg` + `dist/favicon-32.png` (new)
- `dist/index.html` — PWA `<head>` block (manifest + theme-color + apple-* + og:*)
- `tools/build_pwa_icons.mjs` (new) — Playwright-driven SVG → PNG renderer
- `tools/build_macos_app.sh` (new) — bundle builder using `sips` + `iconutil`
- `Makefile` — new targets

#### Verification

- Playwright PWA check — manifest parsed, all 4 icons + favicons load,
  no failed responses, theme-color and apple-* meta tags present.
- `.app` launcher — runtime simulation: server starts, `/api/version`
  responds, log file created at `~/Library/Logs/LazyClaude/server.log`,
  SIGTERM cleanly shuts the server down.

---
## [2.34.3] — 2026-04-26

### 🚨 Mobile sidebar overlay — second pass

The fix in v2.34.1 was insufficient. User reported (with a 670×720
screenshot, English locale) that the page content was still readable
through the dark-theme backdrop — `Documentation` button, the `57`
optimization score, the green `100` progress bars and labels were all
clearly visible behind the open sidebar.

Reproduced with Playwright at the same viewport. Two failures of the
v2.34.1 attempt:

1. `rgba(0,0,0,0.78)` + `blur(2px)` is too weak on a dark theme — the
   page text is mostly white/grey on near-black, and 78% black-on-black
   barely changes contrast.
2. `min(320px, 92vw)` left ~350 px of content visible to the right of
   the sidebar at 670 px viewport width — and that's the part the
   backdrop has to do all the work for.

**Fixes**
- Sidebar full-width (`100vw`) under **720 px** (was 480 px). 720 px
  covers tablet portrait, narrow desktop windows, and the user's actual
  viewport — content exposure is now 0 %.
- Sidebar widened from `min(320px, 92vw)` to `min(360px, 92vw)` for the
  720–900 px range.
- Backdrop alpha 0.78 → **0.92** (dark) / 0.85 (light) with
  `backdrop-filter: blur(10px) saturate(0.6)` — what little leaks past
  the wider sidebar is heavily blurred and desaturated, no longer
  readable.
- Light theme switched from a transparent black overlay to a translucent
  white overlay — better visual hierarchy on a light background.

**Verification**
- Playwright at 670×720 — sidebar is now `100vw`; content exposure 0 %.
- Playwright at 850×720 — sidebar 360 px; right pane is heavily blurred
  near-black, content unreadable.

---
## [2.34.2] — 2026-04-26

### 🌐 EN / ZH translations for v2.34 features

The Korean strings introduced in v2.34.0 / v2.34.1 were missing from the
EN and ZH locales — English and Chinese users saw raw Korean in the Crew
Wizard, palette categories, and node inspectors.

**Changes**
- New `tools/translations_manual_10.py` — ~210 EN + ZH entries covering
  the Crew Wizard, palette categories, `slack_approval` / `obsidian_log`
  node inspectors, the guide modal, and multi-sentence `WF_NODE_TYPES`
  descriptions (the audit extractor only captures the first sentence).
- `tools/translations_manual.py` — wires up `_NEW_EN_10` / `_NEW_ZH_10`.
- `dist/locales/{en,zh,ko}.json` regenerated; Missing EN/ZH = 0.
- `dist/index.html` — `_wfPickNodeType()` now wraps the auto-filled node
  title with `t()` so EN/ZH users see "Start" instead of "시작".

**Palette category labels**
| KO | EN | ZH |
|---|---|---|
| 트리거 | Trigger | 触发器 |
| AI 작업 | AI work | AI 工作 |
| 흐름 제어 | Flow control | 流程控制 |
| 데이터 / HTTP | Data / HTTP | 数据 / HTTP |
| 연동 | Integrations | 集成 |
| 출력 | Output | 输出 |

**Verification**
- `python3 build_locales.py` — Missing EN/ZH = 0.
- Playwright QA across en / zh / ko cookies — Crew Wizard 4 steps + guide
  modal + palette accordion + slack_approval / obsidian_log row picks.
  Korean leak count: EN 0, ZH 2 (pre-existing header CLI status indicator,
  unrelated to v2.34).

---
## [2.34.1] — 2026-04-26

### 🚨 Mobile sidebar backdrop + n8n-style palette + wizard guide

#### 1. Small-screen sidebar overlay (urgent)

User reported (with a 670×720 screenshot) that opening a sidebar category
on a small viewport leaked the page content through the sidebar with a
"weird pink pixel" floating at the corner. Reproduced with Playwright;
four root causes:

1. `body.sidebar-open::after` backdrop was `rgba(0,0,0,0.5)` — too weak
   on the dark theme so the page text was clearly readable.
2. No body scroll lock — content scrolled behind the open sidebar.
3. `#claudeMascot` (z-index 1150), `#chatBubble`, `#chatLauncher` floated
   above the z=35 backdrop — surfacing as the "pink pixel" the user saw.
4. Sidebar width `min(300px, 85vw)` left ~370 px of content visible on a
   670 px viewport.

**Fixes**
- Backdrop alpha 0.5 → 0.78 (dark) / 0.45 (light) + `backdrop-filter: blur(2px)`.
- `body.sidebar-open { overflow: hidden }` to lock body scroll.
- Sidebar widened to `min(320px, 92vw)`; **full `100vw` under 480 px** (no
  background bleed on narrow screens).
- Floating `#claudeMascot` / `#chatBubble` / `#chatLauncher` force-hidden
  while the sidebar is open.

#### 2. Workflow node palette redesigned to n8n-style accordion

User feedback: "too many icons, blocks too big". The 18 node types in a
3-column grid of large blocks were replaced with a **6-category × compact
row accordion**. One category open at a time. Click a category header →
expand a list of compact rows (icon + label + truncated description) →
click a row → detailed form (Zapier / n8n flow).

| Category | Nodes |
|---|---|
| 🚀 Trigger | `start` |
| 🤖 AI work | `session`, `subagent`, `embedding` |
| 🔁 Flow control | `branch`, `loop`, `retry`, `error_handler`, `merge`, `delay`, `aggregate` |
| 🔧 Data / HTTP | `http`, `transform`, `variable`, `subworkflow` |
| 🔗 Integrations | `slack_approval`, `obsidian_log` |
| 📤 Output | `output` |

- The currently selected node's category auto-opens and is highlighted.
- Open-category state is persisted per-editor in `localStorage`.
- The new `slack_approval` and `obsidian_log` nodes also got proper
  default data on selection (`channel`, `vaultPath`, `passThrough`, …) —
  previously they started with an empty data object.

#### 3. Crew Wizard usage guide

A `📖 Show how it works` button plus a first-visit auto-open modal (gated
by `cwGuideSeen` in `localStorage`). Six sections:

1. What is this? — wizard's purpose.
2. Generated structure — ASCII diagram.
3. 4-step guide — input explained step-by-step.
4. Slack interaction — ✅/❌ reactions and reply keyword mapping.
5. Common gotchas — token not configured, vault path, bot channel
   invitation, etc.
6. After generation — canvas editing, Webhook, live monitoring.

**Files**
- `dist/index.html` — backdrop/sidebar CSS, palette accordion
  (`WF_NODE_CATEGORIES`, `_wfPaletteToggleCat`, `.wf-palette` CSS), wizard
  guide modal (`_cwShowGuide`).

**Verification**
- Playwright on viewports 670×720 and 420×720 — backdrop + mascot hidden
  + scroll lock confirmed.
- Palette renders 6 categories × 18 rows; single-open behaviour holds; a
  row click triggers default data + form render.
- Wizard auto-guide on first visit + manual `📖` button both work.

---
## [2.34.0] — 2026-04-26

### 🧑‍✈️ Crew Wizard + Slack approval gate + Obsidian logging

Two-pronged response to the "the workflow editor is too complex"
feedback:

1. **New Crew Wizard tab (`crewWizard`)** — a Zapier-style 4-step form
   that scaffolds a planner + N personas + Slack admin gate + Obsidian
   log workflow in one click. The output is a regular workflow editable
   in the canvas.
2. **The Workflows tab stays the n8n-style advanced surface** — two new
   node types are exposed in the palette and inspector.

**New modules**
- `server/slack_api.py` — Slack Web API client (Bot Token `xoxb-*`):
  `chat.postMessage`, `conversations.replies`, `reactions.get`,
  `auth.test`. Token saved to `~/.claude-dashboard-slack.json` with
  chmod 600.
- `server/obsidian_log.py` — markdown appender writing to
  `<vault>/Projects/<project>/logs/YYYY-MM-DD.md`. `$HOME`-only with
  `realpath` for path-traversal defence.
- `server/crew_wizard.py` — form → DAG builder. Three autonomy modes:
  `admin_gate` / `autonomous` / `no_slack`.

**New workflow nodes**
- `slack_approval` — posts to a Slack channel and polls for ✅/❌
  reactions or thread replies. On timeout one of `approve | reject |
  abort | default`. A free-form reply is used as the next cycle's input
  so the admin can steer mid-flight.
- `obsidian_log` — appends each cycle's report. In pass-through mode the
  input flows on to the next node unchanged.

**New built-in template**
- `bt-crew` (Persona Crew) — Planner (Opus) → 3 personas (Claude / Gemini
  / Ollama mix) → Aggregate → SlackApproval → ObsidianLog → Output, with
  a 3-cycle loop.

**New endpoints**
- `GET  /api/slack/config` — returns only a redacted token hint.
- `POST /api/slack/config/save` — `auth.test` then persist.
- `POST /api/slack/config/clear`
- `POST /api/slack/test`            — send a test message to a channel.
- `POST /api/obsidian/test`         — try writing to the vault.
- `POST /api/wizard/crew/preview`   — build but do not save.
- `POST /api/wizard/crew/create`    — build + save + return wfId.

**Files**
- `server/slack_api.py` (+283)
- `server/obsidian_log.py` (+118)
- `server/crew_wizard.py` (+260)
- `server/workflows.py` (+~190 — two node types' sanitize/executor +
  `bt-crew` template)
- `server/routes.py` (+11 — route registration)
- `dist/index.html` (+~430 — Wizard view 4-step form + inspector +
  palette)

**Security**
- Slack token: env var `SLACK_BOT_TOKEN` > file. Responses expose only a
  redacted hint like `xoxb-1234... ABCD`.
- Slack API calls are restricted to host `slack.com` over HTTPS; token
  format validated by `^xox[bp]-...` regex.
- Obsidian vault path: `realpath`-checked under `$HOME` only; project
  name validated against `[A-Za-z0-9 _\-./]{1,80}` regex.

---
## [2.33.3] — 2026-04-24

### 🎨 Light theme WCAG AA contrast audit

Playwright 기반 contrast sweep 스크립트(`scripts/e2e-light-contrast.mjs`) 신규 — 58 탭을 light 테마로 순회하며 text/bg pair 를 relative luminance 로 측정, WCAG AA 4.5:1 미달 요소를 path · fg · bg · fontSize 와 함께 수집.

**초기 측정**
- `rgb(136,136,146) #888892` (light --text-dim) 414 건, ratio 2.85-3.51
- `rgb(217,119,87)` accent orange 10 건, ratio 3.12
- `rgb(167,139,250)` / `rgb(251,191,36)` 등 pastel 색상 30+ 건

**수정**
1. light 테마 CSS 변수 강화: `--text-dim #888892 → #5a5a62` · `--text-mute → #3f3f46` · `--accent → #9e4422`.
2. Tailwind arbitrary color (`text-[#c4b5fd]` 등) 클래스 셀렉터로 9 색 배치 override.
3. inline `style="color:#XXX"` 패턴을 attribute selector (`[style*="color:#fbbf24"]`) 로 추가 오버라이드 9 색.
4. `.pulse-dot` 녹색을 `#15803d` 로 강화.

**결과**
- Strict AA (4.5:1): 819 → 87 건 (89% 감소). 남은 대부분 `rgb(21,128,61)` on `chip-ok` 배경 — ratio 정확히 4.50 (AA 경계, 읽기 문제 없음).
- 실질적 4.0:1 기준: 9 탭 17 건 (98% 개선).
- Overview / guideHub / workflows 스크린샷에서 카드 제목·숫자·사이드바 메타 모두 뚜렷하게 가독.

**파일**
- `dist/index.html`: light theme CSS 변수 + 20 줄 추가 override.
- `scripts/e2e-light-contrast.mjs`: 신규 audit 스크립트.

---
## [2.33.2] — 2026-04-24

### 🔌 ECC Plugin full auto-install

기존 v2.33.1 의 ECC 자동화는 marketplace 클론까지만 자동이고 실제 플러그인 설치는 사용자가 Claude Code 에서 `/plugin install` 을 직접 실행해야 했다. `claude plugin install` 서브커맨드가 비대화형으로 동작하는 것을 확인 후 두 신규 엔드포인트 추가:

- `POST /api/toolkit/ecc/install-plugin` — marketplace 미클론이면 선행 클론 후 `claude plugin install everything-claude-code@everything-claude-code -s user` 실행
- `POST /api/toolkit/ecc/uninstall-plugin` — `claude plugin uninstall ...` 실행

GuideHub 카드 UI 가 설치 상태에 따라 "🔌 플러그인 설치" / "🗑 플러그인 제거" 버튼으로 자동 토글.

**검증**
- Playwright end-to-end: "플러그인 설치" 클릭 → 30초 내 "1 개 플러그인 설치됨" 으로 전환 확인
- `claude plugin list` 에 `everything-claude-code@everything-claude-code` v1.10.0 등록 확인

**파일**
- `server/toolkits.py`: `_run_claude_plugin` + 2 신규 API
- `server/routes.py`: 2 라우트 등록
- `dist/index.html`: `_renderEccManage` 에 플러그인 토글 버튼 + `_eccInstallPlugin` 핸들러
- `dist/locales/{ko,en,zh}.json`: +7 keys

---
## [2.33.1] — 2026-04-24

### 🪟 사이드바 UX 3종 픽스

**문제**
1. **복구 불가** — 햄버거 버튼으로 사이드바를 접으면, 다시 펼칠 버튼이 사라져 재시작 전까지 좁은 아이콘 모드에 갇힘.
2. **flyout hover 끊김** — 카테고리에서 오른쪽 flyout 으로 마우스를 이동하는 도중 `8px` gap 구간에서 hover 가 빠져 flyout 이 닫힘.
3. **아이콘 의미 불명** — 접힌 사이드바에서 🆕 🏠 🔀 🧪 ⚙️ 📊 아이콘만 보여 어떤 기능인지 즉시 인지 불가.

**원인**
1. `_initMobileNav` IIFE 가 원본 `_syncNavToggleVisibility` 를 래핑하면서 `collapsed` 상태를 무시하고 `#navToggle` 을 항상 `display:none` 으로 덮어씀 → 접힌 상태에서 유일한 재펼치기 버튼이 숨겨짐.
2. `.nav-flyout { left: calc(100% + 8px) }` 의 8px gap 에서 마우스가 공백 위에 놓이면 `.nav-category:hover` 가 풀림.
3. `.nav-category` 에 `title` 속성 없음 + collapsed 상태에서 `.nav-cat-meta` 가 58px sidebar 내에 사실상 클리핑됨.

**수정**
1. `_initMobileNav` 의 래퍼 제거 — 원본 `_syncNavToggleVisibility` 가 이미 `(모바일 OR collapsed) ? 표시 : 숨김` 을 정확히 처리.
2. `.nav-category::after` 로 category 오른쪽에 14px 투명 pseudo-element 를 두어 hover 브리지. pseudo-element 는 category 의 자식이므로 마우스가 그 위에 있어도 `:hover` 유지.
3. collapsed 사이드바 너비 `58px → 78px` 로 확대. 아이콘 아래 **짧은 라벨**(Learn / Main / Build / Lab / Config / Watch) 9.5px 폰트로 세로 정렬. 추가로 `.nav-category` 에 `title` 네이티브 툴팁 부여 → 전체 설명도 hover 로 확인 가능.

**검증**
- `scripts/e2e-sidebar-ux.mjs` 신규 E2E — collapsed 후 `#navToggle` 가시성, flyout gap 중간 hover 유지, 바깥 이동 시 정상 종료, short 라벨 `display:inline-block` + full 라벨 `display:none` 확인.
- 기존 `e2e-ui-elements.mjs` 전 테스트 통과 (회귀 없음).

**파일**
- `dist/index.html`: nav-category CSS/마크업, GROUPS 에 `short` 필드 추가, `_initMobileNav` 단순화.
- `scripts/e2e-sidebar-ux.mjs`: 신규 회귀 테스트.

### 🌐 i18n — 사이드바 카테고리 & 부분 번역 누수 해소

**문제**
1. 사이드바 상위 카테고리 6종(Learn/Main/Build/Playground/Config/Observe)과 short 라벨(Lab/Watch 포함) 이 사전에 없어 en/zh 전환 시 영어 그대로 노출.
2. 서브탭 4개(`learner`/`artifacts`/`eventForwarder`/`securityScan`) 의 한국어 desc 가 en/zh 사전에 없어 원문 한국어가 노출됨.
3. 백엔드 추천 문구(`features.py::overallScore` recommendations 6종) 가 사전에 없어 `_translateDOM` 단어 레벨 치환으로 **부분 번역**(예: "자주 쓰는 Command Allow", "Permissions 프롬프트를 줄이려면 … allowAdd to.") 발생.

**원인**
- GROUPS 의 `label`/`short` 가 영어 리터럴이라 `t()` → ko 분기에서 `!_KO_RE.test(key)` 로 fallback 경로 타고 원문 리턴.
- 4 서브탭 desc 추가 시 locale 파일 업데이트 누락 (v2.30~v2.33 도입 탭).
- `_translateDOM` 의 pattern-based 치환이 긴 Korean 키 일치 없이 부분 단어만 치환하여 어색한 혼합문장 생성.

**수정**
- `GROUPS` label/short 을 Korean 으로 전환 (`학습`/`메인`/`빌드`/`플레이그라운드`/`구성`/`관측` + short `실험실`) — 기존 `t()` dict 경로로 자연 번역.
- `dist/locales/{ko,en,zh}.json` 에 22 개 키 추가:
  - 카테고리 6종 + short 변형
  - 4 서브탭 desc (Learner/Artifacts Viewer/Event Forwarder/Security Scan)
  - 백엔드 추천 6쌍(제목 + 상세) 완전 문장 (훅 설정/거부 규칙/자주 쓰는 명령/세션 스코어/플러그인 활성화/MCP 커넥터)

**검증**
- `scripts/e2e-find-missing-i18n.mjs` 신규 — ko/en/zh 3 언어 전환 후 텍스트 노드 + 속성에서 한국어 누수 수집. UI 텍스트 누수 0건 (남은 4건은 사용자 세션 prompt 내용으로 번역 대상 아님).
- `node scripts/verify-translations.js` 4 단계 검증 통과 (3486 keys × 3 lang).
- 스크린샷 확인: KO "학습/메인/빌드/플레이그라운드/구성/관측" · EN "Learn/Main/Build/Playground/Config/Observe" · ZH "学习/主要/构建/实验场/配置/观测".

**파일**
- `dist/index.html`: GROUPS label/short Korean 전환.
- `dist/locales/{ko,en,zh}.json`: +22 keys each.
- `scripts/e2e-find-missing-i18n.mjs`: 신규.

### 📏 flyout viewport-aware 위치 계산

**문제**
하단 카테고리(Observe/Config 14 items, Playground 12 items 등) 의 flyout 이 category top 기준 `top:0` 으로 아래로만 뻗어 viewport 아래로 삐져나감. `max-height:80vh + overflow-y:auto` 가 걸려있지만 스크롤 영역 자체가 viewport 밖이라 하단 아이템 접근 불가.

**원인**
`.nav-flyout { top: 0; max-height: 80vh }` CSS 만으로는 category 가 viewport 하단 쪽에 있을 때 flyout bottom 이 viewport 를 초과함. 측정 결과: 1440×900 viewport 에서 Observe flyout top=373, bottom=1093 (193px 초과 · 12 items 중 마지막 2개 클리핑).

**수정**
`_positionNavFlyout(cat)` 도입 — category 위치/자연 높이 측정 후 동적으로 `top` 음수 offset + `max-height` clamp. `mouseenter` · `focusin` · 클릭 open 시에 실행. resize 시 열려있는 flyout 자동 재계산.
- flyout 이 아래 공간에 들어가면 top:0 유지
- 아래로 넘치면 위로 shift 해서 flyout bottom ≤ viewport - 12px
- shift 해도 viewport 상단을 넘으면 top = 12px 에서 clamp (이때만 내부 스크롤 필수)

**결과** (1440×900)
| 카테고리 | 아이템 | 이전 flyout bottom | 이후 flyout bottom | fits? |
|---|---|---|---|---|
| learn | 4 | 368 | 368 | ✓ |
| main | 6 | 482 | 482 | ✓ |
| build | 10 | 819 | 819 | ✓ |
| playground | 12 | 1108 | 888 | ✓ (shift -220) |
| config | 14 | 1187 | 888 | ✓ (shift -299) |
| observe | 12 | 1093 | 888 | ✓ (shift -231) |

**파일**
- `dist/index.html`: `_positionNavFlyout` 함수 + nav-category mouseenter/focusin/click 바인딩.

### 🧰 가이드 툴킷 자동 설치/제거 — ECC · CCB

**문제**
1. **가독성** — guideHub 툴킷 카드의 설치 코드박스가 `rgba(0,0,0,0.3)` 반투명 배경 + `#a7f3d0` 민트 글씨라 light 테마에서 중간 회색 위에 밝은 글씨가 거의 안 보임. 카테고리 태그(Agents/Skills/Commands/Hooks) 도 `#c4b5fd` 연보라 글씨라 light 에선 대비 부족.
2. **관리 기능 부재** — Everything Claude Code(ECC) · Claude Code Best Practice(CCB) 가 카탈로그엔 있지만 설치/제거 버튼이 없어 사용자가 직접 터미널/CC 에서 수행해야 했음 (RTK 는 이미 자동화되어 있음).

**수정**
- **CSS `.code-terminal`** — 모든 테마에서 항상 `#0b1220` 진한 배경 + 선명한 민트 글씨로 통일. 툴킷 install 코드박스 전부 이 클래스 사용.
- **CSS `.chip-violet`** — light 테마에서 `#6d28d9` 진한 보라색으로 오버라이드. 카테고리 태그 전부 이 클래스 추가.
- **신규 `server/toolkits.py`** — `/api/toolkit/{status,ecc/install,ecc/uninstall,ccb/install,ccb/uninstall,ccb/open}` 6 라우트:
  - **ECC**: `git clone --depth 1 affaan-m/everything-claude-code` → `~/.claude/plugins/marketplaces/everything-claude-code/` + `known_marketplaces.json` 엔트리 등록. 이후 Claude Code 에서 `/plugin install ...` 만 실행하면 됨(명령 복사 버튼 제공). 제거 시 디렉터리 + 레지스트리 entry 모두 삭제.
  - **CCB**: `git clone --depth 1 shanraisshan/claude-code-best-practice` → 기본 `~/claude-code-best-practice/`. 제거 시 디렉터리 삭제(.git 존재 확인). macOS `open` 으로 폴더 열기 지원.
  - 보안: `_under_home` realpath 검증 · 쓰기 경로 화이트리스트 · `.git` 존재 확인 후 제거.
- **guideHub 카드 UI** — `AFTER.guideHub` → `_refreshToolkitManage()` 가 상태 가져와 각 카드 상단에 상태 chip + 버튼 렌더:
  - ECC: 미설치/마켓추가됨/플러그인 설치 필요, "마켓플레이스 추가"/"업데이트"/"마켓 제거" + `/plugin install` 명령 복사
  - CCB: 미설치/설치됨(commit hash), "내려받기"/"업데이트"/"폴더 열기"/"제거"

**검증**
- `curl -X POST /api/toolkit/ecc/install` → `{"ok":true,"installed":true}` · `~/.claude/plugins/marketplaces/everything-claude-code/` clone 완료 · `known_marketplaces.json` 에 entry 추가 확인.
- UI 재렌더 후 ECC 상태가 "✓ 마켓플레이스 추가됨 · 4e66b28 · 플러그인 설치 필요" 로 자동 업데이트.
- Light 테마 스크린샷에서 코드박스·태그 가독성 확연히 개선.

**파일**
- `server/toolkits.py`: 신규 (237줄).
- `server/routes.py`: 6 라우트 등록.
- `dist/index.html`: `.code-terminal` · `.chip-violet` CSS + `_renderGuideToolkits` 클래스 전환 + `AFTER.guideHub` + 5 API 호출 헬퍼.

### 🔑 로그인 게이트 — 매번 새로고침 → 첫 방문만

**문제**
`boot()` 에서 auth 상태와 무관하게 **항상** `showLoginGate` 를 호출해 새로고침마다 "Continue" 버튼을 한 번씩 눌러야 했음.

**수정**
- `localStorage` `dashboard-entered` 플래그 도입. 첫 `enterDashboard()` 호출 시 설정, `doLogoutOnly()` 에서 제거.
- `boot()` 로직: 플래그가 있고 `auth.connected` 면 → 게이트 스킵 후 바로 `enterDashboard()`. 첫 방문 OR 연결 끊김 OR 서버 실패 시에만 게이트 표시.
- 좌측 하단 `#cliStatus` 카드에 로그아웃 버튼 추가:
  - 연결됨: "🔄 전환" + "🚪 로그아웃" 2 버튼 (기존 "계정 전환" 단독 → 2 버튼)
  - 미연결: "🚀 로그인" 버튼
- i18n 22 키 추가 (`전환`, `로그아웃`, 기타 토글 + 토스트 메시지).

**검증**
- 첫 방문: 게이트 표시 · flag null
- Continue 클릭 후 flag="1"
- 새로고침: 게이트 스킵 · sidebar 즉시 표시 · nav 6 카테고리 렌더
- 로그아웃 버튼 → flag 제거 → 다음 로드 시 게이트 재표시
- verify-translations 4단계 통과 (3508 keys × 3 lang)

**파일**
- `dist/index.html`: `enterDashboard` localStorage 저장 · `boot()` 플래그 분기 · `doLogoutOnly` 플래그 클리어 · `#cliStatus` 카드 버튼 확장.
- `dist/locales/{ko,en,zh}.json`: +22 keys.

---
## [2.33.0] — 2026-04-24

### 🎨 Artifacts 로컬 뷰어 — 4중 보안 워크플로우 출력 미리보기 (build 그룹)

v2.21.0 Obsidian 설계 이후 미루어왔던 Artifacts 뷰어를 전면 새 설계 + 구현. 워크플로우 노드 출력(HTML/SVG/Markdown/JSON)을 **4중 보안** 으로 대시보드에서 안전하게 미리보기.

**4중 보안**
1. **Sandbox iframe** `sandbox=""` (빈 값 = 모든 권한 차단: 스크립트 실행·폼·쿠키·탐색·플러그인·탑레벨 이동 전부 블록)
2. **CSP meta 주입** `default-src 'none'; style-src 'unsafe-inline'; img-src data:` (외부 리소스 전면 차단, inline CSS 와 data: 이미지만)
3. **postMessage 화이트리스트** — iframe → parent 방향 메시지 검증 (현재 구조상 이벤트 없지만 향후 확장용)
4. **정적 필터** — `<script>` / `<iframe>` / `<object>` / `<embed>` / `<link>` / `<meta>` / `<base>` / `<form>` 태그 제거, `on*=` 이벤트 속성 제거, `javascript:` / `data:text/html` URL 제거

**신규 모듈 `server/artifacts.py`**
- 포맷 자동 감지: HTML / SVG / Markdown / JSON / text
- Markdown → 안전 HTML 변환 (외부 라이브러리 없이 순수 Python stdlib — 헤더/리스트/코드블록/bold/italic/code/link 지원)
- `_SRCDOC_WRAPPER`: CSP meta + 다크 테마 CSS 포함 HTML 템플릿
- 2 API: `/api/artifacts/list` (최근 50 run) · `/api/artifacts/render?runId=xxx&format=auto|html|svg|markdown|json|text`

**신규 탭 `artifacts` (build 그룹)**
- 좌측: 최근 run 목록 + 포맷 힌트 chip + 출력 크기
- 우측: iframe 미리보기 + 포맷 재선택 탭 (auto/html/svg/markdown/json/text)
- 보안 힌트: "sandbox='' + CSP default-src:none"

**단위 테스트 — 9/9 공격 패턴 차단**
- `<script>`, `<img onerror=>`, `javascript:`, `<iframe>`, `<object>`, `<link>`, `<meta refresh>`, `onload=`, `data:text/html` 모두 완전 제거 확인
- 포맷 감지 5/5 정확

**검증**
- 58/58 탭 smoke (57→58)
- CSP 주입 확인, srcdoc 길이 1.1KB (빈 문서 템플릿)
- i18n 6 키 × ko/en/zh

---
## [2.32.0] — 2026-04-24

### 🔌 MCP 서버 모드 — LazyClaude 를 Claude Code 에서 직접 호출

Claude Code 세션 안에서 대시보드 기능을 MCP tool 로 호출할 수 있게 LazyClaude 를 stdio MCP 서버로 노출.

**신규 파일**
- `server/mcp_server.py` — stdio JSON-RPC 2.0 루프 (MCP 2024-11-05 protocol)
- `scripts/lazyclaude_mcp.py` — 진입점 스크립트

**노출 tools (6)**
- `lazyclaude_tabs` — 6 상위 카테고리별 탭 카탈로그
- `lazyclaude_cost_summary` — 비용 타임라인 요약 (총 USD · 소스별 · 모델별)
- `lazyclaude_security_scan` — `~/.claude` 정적 보안 검사 결과
- `lazyclaude_learner_patterns` — 세션 반복 패턴 + 누적 토큰
- `lazyclaude_rtk_status` — RTK 설치/훅 상태
- `lazyclaude_workflow_templates` — 10 빌트인 템플릿 목록

**특징**
- Python stdlib 만 사용 (외부 MCP SDK 없음), newline-delimited JSON-RPC
- Transport: stdio · No network · No auth · 100% local
- Initialize → tools/list → tools/call → shutdown 완전 지원
- Unknown method 는 `-32601` error code 로 응답

**설치**
```bash
claude mcp add lazyclaude -- python3 /<path>/LazyClaude/scripts/lazyclaude_mcp.py
```

**대시보드 UI**
- MCP 탭 상단에 "💤 LazyClaude 자체를 MCP 서버로" 카드 추가
- `/api/mcp-server/info` 로 스크립트 절대경로 + 노출 tool 목록 동적 제공
- 설치 명령 readonly input + 📋 클립보드 복사 버튼
- 6 tool 설명 접힘 섹션

**검증**
- stdio 통신 테스트: `initialize` + `tools/list` + `tools/call` × 2 + `shutdown` 모두 정상 응답
- 실제 rtk 0.37.2 설치 감지 · workflow templates 10개 반환 확인
- 57/57 탭 smoke 통과
- i18n 4 키 × ko/en/zh

---
## [2.31.0] — 2026-04-24

### 🛡️ Security Scan 탭 — ECC AgentShield 스타일 정적 검사 (observe 그룹)

사용자 요청: ECC(everything-claude-code) 의 좋은 기능 흡수. 가장 가치 높은 **AgentShield** 를 우리 대시보드 형태로 재구현.

**신규 모듈 `server/security_scan.py` — 로컬 휴리스틱, AI 호출 없음**
- 스캔 대상: `~/.claude/settings.json` · `~/.claude/CLAUDE.md` · hooks · agents · `~/.claude/mcp.json`
- 이슈 카테고리 (severity: critical/high/medium/low/info):
  - **secrets**: API 키/토큰 평문 노출 (OpenAI / Anthropic / Google / GitHub PAT / AWS / Slack / PEM 등 8 패턴)
  - **permissions**: `Bash(*)` · `Bash(sudo *)` · `Bash(* | sh)` 같은 위험 allow 규칙
  - **hooks**: `sudo` / `rm -rf /` / `curl | sh` / `wget | sh` / `eval $()` / `chmod 777` 등 훅 내 위험 명령
  - **mcp**: `npx -y` / `uvx` 자동 설치 (신뢰 안된 패키지 시 RCE), MCP env 내 평문 시크릿
  - **tokens**: autocompact threshold 미설정, CLAUDE.md 50KB+ (토큰 낭비)
  - **integrity**: settings.json 파싱 실패

**신규 탭 `securityScan` (observe 그룹)**
- 상단 severity 카운터 (critical/high/medium/low/info 5 색상 카드)
- 이슈 카드 리스트 (좌측 3px 색상 바 · 심각도 이모지 · 카테고리 chip · 상세 · 파일 경로)
- "다시 검사" 버튼으로 재실행
- 이슈 0건 시 "✅ 깨끗합니다" 빈 상태

**API**
- GET `/api/security-scan` — 이슈 리스트 + severity/category 집계

**ECC 와의 차이**
- ECC AgentShield: 1282 tests · 102 정적 규칙 · `/security-scan` skill + `npx ecc-agentshield scan --opus` CLI
- 우리: **정적 휴리스틱 중심** (~~50 규칙) · GUI 탭 · 즉시 실행 · Python stdlib
- 향후 v2.32+ 에서 AI 보조 판단 (Opus scan) 옵션 추가 가능

**탭 57개** (56 → 57). i18n 6 키 × ko/en/zh.

**검증**
- 57/57 탭 smoke 통과
- 실환경 스캔: 1 info 감지 (autocompact threshold 미설정 권장)
- 8 secret 패턴 + 6 shell 위험 패턴 + 4 MCP 패턴 unit 커버리지

---
## [2.30.0] — 2026-04-24

### 🎓 Learner 탭 — 세션 패턴 추출 (B8, 마지막 backlog medium 항목 소화)

Claude Code 세션 JSONL 에서 반복되는 tool 시퀀스 · 프롬프트를 자동 감지해 Prompt Library / 워크플로우 템플릿으로 저장하도록 제안하는 탭.

**순수 통계 기반 (AI 호출 없음)**
- 최근 30일 / 최대 100 세션 / 세션당 500 라인 스캔
- 추출 지표:
  - **Top Tools** (Bash / Edit / Read 등 빈도 TOP 10, 가로 바 차트)
  - **Tool 3-gram 시퀀스** (같은 세션 내 연속 tool 호출 패턴, 3회 이상 발생)
  - **반복 프롬프트** (첫 60자 정규화 매칭, 3회 이상 반복)
  - **세션 길이 분포** (small ≤10 / medium 10-50 / large 50-200 / huge >200 라인 bucket)
  - **누적 토큰**
- 분석은 100% 로컬 — 외부 API 호출 없음

**UI**
- 3열 상단 카드 (스캔 세션 수 / 누적 토큰 / 길이 분포 stacked bar)
- Top Tools 가로 바 차트 (8개)
- 자동 추출 제안 카드 그리드:
  - 반복 프롬프트 → "Prompt Library 로 저장" 버튼 (에디터에 title/body/tags=['learner'] 자동 prefill 후 promptLibrary 탭으로 이동)
  - Tool 시퀀스 → "워크플로우 탭으로 이동" 버튼
- 하단 힌트 "분석은 완전히 로컬에서 수행됩니다"

**모듈**
- 신규 `server/learner.py::api_learner_patterns` (1 라우트)
- 새 탭 `learner` (build 그룹, nav_catalog + TAB_DESC_I18N + 프런트 NAV 엔트리)
- VIEWS.learner + `_learnerToPromptLib()` 헬퍼

**검증**
- 56/56 탭 smoke (신규 `learner` 추가로 55→56)
- 실환경 테스트: 100 세션 스캔 → 2.9M 토큰, 10 패턴 카드 생성 (Bash 412 · Edit 403 · Read 389 등), 반복 프롬프트 11회 감지
- i18n 16 키 추가 × ko/en/zh (learner_*)

**Backlog 현황**
- ✅ B1~B8 모두 소화 완료
- 🚫 blocked (사용자 설계 승인 필요): MCP 서버 모드 · Artifacts 로컬 뷰어

---
## [2.29.0] — 2026-04-24

### ⚙️ Policy fallbackProvider 확장 + 📤 Event Forwarder 신규 탭 (B7)

**Policy · fallbackProvider 확장 (`workflow.policy.fallbackProvider`)**
- session 노드가 assignee 로 실패할 때 설정된 프로바이더로 **1회 재시도**
- 허용값: `""`(none) · `claude-api` · `openai-api` · `gemini-api` · `ollama-api`
- 실행 결과에 `fallbackUsed` 필드로 어떤 프로바이더가 쓰였는지 기록 (빈 문자열이면 원래 assignee 로 처리됨)
- 재귀 방지: 폴백 호출은 `fallback=False` 로 넘겨 ai-providers chain 가 또 타지 않음
- 에디터 인스펙터 🛡 실행 정책 섹션에 select UI 추가

**B7 · Event Forwarder 신규 탭 (`eventForwarder`, config 그룹)**
- Claude Code hook 이벤트(`PostToolUse`, `Stop`, `SessionStart` 등 9종)를 외부 HTTP endpoint 로 포워딩
- 신규 모듈 `server/event_forwarder.py`:
  - `~/.claude/settings.json` 의 hooks 섹션에 `curl -sS -X POST --data-binary @- '<URL>' # __lazyclaude_forwarder__` 엔트리 add/remove
  - 매 변경 시 `settings.json.bak.<ts>` 자동 백업
  - `__lazyclaude_forwarder__` 마커로 우리 엔트리만 필터 — 사용자가 직접 추가한 hook 은 건드리지 않음
- **SSRF 방어 (호스트 화이트리스트 11종)**: `hooks.slack.com` · `discord.com` · `webhook.site` · `requestbin.com` · `pipedream.net` · `zapier.com` · `api.github.com` · `maker.ifttt.com` · `n8n.cloud` 등 + 루트 도메인 매칭 (예: `subdomain.webhook.site` OK)
- https-only · URL 길이 500 이하 · shell metacharacter 금지 (`'`, `"`, `\\`, `$`, `` ` ``, newline) → single-quote 래핑으로 안전하게 shell escape
- 4개 라우트: GET `/api/event-forwarder/{list,meta}`, POST `/api/event-forwarder/{add,remove}`
- UI: 이벤트 타입 select + matcher input + URL input + 허용 호스트 안내 + 등록된 forwarder 테이블 + 삭제 버튼

**검증**
- 55/55 탭 smoke (신규 `eventForwarder` 추가로 54→55)
- Policy fallback sanitize 경계 케이스 3종 (정상 / evil / claude-api)
- Event Forwarder E2E: http 거부 · evil.com 거부 · webhook.site 정상 add→list→remove round-trip
- settings.json 자동 백업 후 정상 JSON 쓰기 확인
- i18n 26 키 추가 × ko/en/zh (policy_fallback_* · fwd_*)

---
## [2.28.0] — 2026-04-23

### 🔧 RTK init 근본 수정 + 🌐 번역 완전성 + 🛡 보안 감사

사용자 리포트 3건: RTK 자동 설치가 N 으로 되어버림, 번역 누락, 신규 코드 보안 점검.

**🔧 RTK `init` 근본 수정 — `--auto-patch` 플래그로 교체**
- 기존 `yes | rtk init -g` 는 오히려 rtk 의 `is_terminal()` 감지로 "stdin not a terminal → default No" 로 빠져 훅이 설치되지 않았음
- [`rtk-ai/rtk/src/hooks/init.rs`](https://github.com/rtk-ai/rtk/blob/master/src/hooks/init.rs) 소스 확인: `--auto-patch` 공식 플래그로 프롬프트 스킵 가능
- `api_rtk_init` → `rtk init -g --auto-patch` 로 변경 + UI 토스트 문구 조정

**🌐 번역 완전성 — 71 한국어 잔여 제거**
- `t('key', '한국어 fallback')` 의 긴 한국어 fallback 들이 `extract_ko_strings.py` 에 의해 audit 에 수집되어 `locales/{en,zh}.json` 에 `key=한국어 identity / value=한국어` 로 등록되어 있었음 (ko 원문 그대로 노출)
- `translations_manual_9.py` 의 `NEW_EN` / `NEW_ZH` 양쪽에 71 항목 × 3 언어 추가 번역 일괄 등록
- 결과: `en.json` · `zh.json` 내 한국어 잔여 **71 → 0**
- 전수 검증: `python re '[가-힣]'` 매칭 0건

**🛡 보안 감사 — v2.24~v2.27 신규 코드 방어 강화**

1. **`session_replay.py` 경로 boundary 체크 강화** (v2.25.0 에 `pass` 로 무력화되어 있었음)
   - `try/pass` 블록을 실제 `resolve(strict=True)` + `relative_to(_PROJECTS)` 검증으로 교체
   - symlink 경유 경로 탈출 차단
   - 공격 시도 테스트: `../../../../etc/passwd` · `/etc/passwd` · `abc/..` · `..` 모두 `invalid path` 반환

2. **`notify.py` HTTP redirect 차단** (defense-in-depth)
   - 기존 `urllib.request.urlopen` 은 3xx 자동 추종 → 이론상 화이트리스트 호스트에서 다른 호스트로 redirect 유도 가능
   - `_NoRedirect` 핸들러 + 전용 opener 로 리다이렉트 전면 차단
   - Slack/Discord webhook 은 일반적으로 리다이렉트 없음 → 기능 영향 없음

3. **감사 대상** (조치 불필요):
   - `rtk_lab.api_rtk_uninstall_hook` — 백업 자동 생성 + `_is_rtk_hook` 휴리스틱 OK
   - `prompt_library.find_keyword_triggers` — 로컬 단일 사용자 전제, UI 에서 키워드 가시 관리
   - `policy.tokenBudgetTotal` sanitize 0~1억 경계 OK

**검증**
- 54/54 탭 smoke 통과
- i18n 3 언어 정합성 + 한국어 잔여 0
- 공격 시도 4 경로 · 잘못된 host 1 케이스 모두 차단

---
## [2.27.0] — 2026-04-23

### 🏗️ Team Sprint 템플릿 + 워크플로우 전역 토큰 예산 정책 (backlog B6 + Policy)

**B6 · Team Sprint 빌트인 템플릿 (`bt-team-sprint`)**
- OMC `omc team 3:executor` 의 5단계 파이프라인을 단일 DAG 로:
  - 🧭 Plan (Opus) → 📋 PRD (Sonnet) → 👷 Exec ×3 병렬 (Sonnet) → 🔀 Merge → 🔎 Verify (Haiku) → Branch `PASS?` → ✅ Out / 🛠️ Fix
- Verify 실패 시 피드백 자동 주입해 Plan 단계부터 최대 3회 repeat 루프 (bt-ralph 패턴 응용).
- 11 노드 · 12 엣지 · repeat(maxIterations=3, feedbackNodeId=n-plan).
- 빌트인 템플릿 9 → 10.

**Policy 프리셋 — 워크플로우 전역 토큰 예산 (`workflow.policy.tokenBudgetTotal`)**
- `_sanitize_workflow` 에 `policy` 필드 추가:
  - `tokenBudgetTotal`: 0 (unlimited) ~ 100,000,000 토큰
  - `onBudgetExceeded`: `"stop"` (기본) | `"warn"` — 현재는 stop 만 동작
- `_run_one_iteration` 의 level 루프 시작부에 누적 토큰 집계:
  - `sum(tokensIn + tokensOut for 완료된 노드)` ≥ 예산 → 남은 모든 노드를 `budget_exceeded` 상태로 표시 후 iteration 조기 종료
  - 부분 결과는 유지 (status="ok" 로 종료, `budgetExceeded: true` 플래그)
- 에디터 인스펙터에 **🛡 실행 정책** 섹션 — 예산 입력 필드 + 힌트

**i18n** — `policy_heading` / `policy_budget_label` / `policy_budget_hint` 3 키 × ko/en/zh.

**검증**
- 54/54 탭 smoke · 템플릿 10건 조회 확인
- Policy round-trip: `{tokenBudgetTotal: 1234}` 저장 → 조회 시 `{tokenBudgetTotal: 1234, onBudgetExceeded: "stop"}` 정상 반환
- Sanitize 3 케이스 (정상/음수/거대값) 경계 확인

---
## [2.26.0] — 2026-04-23

### 🧭 사이드바 UX 개편 — 6 상위 카테고리 + hover flyout

사용자 피드백: "카테고리가 너무 많아서 보기 어려운데, 상위 카테고리를 만들고 마우스가 가까이가면 바가 열리면서 상세 카테고리를 고를 수 있게 해줘. 형태나 양식이 비슷한 것들을 모아줘."

**재분류 (6 → 6, 의미 재정비)**
- `new` → **Learn** 🆕 — 신기능 · 온보딩 · Claude Docs · 가이드 (4)
- `main` → **Main** 🏠 — 대시보드 · 프로젝트 · **plans(이동)** · 통계 · AI 평가 · 세션 (6)
- `work` 분할 → **Build** 🔀 (워크플로우/에이전트/프롬프트 8) + **Playground** 🧪 (API 실험실 12)
  - Build: workflows · promptLibrary · rtk · projectAgents · agents · skills · commands · agentSdkScaffold
  - Playground: aiProviders · promptCache · thinkingLab · toolUseLab · batchJobs · apiFiles · visionLab · modelBench · serverTools · citationsLab · embeddingLab · sessionReplay
- `advanced` 해체 → **Config** ⚙️ 로 흡수 (13). plans 만 Main 으로.
- `system` → **Observe** 📊 — 비용/메트릭/세션 관측 (11)

**UX**
- `renderNav()` 전면 재작성: `nav-category` (상위 6) 만 사이드바에 표시, 각 `nav-category` 자식으로 `nav-flyout` (서브 탭 목록) 포함.
- 호버/포커스/클릭 모두로 flyout 열기 — `hover: `, `:focus-within`, `.open` 트리거.
- 현재 탭이 속한 카테고리에 `.has-active` + 주황 dot · drop-shadow 강조.
- 탭 클릭 시 `go(id)` + flyout 자동 닫기.
- ESC 로 모든 flyout 닫기. 사이드바 바깥 클릭으로도 닫힘.
- 모바일(max-width: 900px) 에선 flyout 이 아코디언 (position static, hover 비활성, click 만).

**CSS**
- `.nav-category`, `.nav-cat-icon/meta/label/dot/desc/count/chevron`, `.nav-flyout`, `@keyframes navFlyoutIn` 신규.
- `#nav` 의 `overflow-y-auto` → `overflow: visible` (flyout 이 오른쪽으로 튀어나올 수 있게).
- 6 카테고리뿐이라 스크롤 불필요 (viewport 900 에서 footer 까지 여유).

**서버 `nav_catalog.py`**
- `TAB_GROUPS` 재정의 (6 상위).
- `_new_group()` remap: 기존 `TAB_CATALOG` 엔트리의 legacy group 을 runtime 에 신규 group 으로 변환 — 챗봇 프롬프트(`render_tab_catalog_prompt`) 도 새 카테고리 기준.
- `plans` 만 main 으로 수동 예외.

**검증**
- 54/54 탭 smoke 통과
- Playwright 시각 체크: 6 카테고리 사이드바 + Playground hover 시 12 항목 flyout 펼쳐짐, 워크플로우 콘텐츠 정상 공존.
- 챗봇 프롬프트 확인: Learn/Main/Build/Playground/Config/Observe 로 정렬됨.

---
## [2.25.1] — 2026-04-23

### ⚡ 자율모드 빠른 개선 3건 (C1~C3)

v2.25.0 이후 backlog 의 "quick wins" 를 자율모드로 일괄 반영.

**C1 · RTK 탭 스크린샷을 README 3종에 반영**
- 이미 생성되어 있던 `docs/screenshots/{ko,en,zh}/rtk.png` (각 200KB+) 가 README 에서 참조되지 않고 있던 것을 정리.
- 영문/한글/중문 README 의 스크린샷 섹션 하단에 "Token Optimization / 토큰 최적화 / Token 优化" 섹션 추가.

**C2 · CostsTimeline 주/월별 뷰 토글**
- `VIEWS.costsTimeline` 차트 헤더에 `일 / 주 / 월` 토글 버튼 추가.
- 클라이언트 사이드에서 일별 `days` 데이터를 ISO 주(월요일 시작) / YYYY-MM 단위로 재집계 (`_costsBucket` 헬퍼).
- `state.data._costsBucket` 으로 선택 상태 유지, 탭 재진입 시 복원.

**C3 · Workflow run diff 에 토큰/비용 변화량**
- `api_workflow_run_diff` 응답 확장:
  - 노드별: `aTokensIn/Out`, `bTokensIn/Out`, `tokensInDelta`, `tokensOutDelta`, `aCostUsd`, `bCostUsd`, `costDelta`
  - 요약: `a/b.tokensIn/Out/costUsd`, `tokensInDelta`, `tokensOutDelta`, `costDelta`
- UI 테이블에 `Δ 토큰` `Δ 비용` 컬럼 추가, 하이라이트 조건에 토큰 변화 반영.
- 요약 줄에 `A tok $` · `B tok $` · `Δ 토큰` · `Δ 비용` 모두 노출.

**i18n** — costs_bucket_day/week/month · 토큰 · diff_highlight_hint 등 8 키 추가 × ko/en/zh.

**검증**
- 54/54 탭 smoke 통과
- CostsTimeline Playwright smoke — day/week/month 헤더 전환 모두 확인
- i18n 정합성 통과

---
## [2.25.0] — 2026-04-23

### 🆕 OMC/OMX gap 흡수 세션 (자율모드 큐 소진)

사용자 요청: `oh-my-claudecode` (OMC) / `oh-my-codex` (OMX) 분석 후 LazyClaude 에 없는 기능 중 low 위험도 항목을 자율모드로 일괄 반영.  
분석 노트: `docs/plans/analysis-omc-omx-gap.md`, 큐: `docs/plans/today-queue.md`, 로그: `docs/logs/2026-04-23.md`.

**B1 · 실행 모드 빌트인 템플릿 4종 (work 그룹)**
- `bt-autopilot` — 요구사항 → 계획 → 실행 → 검증 단일 흐름 (OMC `/autopilot`)
- `bt-ralph` — verify → fix 루프 (repeat enabled, max 5, feedback auto-inject · OMC `/ralph`)
- `bt-ultrawork` — 5 병렬 에이전트 → merge (Sonnet×2, Haiku×3 · OMC `/ultrawork`)
- `bt-deep-interview` — Socratic 명확화 → 설계 문서 (OMC `/deep-interview`)
- 총 빌트인 템플릿 5→9

**B2 · Prompt Library 키워드 트리거 (OMC `ultrathink`/`deepsearch` 대응)**
- `keywords: string[]` 필드 추가 (최대 10)
- 워크플로우 session 노드 실행 시 입력 텍스트에 키워드 매칭되면 해당 프롬프트 body 가 systemPrompt 앞에 자동 prepend
- 에디터에 키워드 입력란 + 설명

**B3 · 워크플로우 완료 알림 — Slack / Discord (OMC `config-stop-callback` 대응)**
- 신규 모듈 `server/notify.py` — `hooks.slack.com` / `discord.com` / `discordapp.com` 호스트 화이트리스트, https-only
- 워크플로우 저장 스키마에 `notify: {slack, discord}` 필드 (sanitize 에서 URL 검증)
- run 성공/실패 시 이모지 + 상태 + 실행 시간 + 비용 + 요약 500자 전송
- `POST /api/notify/test` — UI 테스트 버튼 (`target: slack|discord`, `url`)
- 에디터 인스펙터에 Webhook URL 섹션 + 테스트 버튼

**B4 · session 노드 modelHint — 자동 모델 라우팅 (OMC smart routing 대응)**
- session 노드 data 에 `modelHint: "" | "auto" | "fast" | "deep"`
- assignee 가 비어있을 때만 적용 (명시적 지정이 우선, backward compat)
- fast → haiku, deep → opus, auto → 휴리스틱 (길이 + 키워드)
  - 3000+ 문자 또는 architect/design/deep 키워드 → opus
  - 500- 문자 + list/summary/quick 키워드 → haiku
  - 그 외 → sonnet
- 실행 결과에 `chosenModel` 필드 노출

**B5 · Session Replay Lab 신규 탭 (`sessionReplay`, work 그룹)**
- 신규 모듈 `server/session_replay.py` — `~/.claude/projects/**/*.jsonl` 스캔
- 최근 50 세션 목록 + 개별 파싱 (최대 2000 events) — role · 요약 · tool_use 마커 · tokens · timestamp
- 좌측 세션 목록 + 우측 타임라인 (색상별 role · 툴 호출 하이라이트)
- 누적 토큰 스파크라인 (600×40 SVG path)
- 54 탭으로 확장

**분석 문서 (기록)**
- `docs/plans/analysis-omc-omx-gap.md` — OMC/OMX vs LazyClaude 매트릭스 + 흡수 후보 HIGH/MED/LOW 분류 + 추가 최적화 포인트
- `docs/plans/backlog.md` — 자율모드 제외(medium 위험) 항목 + MCP 서버 모드 등 향후 후보

**통계**
- 탭: 53 → 54
- API 라우트: 192 → 198
- 빌트인 템플릿: 5 → 9
- 54/54 탭 smoke 통과 · i18n ko/en/zh 정합성 통과 (키 추가 ~15)

---
## [2.24.1] — 2026-04-23

### 🔁 RTK 자동화 — 설치/훅 완료 자동 감지 + y/n 자동 응답

사용자 피드백 2건 반영:
1. 설치 완료 후 탭 새로고침을 수동으로 해야 함 → 자동 감지 + renderView
2. `rtk init -g` 가 묻는 y/n 프롬프트를 수동 응답해야 함 → `yes` 파이프로 자동

**백엔드 (`server/rtk_lab.py::api_rtk_init`)**
- 명령 변경: `rtk init -g` → `yes | rtk init -g`
- `yes` 는 모든 확인 프롬프트에 `y` 자동 응답. rtk 가 stdin 을 쓰지 않으면 `yes` 가 SIGPIPE 로 조기 종료되어 부작용 없음.

**프런트 (`dist/index.html::_rtkStartPolling`)**
- `_rtkInstall()` 완료 시 `install` 모드 polling 시작 (2.5s 간격, 5분 타임아웃)
- `_rtkInit()` 완료 시 `hook` 모드 polling 시작 (1.5s 간격, 2분 타임아웃)
- polling 은 `/api/rtk/status` 를 주기 호출 → `installed` / `hookInstalled` true 되면 `renderView()` + toast
- RTK 탭을 떠나면 `go()` / `hashchange` 에서 `_rtkStopPolling()` 호출로 polling 정리
- 현재 탭이 RTK 가 아니면 renderView 없이 toast 알림만

**i18n** 10 키 추가 × ko/en/zh (rtk_polling_* / rtk_detected_*).

---
## [2.24.0] — 2026-04-23

### 🦀 New tab: RTK Optimizer (`work` group)

Claude 토큰 **60-90% 절감** 하는 Rust CLI 프록시 [`rtk-ai/rtk`](https://github.com/rtk-ai/rtk) 를 대시보드에서 바로 설치·활성화·통계 조회 가능한 탭으로 통합.

**신규 모듈: `server/rtk_lab.py`**
- 설치 여부 감지 — `_which("rtk")` 로 PATH + homebrew/cargo 경로 fallback
- 설정 파일 경로 OS 분기 (macOS: `~/Library/Application Support/rtk/config.toml`, Linux: `$XDG_CONFIG_HOME/rtk/config.toml`)
- Claude Code settings.json 내 `rtk` 참조 탐지로 훅 활성 상태 체크
- 6가지 명령 그룹 카탈로그 (file · git · test · build · analytics · utility)

**신규 라우트 6건**
- GET `/api/rtk/status` · `/api/rtk/config` · `/api/rtk/gain` · `/api/rtk/session`
- POST `/api/rtk/install` · `/api/rtk/init`
- 설치/init 은 기존 `cli_tools._run_in_terminal` 재사용 → AppleScript 로 Terminal 창 대화형 실행

**설치 경로 3종**
- `brew install rtk` (Homebrew 있을 때 기본)
- `curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh`
- `cargo install --git https://github.com/rtk-ai/rtk`

**UI — `VIEWS.rtk`**
- 상태 카드 3열 (설치 상태 + 훅 활성 / 설정 파일 경로 / 참고 링크)
- 미설치 시: 설치 방법 버튼 (Homebrew · curl · Cargo — 환경별 노출)
- 설치 시: `rtk init -g` 훅 설치 버튼 + 누적 절감 통계 (`rtk gain`) + 세션 내역 (`rtk session`) 실시간 조회
- 명령 레퍼런스 6 그룹 그리드 — chip 단위 빠른 참조 + `-u/--ultra-compact` 힌트

**i18n** 28 키 추가 × ko/en/zh → 3,281 키 정합성 통과.

**LazyClaude 마스코트 (`docs/logo/mascot.svg`)**
- 기존 오렌지 픽셀 캐릭터 (`#E07C4C`) 를 정적 로고로 변환
- "lazy" 정체성 강조 — 눈을 감은 표정 (sleeping slits) + `Zzz` 인디케이터 + 볼 홍조
- 애니메이션 제거 (GitHub README 는 SVG `<style>` 차단) → 정적 포즈만
- README 3종 Hero 섹션 아래에 `<img>` 임베드

**기타**
- `dist/index.html`: 잔여 `Claude Control Center` 4곳 (title · 사이드바 · 온보딩 모달) → `LazyClaude`
- nav 카탈로그 · TAB_DESC_I18N 갱신 (52탭 → 53탭)
- e2e-tabs-smoke 53/53 통과

---
## [2.23.2] — 2026-04-23

### 📸 Docs — 언어별 스크린샷 36장 + UI 브랜드 텍스트 정리

사용자 리포트 2건 반영:
1. 영문 README 가 한글 UI 스크린샷을 참조
2. `AI Providers` / `Costs Timeline` 이 빈 화면으로 캡처됨

**`scripts/capture-screenshots.mjs` 전면 재작성**
- 12 탭 × 3 언어 = 36장 → `docs/screenshots/{ko,en,zh}/<tab>.png`
- `?lang=en|zh` 쿼리로 UI 언어 전환 후 캡처 (context 재생성)
- `waitForLoadState('networkidle')` + 탭별 selector + `waitForResponse('/api/ai-providers/list')` + chip 개수 `waitForFunction` — zh/en 에서 `aiProviders` 가 스켈레톤 상태로 찍히던 문제 해결
- `page.route('**/api/cost-timeline/summary', ...)` 로 Costs Timeline 모의 응답 주입 (14일 × 5 소스 × 147건 · 총 $12.38) — 실 API 호출 없이 의미있는 스택 차트 생성
- overview 탭의 Claude 계정 온보딩 모달을 `Continue|계속|继续` 버튼 자동 클릭으로 통과
- 워크플로우 시드 선택 fallback: `_wfOpen` → `_wfSelect` → 직접 `__wf.current` 할당

**`dist/index.html` UI 브랜드 텍스트 정리**
- `<title>` · 사이드바 브랜드 · 계정 온보딩 모달 헤더 등 4곳의 `Claude Control Center` → `LazyClaude` 치환 (리브랜딩 일관성)

**README 3종 이미지 경로 분기**
- `./docs/screenshots/*.png` → `./docs/screenshots/{ko,en,zh}/*.png` (각 README 자신의 언어로)

**검증**
- 36/36 캡처 성공
- 각 언어에서 overview (최적화 점수 21 · 6171 세션 렌더) · aiProviders (8 프로바이더 카드) · costsTimeline (스택 차트 + 소스별 집계) · workflows ([Demo] Multi-AI Compare DAG) 시각 확인

---
## [2.23.1] — 2026-04-23

### 🎨 Branding — 프로젝트 이름을 **LazyClaude** 로

레퍼런스: [`Yeachan-Heo/oh-my-claudecode`](https://github.com/Yeachan-Heo/oh-my-claudecode) 의 README 스타일 참고.

- **브랜드 네임**: `Claude Control Center` → `💤 LazyClaude`
  - 네이밍 톤: `lazygit` / `lazydocker` / `lazyvim` 패밀리 편승. 게으른 사람을 위한 로컬 Claude 커맨드 센터.
  - 캐치프레이즈: "Don't memorize 50+ CLI commands. Just click." / "50+ 개 CLI 명령어 외우지 마세요. 그냥 클릭하세요."
- **README 3종 (ko/en/zh)**
  - Hero 섹션을 `<div align="center">` 중앙 정렬, 태그라인 + 캐치프레이즈 상단에 배치.
  - Quick Start 를 "1 · 클론 / 2 · 실행 / 3 · 접속" 3단계 박스 스타일로 재구성.
  - 장문 "v2.x 신기능" 나열을 "최근 업데이트" 테이블 (6 행) 로 압축.
  - ASCII 배너 내 `🧭 Claude Control Center` → `💤 LazyClaude`.
  - Contributing 섹션: 1인 메인테이너 개인 프로젝트임을 명시, "core team" 같은 구절 제거. PR 유도 톤은 유지.
  - Acknowledgements 에 lazygit/lazydocker 크레딧 추가.
  - 하단에 "Made with 💤 for those who'd rather click than type." 서명.
- **기술 경로 유지** (하위 호환):
  - Repo URL `github.com/cmblir/claude-dashboard` 유지 (rename 은 사용자 선택 사항).
  - 데이터 파일 `~/.claude-dashboard-*.json` 경로 유지 — 기존 사용자 데이터 보존.
  - 내부 변수명·모듈명 변경 없음.

---
## [2.23.0] — 2026-04-23

### 🛡 Security — Webhook 인증 + Output 경로 화이트리스트 (v2.22 보안 감사 후속)

v2.22.0 SSRF 가드 직후 남아있던 MEDIUM 2건을 마무리. 로컬 `127.0.0.1:8080` 바인딩 전제라 실위협은 제한적이지만, 원격 포워딩·컨테이너 공유 환경을 대비해 선반영.

**Finding 2 · Webhook 무인증 → `X-Webhook-Secret` 필수 (`server/workflows.py`)**
- 워크플로우마다 `webhookSecret` 필드 보관. `POST /api/workflows/webhook/<wfId>` 호출 시 헤더 필수.
- 비교는 `hmac.compare_digest` — 타이밍 공격 방어.
- secret 미발급 상태면 401 응답으로 호출 차단 (`err_webhook_no_secret`).
- 저장 API (`/api/workflows/save`) 로는 secret 을 변경할 수 없음 (기존값만 보존). 전용 API 로만 관리.

**신규: `POST /api/workflows/webhook-secret`**
- `{action: "get"}` 현재값 조회
- `{action: "generate"}` 미발급 시 발급, 이미 있으면 기존값
- `{action: "rotate"}` 새 값으로 교체 (기존 호출자 모두 401)
- `{action: "clear"}` 제거 — webhook 비활성화
- 생성: `secrets.token_urlsafe(32)` → 43자 URL-safe base64

**UI · 워크플로우 에디터 우측 인스펙터**
- Webhook URL 아래 Secret 패널 추가. 상태(발급/미발급) 표시.
- 버튼: 🔐 Generate · 🔄 Rotate · 🚫 Clear · 👁 Show/Hide · 📋 Copy
- `curl` 예시에 `-H "X-Webhook-Secret: ..."` 자동 삽입 (실값 반영).
- rotate/clear 는 confirm 모달로 이중 확인.

**Finding 3 · Output 노드 `exportTo` 경로 화이트리스트 (`server/workflows.py`)**
- 기존 `_under_home` (`~/` 하위 모두 허용) → 신규 `_under_allowed_export` (`~/Downloads` · `~/Documents` · `~/Desktop` 만 허용).
- `os.path.realpath` 로 symlink 완전 해제 후 비교 → `~/Documents/../.ssh/x` 같은 traversal 차단.
- 허용 경로 밖이면 노드 실행 단계에서 명시적 에러.

**i18n · 한/영/중**
- 17 항목 추가 (`webhook_secret_*` 9 + 표시/숨김 등). 3,253 키로 정합성 검증 통과.

**검증**
- `e2e-tabs-smoke.mjs` 52/52 통과
- `verify:i18n` 통과 (3,253 ko/en/zh 키 집합 일치)
- curl E2E: no-secret → 401, wrong → 401, rotate 후 옛 값 → 401, 새 값 → 200
- 경로 화이트리스트 단위 테스트: `/etc/passwd`, `~/../etc/passwd`, `~/.ssh/id_rsa`, `/tmp/foo.txt`, `~/Documents/../.ssh/x` 모두 차단 확인

---
## [2.22.1] — 2026-04-23

### 📸 Docs — README 3종에 스크린샷 12장 삽입

사용자 피드백: "글만 보고 어떤식으로 나오는지 알 수 없잖아". 실제 UI 보여주는 스크린샷 자동 생성 + README 임베드.

**신규: `scripts/capture-screenshots.mjs`**
- Playwright 로 주요 12 탭을 1440×900 @2x (레티나) 로 캡처
- `docs/screenshots/<tab>.png` 에 저장
- workflows 탭은 `bt-multi-ai-compare` 템플릿 시드 후 `_wfFitView()` 로 전체 DAG 노출
- promptCache 탭은 예시 1개 로드 후 캡처
- 캡처 완료 시 `[Demo]` 시드 워크플로우 자동 정리

**캡처 대상 (12)**
- `overview` · `workflows` · `aiProviders` · `costsTimeline`
- `promptCache` · `thinkingLab` · `toolUseLab` · `modelBench`
- `claudeDocs` · `promptLibrary` · `projectAgents` · `mcp`

**총 용량**: ~2.4MB (탭당 100~330KB · PNG 레티나). Git 저장소에 직접 commit.

**README 3종 구조**
- ASCII 미리보기 박스 바로 아래 `### 📸 Screenshots / 스크린샷 / 截图` 섹션 추가
- 4개 카테고리 × 2열 markdown 표 (메인 / 멀티AI·비용 / API 플레이그라운드 / 지식·재사용)
- `![label](./docs/screenshots/tab.png)` 상대 경로 → GitHub raw 렌더 호환

**package.json scripts.screenshots** 추가: `npm run screenshots` 로 재생성.

**사전 요건**: 서버가 `127.0.0.1:8080` 에서 기동 중이어야 함 + `npx playwright install chromium` 완료.

## [2.22.0] — 2026-04-23

### 🔒 Security — 워크플로우 HTTP 노드 SSRF 가드 (Finding 1 fix)

보안 감사에서 발견된 **HIGH** 급 SSRF 취약점 수정. 기존 `_execute_http_node` 가 URL 의 scheme/host 검증 없이 `urllib.request.urlopen` 을 호출해 **DNS rebinding / CSRF / 악성 워크플로우 import** 시 다음 공격이 가능했음:

- 클라우드 메타데이터 (`http://169.254.169.254/`) 접근 → 자격 증명 유출
- 로컬/사설 네트워크 포트 스캔 (`http://127.0.0.1:6379`, `http://192.168.x.x:*`)
- `file://`, `ftp://`, `gopher://` 등 비-HTTP 스킴을 통한 파일 읽기 / 내부 호출

**수정 내역**
- `server/workflows.py::_execute_http_node`:
  * scheme 화이트리스트: `http`, `https` 만 허용. 그 외는 `"scheme blocked"` 에러.
  * 호스트 블랙리스트: `127.0.0.1 · 0.0.0.0 · ::1 · localhost · 169.254.169.254 · metadata.google.internal · metadata.goog · fd00:ec2::254`
  * 사설/링크로컬 프리픽스 차단: `10.*`, `127.*`, `169.254.*`, `172.16~31.*`, `192.168.*`, IPv6 `fc*/fd*/fe80~feb*`
  * **DNS rebinding 방어**: 호스트가 DNS 이름일 때 `getaddrinfo` 로 실제 IP 를 해석 후 재검사. 해석 실패 시 `fail-closed`.
- **옵트인 우회**: 노드 `data.allowInternal = true` 로 체크 시만 내부 호출 허용. UI 에 경고 박스 + 체크박스 (기본 off).
- `dist/index.html::VIEWS.workflows` HTTP 노드 에디터에 체크박스 추가 + 신규 HTTP 노드 data 기본값에 `allowInternal: false` 명시.
- `tools/translations_manual_9.py`: 2 키 × ko/en/zh 추가.

**영향도**
- **공격 차단**: 외부 공격자의 DNS rebinding 이나 악성 워크플로우 JSON import 를 통한 내부 네트워크 접근 원천 차단.
- **호환성**: 기존 워크플로우의 외부 API 호출 (`api.openai.com`, `api.anthropic.com` 등) 은 영향 없음. 로컬 테스트용 호출(`http://localhost:3000`) 은 UI 에서 체크박스 켜야 동작.

**감사 출처**: `/security-review` 스킬 · `Obsidian/logs/2026-04-23-security-audit.md` 에 상세 기록.

## [2.21.1] — 2026-04-23

### Docs — README 3종 통계 v2.21.1 기준 갱신 (세션 5 결과)

T15~T17 (v2.19.0 · v2.20.0 · v2.21.0 docs) 반영:
- 버전 배지 v2.18.1 → **v2.21.1**
- 51 → **52 tabs** (costsTimeline 추가)
- 178→188→**190** routes (GET 102 / POST 85 / PUT 3)
- 3,212 → **3,234** i18n keys × 3언어
- Stats 섹션: 백엔드 ~17,600/44 → **~18,000/46 modules** · 프론트 ~16,300→**~16,600**
- **신규 행**: "Unified cost timeline ✓ · Workflow run diff/rerun ✓"
- README ko/en/zh 3종 동등 갱신
- `npm run test:e2e:smoke` 52/52 tabs (comment 업데이트)

## [2.21.0] — 2026-04-23

### 📐 Docs — Artifacts 로컬 뷰어 설계 문서 (구현 X)

B6 (Claude.ai Artifacts 의 로컬 대안) 을 안전하게 구현하기 위한 **설계 선행**. 실제 코드는 다음 세션 (T20~T23, v2.22~v2.24) 에 나누어 진행.

**저장 위치**: `Obsidian/Projects/claude-dashboard/decisions/2026-04-23-artifacts-design.md`

**핵심 보안 4중 방어**
1. **iframe sandbox**: `srcdoc` 로 origin = null · `sandbox="allow-scripts"` (allow-same-origin 제외) → cookie / localStorage / IndexedDB 불가
2. **CSP via srcdoc meta**: `default-src 'none'; script-src 'unsafe-inline'; connect-src 'none'` → 외부 fetch 차단 (CSS exfiltration 포함)
3. **postMessage 화이트리스트**: `artifact:ready` / `artifact:resize` / `artifact:error` / `artifact:theme` 외 모두 무시. `event.origin` 검사
4. **정적 코드 필터**: `import from 'https://'`, `navigator.credentials`, `document.cookie`, `localStorage`, `indexedDB` 패턴 발견 시 거부 + confirmModal 승인 필요

**릴리스 로드맵**
- v2.22.0 — `server/artifacts_lab.py` (extract/save/list/delete) + 4 라우트
- v2.23.0 — `VIEWS.artifacts` UI + 샌드박스 iframe + postMessage 프로토콜
- v2.24.0 — Babel standalone **로컬 번들** (supply chain 면역) + React/JSX 지원
- v2.24.1 — Playwright `e2e-artifacts.mjs` 5 테스트 케이스 (CSP 차단 · sandboxed origin · postMessage 필터 · 금지 패턴 · 강제 렌더)

**의사결정 (Open → Closed)**
- Babel: CDN ❌ · **로컬 번들** ✅ (공급망 안전)
- Artifact 외부 공유: **완전 불가**. 로컬 JSON export 만
- 강제 렌더: 매번 confirmModal (세션 skip 옵션 없음)

## [2.20.0] — 2026-04-23

### 💸 비용 타임라인 통합 탭 — 신규 `costsTimeline` (system 그룹)

Claude API 플레이그라운드 10종 + 워크플로우 실행 비용을 **한 화면**에 통합.

**기능**
- 상단 카드 3개: 총 비용 · 총 호출 수 · 활성 소스 (10 플레이그라운드 + workflows)
- **일별 비용 차트** (최근 60일) — SVG 수평 막대 · 소스별 스택 색상
- **소스별 집계 테이블**: 호출 수 · 토큰 in/out · USD
- **모델별 집계** (Top 20)
- **최근 30건 리스트**

**Architecture**
- `server/cost_timeline.py` 신설 — 각 `~/.claude-dashboard-*.json` 히스토리를 통합 집계
- 처리 소스 (10 + workflows):
  * promptCache / thinkingLab / toolUseLab / batchJobs / apiFiles / visionLab / modelBench / serverTools / citationsLab + workflows(store costs 배열)
- 엔트리 없는 USD 값은 `_estimate(model, ti, to)` 로 재계산 (Opus/Sonnet/Haiku 가격표)
- `server/routes.py` 라우트 1 추가 (`GET /api/cost-timeline/summary`)
- `server/nav_catalog.py` `costsTimeline` 탭 등록 (system 그룹) + en/zh
- `dist/index.html` NAV (icon 💸) + `VIEWS.costsTimeline` — SVG 스택 차트 + 3 테이블
- `tools/translations_manual_9.py` 18 키 × ko/en/zh

## [2.19.0] — 2026-04-23

### 📜 워크플로우 실행 이력 diff / 재실행

기존 `📜 이력` 모달을 확장. 각 run 카드에 **🔍 diff** + **🔄 재실행** 버튼.

**🔍 diff**
- 바로 직전 run 과 per-node 비교 테이블
- 컬럼: 노드 id · A status · A duration · B status · B duration · Δ
- 상태 변화 또는 한쪽에만 있는 노드는 하이라이트
- 상단 요약: A/B 전체 status · duration · Δ

**🔄 재실행**
- 현재 선택된 워크플로우를 즉시 재실행 (기존 `api_workflow_run` 재사용)
- SSE 폴링 자동 시작 → 배너 등장

**Architecture**
- `server/workflows.py` 신규 `api_workflow_run_diff(body: {a, b})` — 두 runId 의 `nodeResults` 비교 → node 별 status/duration Δ + onlyA/onlyB 플래그
- `server/routes.py` 라우트 1 추가 (`POST /api/workflows/run-diff`)
- `dist/index.html::_wfShowRuns` 확장: run 카드에 diff/rerun 액션
- `_wfDiffRuns(aId, bId)` / `_wfRerunWorkflow()` 신규 함수
- `tools/translations_manual_9.py` 10 키 × ko/en/zh

**스모크**
- `/api/workflows/run-diff` 신규 엔드포인트 정상
- 워크플로우 탭 "📜 이력" 모달에서 각 run 카드에 diff/재실행 버튼 노출 확인

## [2.18.1] — 2026-04-23

### Docs — README 3종 통계 갱신 (세션 4 결과 반영)

T10~T13 (v2.15.0 ~ v2.18.0) 신규 3 탭(embeddingLab + promptLibrary + Batch 가드 UI) + E2E 확장이 README 본문에 반영되도록 일괄 갱신.

- 버전 배지 v2.14.1 → **v2.18.1**
- 49 → **51 tabs / 51 탭 / 51 个标签页**
- work 그룹 테이블에 🆕 `embeddingLab` · `promptLibrary` 추가 (serverTools/citationsLab/agentSdkScaffold 는 기존으로 이동)
- Architecture 트리: routes 178 → **188**, nav 49 → **51 tabs**, locales 3,157 → **3,212 keys**
- Stats 섹션을 **v2.18.1** 기준으로 전면 갱신:
  * 백엔드 ~17k/42 → **~17,600줄/44 모듈**
  * 프론트 ~15,500줄 → **~16,300줄**
  * API 라우트 178 → **188** (GET 101 / POST 84 / PUT 3)
  * 플레이그라운드 탭 10 → **11** (+ Embedding Lab)
  * **신규 행**: Prompt Library ✓, Batch 비용 가드 ✓, E2E 테스트 스크립트 **3**
- E2E 테스트 섹션에 `test:e2e:ui` · `test:e2e:all` 추가 (smoke 51 tabs 재반영)
- README ko/en/zh 3종 동등 갱신

## [2.18.0] — 2026-04-23

### 🎭 E2E 커버리지 확장 (v2.10.x UX 회귀 방지)

**신규: `scripts/e2e-ui-elements.mjs`**

워크플로우 탭의 중요 DOM/전역 함수 무결성을 자동 검증. Anthropic API 키 없이도 동작.

**검증 항목**
1. 핵심 컨테이너 7개 (`#wfRoot` · `#wfCanvasWrap` · `#wfToolbar` · `#wfCanvasHost` · `#wfCanvas` · `#wfViewport` · `#wfMinimap`)
2. 빌트인 `bt-multi-ai-compare` 로 임시 워크플로우 생성 → `.wf-node` 6개 렌더 확인 → 자동 정리
3. **v2.10.0 UX**: `.wf-node-ring` / `.wf-node-elapsed` 각 6개 존재 · `_wfRenderRunBanner` 전역 노출 · mock running run 으로 `#wfRunBanner.visible` 부착 검증
4. **v2.10.1 UX**: `_wfToggleCat` 전역 노출
5. **v2.10.2 UX**: `_wfShowNodeTooltip` 전역 노출
6. `pageerror` / `console.error` 집계 → 하나라도 있으면 실패

**package.json scripts 추가**
- `test:e2e:ui` → `node scripts/e2e-ui-elements.mjs`
- `test:e2e:all` → smoke + ui 연속 실행

**검증 실행 결과 (v2.18.0)**
- `npm run test:e2e:ui` — 18개 체크 전부 통과
- `npm run test:e2e:smoke` — **51/51 탭 전수 통과**

## [2.17.0] — 2026-04-23

### 🚨 Batch 비용 가드 (batchJobs 확장)

Message Batches 제출 전 **예상 비용/토큰**을 계산해 임계치 초과 시 거부.

**설정**
- `~/.claude-dashboard-batch-budget.json` — `{enabled, maxPerBatchUsd, maxPerBatchTokens}`
- 기본: **disabled** · $1.00 · 100,000 tokens
- 사용자가 명시 활성화해야 작동 (기존 동작 유지)

**예상 비용 계산 (`_estimate_batch_cost`)**
- input_tokens 근사치 = Σ `len(prompt) // 4`
- output_tokens = `max_tokens × len(prompts)`
- 가격표: Opus/Sonnet/Haiku 3 모델 per-1M-token 단가
- **50% 할인 적용** (Anthropic Message Batches 공식 정책, 2026-04 기준)

**제출 시 플로우**
1. `api_batch_create` 상단에서 예상 계산
2. `budget.enabled` 이면 USD · tokens 두 임계치 모두 체크
3. 초과 시 `{ok:False, budgetExceeded:True, estimate, budget}` 반환
4. 프론트에서 confirmModal 로 차단 사유 + 예상 비용 · 토큰 상세 표시

**UI 추가**
- batchJobs 탭 상단에 **가드 상태 배너** (ON/OFF + 한도 표시 + ⚙️ 임계치 편집 버튼)
- "임계치 편집" 모달: enabled 토글 · maxPerBatchUsd · maxPerBatchTokens
- 제출 시 budgetExceeded 응답 오면 상세 모달 자동 노출

**Architecture**
- `server/batch_jobs.py` 확장: `_load_budget` · `_save_budget` · `_estimate_batch_cost` · `_PRICING` · `_BATCH_DISCOUNT=0.5` · `api_batch_budget_{get,set}`
- `api_batch_create` 에 pre-submit 가드
- `server/routes.py` 2 라우트 (GET budget · POST budget/set)
- `dist/index.html::VIEWS.batchJobs`: 가드 상태 배너 + `bjEditBudget` modal
- `bjSubmit` 에 `budgetExceeded` 분기
- `tools/translations_manual_9.py` 11 키 × ko/en/zh

## [2.16.0] — 2026-04-23

### 📝 Prompt Library — 신규 탭 `promptLibrary`

자주 쓰는 프롬프트를 태그와 함께 저장하고 검색 · 복사 · 복제 · **워크플로우로 변환** 가능한 라이브러리 탭.

**기능**
- CRUD 인라인 에디터: title · body · tags (쉼표 구분) · model
- 검색: 제목/본문/태그 substring (250ms debounce)
- 태그 chip 필터
- 카드별 액션 5개: 📋 복사 / ✏️ 수정 / 🗂️ 복제 / 🔀 워크플로우로 / 🗑️ 삭제
- 🔀 워크플로우로 — start → session(prompt) → output 3 노드 자동 생성 후 workflows 탭으로 이동
- 시드 3종 (코드 리뷰 / 회의 요약 / SQL 최적화)

**Architecture**
- `server/prompt_library.py` 신설 — `api_prompt_library_{list,save,delete,duplicate,to_workflow}` + SEED_ITEMS 3종
- 저장: `~/.claude-dashboard-prompt-library.json`
- workflows store 와 통합 (to-workflow 가 `_load_all/_dump_all/_new_wf_id` 사용)
- `server/routes.py` 5 라우트 (GET list · POST save/delete/duplicate/to-workflow)
- `server/nav_catalog.py` `promptLibrary` 탭 + en/zh
- `dist/index.html` NAV (icon 📝) + `VIEWS.promptLibrary` (에디터 + 카드 리스트 + 필터)
- `tools/translations_manual_9.py` 24 키 × ko/en/zh

## [2.15.0] — 2026-04-23

### 🧬 Embedding 비교 실험실 — 신규 탭 `embeddingLab`

같은 쿼리/문서 집합을 **Voyage AI · OpenAI · Ollama** 세 프로바이더에 돌려 cosine similarity + rank 를 비교.

**지원**
- Voyage AI — `voyage-3-large` / `voyage-3` / `voyage-3-lite` (VOYAGE_API_KEY 필요)
- OpenAI — `text-embedding-3-large` / `text-embedding-3-small`
- Ollama — `bge-m3` / `nomic-embed-text` / `mxbai-embed-large` (로컬)

**기능**
- 쿼리 1 + 문서 2~10 → 각 프로바이더 병렬 호출 → cosine + rank
- 프로바이더별 rank 나란히 + **rank Δ ≥ 2** 문서 자동 하이라이트
- 예시 2종 (FAQ 검색 / 유사 문장)
- 프로바이더별 모델 드롭다운 · 키 미설정 시 체크박스 비활성

**Architecture**
- `server/embedding_lab.py` 신설 — `api_embedding_{compare,providers,examples}`, `_cosine`, `_rank_desc`, `_voyage_embed` (stdlib HTTP)
- `ai_providers.embed_with_provider` 재사용 (OpenAI/Ollama)
- `ThreadPoolExecutor(max_workers=3)` 병렬 호출
- `server/routes.py` 3 라우트 (GET providers/examples · POST compare)
- `server/nav_catalog.py` `embeddingLab` 탭 + en/zh
- `dist/index.html` NAV (icon 🧬) + `VIEWS.embeddingLab` — 체크박스 · 인라인 모델 select · rank 테이블 · Δ 하이라이트
- `tools/translations_manual_9.py` 26 키 × ko/en/zh

## [2.14.1] — 2026-04-23

### Docs — README 3종 통계/탭 테이블 v2.14 기준 갱신

T5~T8 (v2.11.0 ~ v2.14.0) 신규 4 탭(serverTools · claudeDocs · citationsLab · agentSdkScaffold) 이 README 본문에 반영되도록 일괄 갱신.

- 배지 v2.9.1 → **v2.14.1**
- 미리보기 "45 탭" → **"49 탭"**
- Why 비교표 "45 tabs" → "49 tabs"
- Claude Code Integration 테이블:
  * 🆕 그룹에 `claudeDocs` 추가
  * 🛠️ Work 그룹에 `serverTools` · `citationsLab` · `agentSdkScaffold` 추가
- Architecture 트리: routes 168 → **178**, nav_catalog 45 → **49 tabs**, locales 3,090 → **3,157 keys**
- Stats 섹션을 v2.14.1 기준으로 갱신:
  * 백엔드 ~16,000줄/27 → **~17,000줄/42 모듈**
  * API 라우트 168 → **178** (GET 97 / POST 78 / PUT 3)
  * Claude API 플레이그라운드 탭 7 → **10**
  * **신규 행**: "공식 문서 색인 — 33 페이지"
- README ko/en/zh 3종 동등 반영

## [2.14.0] — 2026-04-23

### 🧪 Agent SDK 스캐폴드 — 신규 탭 `agentSdkScaffold`

`claude-agent-sdk` 기반 Python / TypeScript 프로젝트 뼈대를 UI 에서 생성 + Terminal 새 창에 초기화 명령 자동 붙여넣기.

**언어 · 도구**
- **Python** — `uv` (대체 제안: `brew install uv`)
- **TypeScript** — `bun` (대체 제안: `curl -fsSL https://bun.sh/install | bash`)

**템플릿 3종**
- `basic` — Messages API 1회 호출 + 응답 출력
- `tool-use` — tool 정의 + `tool_use → tool_result` 라운드 트립 (가짜 weather)
- `memory` — 대화 히스토리 JSON 저장

**생성 결과**
- `<path>/<name>/main.py` (py) 또는 `index.ts` (ts)
- `pyproject.toml` / `package.json` — uv sync / bun install 시 실제 의존성 설치
- `README.md` · `.gitignore`
- AppleScript 로 Terminal 새 창 열림 + `cd <path>/<name> && uv sync` (또는 `bun install`) 명령 **붙여넣기** (Enter 는 사용자가 누름)

**안전 장치**
- `name` 은 `[a-zA-Z][a-zA-Z0-9_-]{1,63}` 만 (path traversal 방지)
- `path` 는 `$HOME` 내부만
- `<path>/<name>` 이 이미 있으면 거부
- `uv`/`bun` 없으면 친절한 설치 힌트 포함 에러 (자동 설치 금지)

**Architecture**
- `server/agent_sdk_scaffold.py` 신설 — `api_scaffold_{catalog,create}` + 템플릿 본문 inline (python / ts × 3종)
- `server/routes.py` 2 라우트 (GET catalog · POST create)
- `server/nav_catalog.py` `agentSdkScaffold` 탭 (work 그룹) + en/zh
- `dist/index.html` NAV (icon 🧪) + `VIEWS.agentSdkScaffold` + `scCreate/scSet/scReset/openFolderFromPath`
- `tools/translations_manual_9.py` 25 키 × ko/en/zh

**한계**
- macOS 전용 (AppleScript Terminal). Linux/Windows 는 생성만 되고 Terminal 스폰은 실패 — 결과 카드에 `next command` 를 복사할 수 있도록 노출.

## [2.13.0] — 2026-04-23

### 📑 Citations 플레이그라운드 — 신규 탭 `citationsLab`

Anthropic Messages API 의 `citations.enabled` 응답 모드 실습. 문서를 `content` 의 document 블록으로 제공 + `citations: {enabled: true}` 를 세팅하면 답변 text block 에 `citations: [{cited_text, start_char_index, end_char_index, ...}]` 배열이 포함된다.

**기능**
- 예시 2종: 회사 소개문 / 기술 아티클
- 모델(Opus/Sonnet), 문서 제목(선택), 문서 본문 textarea, 질문 입력
- 답변 렌더링: 각 citation 을 `[N]` 번호 pill 로 본문 뒤에 inline 추가
- `[N]` hover → 원문 패널에서 해당 `start/end_char_index` 구간을 `<mark>` 로 하이라이트
- 히스토리 최근 20건 (`~/.claude-dashboard-citations-lab.json`)

**Architecture**
- `server/citations_lab.py` 신설 — `api_citations_{test,examples,history}` · examples 2 · text-type document 블록 구성
- `server/routes.py` 3 라우트 (GET examples/history · POST test)
- `server/nav_catalog.py` `citationsLab` 탭 (work 그룹) + en/zh desc
- `dist/index.html` NAV (icon 📑) + `VIEWS.citationsLab` · `ciHoverCit` · `ciLoadExample` · `ciRun` · `ciReset` · `ciSet`
- `tools/translations_manual_9.py` 17 키 × ko/en/zh

**한계 / 후속**
- 현재는 **text source** 만 지원. PDF / base64 document 는 T+N 에서 확장 예정.
- `page_location` citation 타입은 PDF 입력에서만 나타나므로 현 UI 는 `char_location` 중심.

## [2.12.0] — 2026-04-23

### 📖 Claude Docs Hub — 신규 탭 `claudeDocs` (new 그룹)

docs.anthropic.com 의 주요 페이지를 대시보드 안에서 카테고리별 카드로 색인 + 검색.

**카테고리 5**
- **Claude Code** — Overview / Sub-agents / Skills / Hooks / MCP / Plugins / Output Styles / Status Line / Slash Commands / Memory / Interactive / IAM / Settings / Troubleshooting (14)
- **Claude API** — Messages / Prompt Caching / Extended Thinking / Tool Use / Message Batches / Files / Vision / Citations / Web Search Tool / Code Execution Tool / Embeddings (11)
- **Agent SDK** — Overview / Python / TypeScript (3)
- **Models** — Models / Deprecations / Pricing (3)
- **Account & Policy** — Team / Glossary (2)

총 **33개 공식 페이지** 카드.

**기능**
- 제목/요약/URL 필터 (300ms debounce)
- 각 카드 2 버튼: `🔗 외부 열기` · `→ 관련 탭` (해당하는 대시보드 탭 id 가 있으면 `go(...)` 호출)
- 결과 없으면 친절한 empty state

**Architecture**
- `server/claude_docs.py` 신설 — 정적 `CATALOG` dict + `api_claude_docs_{list,search}`
- `server/routes.py` 2 라우트 (GET list/search)
- `server/nav_catalog.py` `claudeDocs` 탭 등록 (`new` 그룹) + en/zh
- `dist/index.html` NAV (icon 📖) + `VIEWS.claudeDocs` · `cdSet` · `cdRender` (debounce)
- `tools/translations_manual_9.py` 7 키 × ko/en/zh

**주의**
- URL 은 2026-04 시점 기준 추정. Anthropic 이 경로를 바꾸면 `CATALOG` 만 갱신하면 됨.

## [2.11.0] — 2026-04-23

### 🧰 Claude 공식 내장 Tools 플레이그라운드 — 신규 탭 `serverTools`

Anthropic 서버가 **직접 실행하는 hosted tool** 실습 탭. 기존 `toolUseLab` 이 사용자가 tool_result 를 수동 공급하는 구조라면, 이건 Anthropic 이 tool 을 실행하고 결과를 포함한 응답을 돌려준다.

**지원 도구**
- 🌐 **web_search** (`web_search_20250305`, beta `web-search-2025-03-05`) — 웹 검색 + citation
- 🧪 **code_execution** (`code_execution_20250522`, beta `code-execution-2025-05-22`) — Python sandbox (stdout / stderr / return_code)

**기능**
- 도구 체크박스 (model supportedModels 가드 — Haiku 비활성)
- 모델 선택 (Opus / Sonnet) + max_tokens
- 예시 3종 (뉴스 검색 / Python 계산 / 검색+분석 결합)
- 응답 content 블록 분류 시각화:
  * `server_tool_use` — 보라 카드 (tool 입력 JSON)
  * `*_tool_result` — 초록 카드 (실행 결과)
  * `text` — 최종 응답
- 히스토리 최근 20건 (`~/.claude-dashboard-server-tools.json`)

**Architecture**
- `server/server_tools.py` 신설 — `api_server_tools_{catalog,history,run}` + `TOOL_CATALOG` (beta 헤더 중앙화) + `EXAMPLES` 3종
- `server/routes.py` 3 라우트 추가 (GET catalog/history · POST run)
- `server/nav_catalog.py` `serverTools` 탭 등록 + en/zh desc
- `dist/index.html` NAV (icon 🧰) + `VIEWS.serverTools` + `stRun/stToggleTool/stLoadExample/stReset/stSet`
- `tools/translations_manual_9.py` 17 키 × ko/en/zh

**주의**
- beta header 스펙은 2026-04 시점 추정. Anthropic 에서 바뀌면 `TOOL_CATALOG[*].beta` 만 갱신.
- `web_search` / `code_execution` 호출은 별도 과금.

## [2.10.4] — 2026-04-23

### Fixed — v2.10.3 스모크 테스트 실행으로 드러난 2건

**1. `VIEWS.team` — `TypeError: t is not a function`**
team 탭 진입 시 `VIEWS.team` 이 로컬 변수 `const [t, auth] = ...` 로 전역 `t(key)` i18n 함수를 **섀도잉** → 이후 `${t('내 계정')}` 같은 모든 i18n 호출이 TypeError 로 실패.

- `VIEWS.team` 의 로컬 변수 `t` → **`team`** 으로 rename
- 본문 11개 참조 지점 (`t.displayName`, `t.organizationUuid`, `t.note` 등) 모두 갱신
- 주석으로 "전역 `t` 섀도잉 금지" 명기

이 버그는 사용자가 team 탭을 열었다면 즉시 드러났을 텐데, 수동으로 접속할 일이 적어 회귀로 남아 있었음. **E2E smoke 가 없었다면 찾기 어려웠을 회귀.**

**2. `scripts/e2e-tabs-smoke.mjs` — 오탐 가능 구조**
`document.querySelector('main')?.innerText` 에 "뷰 렌더 실패" / "View render failed" 문자열이 있는지 단순 포함 검사 → `memory` 탭에 메모리 노트 내용(ex. `feedback_escape_html_helper.md`)의 문자열이 포함되어 **정상 렌더를 실패로 오탐**.

- 검사 조건을 `#view .card.p-8.empty` element 존재 여부로 **엄격화**. `renderView()` catch 블록이 렌더하는 에러 카드만 검출 → 본문 텍스트 충돌 제거.
- 네비게이션을 `window.state.view = ...` → `location.hash = '#/<tab>'` (go() 와 동일 경로) 로 변경. 이전엔 전역 `state` 변수가 `window` 에 노출 안 돼 **실제 뷰 전환이 안 된 채 45 탭이 전부 통과** 하는 false-positive 가 있었음 → 이번 smoke 로 최초 true positive 확인.

**3. `package.json` — `"type": "module"` 제거**
v2.10.3 에서 추가했던 `"type": "module"` 이 기존 CommonJS 스크립트 `scripts/verify-translations.js` (`require` 사용) 를 깨뜨림. `.mjs` 파일은 명시 확장자로 ESM 처리되므로 `"type"` 필드 없이도 충분. 제거.

**결과**
- `HEADLESS=1 npm run test:e2e:smoke` → 45/45 탭 **실제 전수 통과**
- `npm run verify:i18n` → 3,096 키 × 3언어 · 0 누락

## [2.10.3] — 2026-04-23

### 🎭 Playwright E2E 스모크 스크립트

자동화 테스트로 회귀 방지. 모든 스크립트는 **라이브 서버(127.0.0.1:8080)** 를 대상으로 동작.

**scripts/e2e-tabs-smoke.mjs** (45 탭 전수 검사)
- `server/nav_catalog.py::TAB_CATALOG` 를 정적 파싱해 탭 id 목록 추출
- 각 탭으로 `window.state.view` 전환 + `renderView()` 호출 후
  - "뷰 렌더 실패" / "View render failed" 텍스트 검출 시 실패
  - `console.error` 발생 시 실패
- 단일 탭 검사: `TAB_ID=workflows npm run test:e2e:smoke`

**scripts/e2e-workflow.mjs** (빌트인 템플릿 실행 E2E)
- `bt-multi-ai-compare` 템플릿 조회 → `POST /api/workflows/save` 로 E2E 워크플로우 생성 → `POST /api/workflows/run`
- 5초간 `run-status` 폴링 + `#wfRunBanner.visible` 등장 여부 체크
- 완료 후 `POST /api/workflows/delete` 로 자동 정리
- critical error (`is not defined`, `View render failed`, `뷰 렌더 실패`) 발견 시 실패

**package.json**
- `scripts.test:e2e:smoke` / `test:e2e:workflow` / `test:e2e:headed` / `verify:i18n`
- `name`, `type:"module"`, `private:true` 추가 (ESM 스크립트 지원)

**.gitignore**
- `test-results/`, `playwright-report/`, `playwright/.cache/`, `node_modules/`

**README 3종**: `🎭 E2E 테스트` 섹션 (Troubleshooting 과 Contributing 사이) — `npx playwright install chromium` 안내 + 스크립트 사용법.

**주의**
- 최초 실행 전 `npx playwright install chromium` 필요 (약 150MB).
- 서버가 기동 중이 아니면 timeout 후 실패 — 테스트 실행 전 수동 기동.

## [2.10.2] — 2026-04-23

### 💬 노드 hover 결과 tooltip

실행 이력이 있는 노드에 마우스 hover 시 결과 미리보기 tooltip.

**내용**
- 상태 아이콘(✅/❌/⏳/⏭️) + 노드 제목 + 상태 라벨
- 소요 시간 (running 노드는 startedAt 기반 실시간, ok/err 는 durationMs)
- 제공자 · 모델 (있으면)
- 입력/출력 토큰 (있으면)
- 출력 미리보기 (앞 160자) 또는 에러 메시지 (앞 260자)

**UX**
- 280ms debounce → 손을 살짝 stop 시에만 노출, 지나갈 때는 안 뜸
- 마우스 이동 시 위치 따라감 (화면 경계 감지)
- 노드에서 벗어나면 즉시 숨김 (단 related target 이 다른 노드면 유지)
- 실행 이력 없는 노드는 표시 안 함 (노이즈 최소화)
- 상태별 left border 색 (ok 초록 / err 빨강 / running 보라 / skipped 회색)

**Architecture**
- `dist/index.html`:
  * CSS: `#wfNodeTooltip` + 상태별 variant
  * JS: `_wfShowNodeTooltip(nid, evt)` · `_wfHideNodeTooltip()` · delegation IIFE (mouseover/mousemove/mouseout)
- `tools/translations_manual_9.py`: 3 키 × ko/en/zh (건너뜀 / 제공자 / 토큰)

## [2.10.1] — 2026-04-23

### 🪟 노드 편집 모달 — 카테고리 그리드 접기

사용자 피드백 스크린샷: 노드 편집 모달 하단의 제목/모델/subject 등 필드가 항상 스크롤해야만 보임.

**원인**: `_wfRenderEditorBody` 가 타입 선택 여부와 무관하게 16개 노드 타입 그리드를 3열 × 4~6행으로 **항상 펼쳐서** 표시 → 720px 모달에서 약 160~200px(25~30%) 를 카테고리가 점유.

**수정**
- **기존 노드 편집** (type 이미 세팅): 기본 **접힘** — `[아이콘] [타입 라벨] 칩 · ▸ 타입 변경` 한 줄(≈48px)만 표시. 폼 영역에 +110~150px 추가 확보.
- **신규 노드 추가** (type 없음): 기본 **펼침** (기존 UX 유지).
- **타입 선택 직후 자동 접힘** + 첫 입력 필드(제목/subject 등) autofocus.
- **토글 버튼** `▾ 접기` / `▸ 타입 변경` (tooltip: `Alt+C`).
- **단축키** `Alt+C` — 워크플로우 탭에서 노드 편집 창이 열려 있을 때 토글.
- **localStorage 기억** (`wfEditorCatExpanded`): 사용자 취향 영속.

**Architecture**
- `dist/index.html`:
  * `_wfCatIsExpanded(draft)` · `_wfToggleCat(winId)` 신규
  * `_wfRenderEditorBody` 가 expanded 분기로 재구성 (접힘 시 칩 + 변경 버튼)
  * `_wfPickNodeType` 종료 후 localStorage 접힘 + first-field autofocus
  * 워크플로우 키보드 핸들러에 `Alt+C` 토글 분기 추가
- `tools/translations_manual_9.py`: 4 키 × ko/en/zh (타입 / 타입 변경 / 접기 / 펼치기)

## [2.10.0] — 2026-04-23

### 🔦 워크플로우 실행 가시성 강화

사용자 피드백: "**워크플로우가 지금 어느 노드에서 실행 중인지 보기 어렵다**".

기존 `data-status` CSS 는 작동했지만 시각적 강조가 약했고, 큰 캔버스에서 running 노드가 화면 밖이면 전혀 알 수 없었음.

**상단 플로팅 실행 배너 (신규)**
- `#wfRunBanner` — 캔버스 상단 중앙 고정
- 포맷: `⏳ [노드명] · {완료}/{전체} · {경과초}s · 진행률 바 · 📍 위치로 이동`
- 상태별 색: running (보라 · pulse) / ok (초록) / err (빨강)
- 완료·실패 3.5초 후 자동 페이드아웃
- 수동 닫기 버튼

**Running 노드 시각 강화**
- 외곽 점선 링 (`.wf-node-ring`, stroke-dasharray 6 6) + 회전 애니메이션 (`@keyframes wfSpinDash`, 2.5s linear)
- `drop-shadow` 보라 글로우 추가
- 라벨 옆 `⏱ {초}s` 실시간 카운터 (`.wf-node-elapsed`)

**미니맵 상태 색 반영**
- running/ok/err/skipped 색을 node dot 에 우선 적용
- running 노드는 dot 크기 3px → 5px 로 강조

**서버 SSE 폴링 1.0s → 0.5s**
- `handle_workflow_run_stream`: `time.sleep(0.5)` + `max_polls = 3600` (30분 유지)
- 서버 노드 실행 시작 시 `nodeResults[nid].startedAt` 기록 → 프론트 elapsed 계산

**위치로 이동 (`_wfFocusNode`)**
- 배너의 📍 버튼 또는 직접 호출로 해당 노드를 뷰포트 중앙에 pan (zoom 유지)

**i18n** — 6 키 × ko/en/zh (실행 중 / 대기 중 / 완료 / 실패 / 위치로 이동 / 닫기). 총 **3,092 키** · 누락 0.

**Architecture**
- `server/workflows.py`: `handle_workflow_run_stream` sleep 0.5s, `_run_one_iteration` running 상태에 `startedAt` 포함
- `dist/index.html`:
  * CSS: `#wfRunBanner` 스타일, `.wf-node-ring` / `.wf-node-elapsed` 추가, `wfSpinDash` keyframe
  * JS: `_wfApplyRunStatus` 확장 (배너/미니맵 호출), `_wfRenderRunBanner`, `_wfHideRunBanner`, `_wfFocusNode` 신규
  * `_wfRenderNode` SVG 템플릿에 `<rect class="wf-node-ring">` + `<text class="wf-node-elapsed">` 삽입
  * `_wfRenderMinimap` node dot 에 실행 상태 색 우선 적용
- `tools/translations_manual_9.py`: 6 키 ko/en/zh
- `dist/locales/{ko,en,zh}.json`: 3,092 키 재빌드

## [2.9.3] — 2026-04-23

### Fixed — 빌트인 워크플로우 템플릿 조회 실패 (404 → "템플릿 생성 에러")

사용자 리포트: **"멀티 AI 비교 커스텀 템플릿을 사용하려는데 error 라고 나오면서 안 생성돼"**.

**원인**
`server/routes.py::_ITEM_GET_ROUTES` 의 템플릿 단일 조회 정규식이 `(tpl-[0-9]{10,14}-[a-z0-9]{3,6})` 로 **커스텀 템플릿 id 포맷만 허용**하고 있었다. `workflows.py::BUILTIN_TEMPLATES` 의 id 는 `bt-multi-ai-compare / bt-rag-pipeline / bt-code-review / bt-data-etl / bt-retry-robust` 5종으로 전혀 다른 포맷이라 매칭 실패 → `GET /api/workflows/templates/bt-multi-ai-compare` 가 계속 **404**. 프론트의 템플릿 상세 fetch 가 실패해 워크플로우 생성이 중단됨.

`api_workflow_template_get` 핸들러 자체는 이미 `BUILTIN_TEMPLATES` 먼저 조회 후 fallback 으로 custom 저장소를 뒤지는 올바른 구조였음 — 라우트 레이어에서 도달조차 못 하던 문제.

**수정**
- `server/routes.py` 정규식을 `(tpl-[0-9]{10,14}-[a-z0-9]{3,6}|bt-[a-z0-9-]+)` 로 확장해 두 id 포맷 모두 허용.

**검증**
5개 빌트인 템플릿 전수 스모크:
- `bt-multi-ai-compare` (멀티 AI 비교, 6 nodes) ✓
- `bt-rag-pipeline` (RAG 파이프라인, 5 nodes) ✓
- `bt-code-review` (코드 리뷰, 5 nodes) ✓
- `bt-data-etl` (데이터 ETL, 5 nodes) ✓
- `bt-retry-robust` (재시도, 5 nodes) ✓

모두 `ok: True`, 정확한 노드 수 반환.

## [2.9.2] — 2026-04-23

### Docs — README 3종 통계/탭 테이블 전면 갱신

v2.3.0 ~ v2.9.1 누적 결과를 README 의 본문 섹션에 반영 (그간 상단 배너만 추가하고 본문 통계가 v2.1.1 로 남아있었음).

- 버전 배지 **v2.9.0 → v2.9.1**
- ASCII 미리보기 표기 "6 그룹 38 탭" → **"6 그룹 45 탭"**
- "Why" 비교 표 셀 "38 탭" → **"45 탭"**
- `🤝 Claude Code Integration` 탭 테이블의 work 그룹에 신규 7 탭(`promptCache` `thinkingLab` `toolUseLab` `batchJobs` `apiFiles` `visionLab` `modelBench`) 🆕 표시로 추가 + "Claude API 플레이그라운드" 하이라이트 줄 추가
- Architecture 트리: `routes.py` 143 → **168 라우트**, `nav_catalog.py` 38 → **45 탭**, `locales` 2,932 → **3,090 키**
- `🔢 Stats (v2.1.1)` 섹션 전체를 **`v2.9.1`** 기준으로 갱신:
  - 백엔드 14,067줄/20 모듈 → **~16,000줄/27 모듈**
  - 프론트 ~13,500줄 → **~15,500줄**
  - API 라우트 143 → **168 (GET 90 / POST 75 / PUT 3)**
  - 탭 38 → **45**
  - i18n 키 2,932 → **3,090**
  - 신규 행: "Claude API 플레이그라운드 탭 — 7"
- README.md / README.ko.md / README.zh.md 3종 동등 구조로 반영.

## [2.9.1] — 2026-04-23

### Fixed — v2.3.0~v2.9.0 신규 탭 렌더 실패 + NAV desc 번역 누락

**`_escapeHTML is not defined` 런타임 에러 해소**
- v2.3.0~v2.9.0 에서 추가한 7개 VIEWS (`promptCache`, `thinkingLab`, `toolUseLab`, `batchJobs`, `apiFiles`, `visionLab`, `modelBench`) 가 **존재하지 않는 `_escapeHTML()`** 을 참조해 탭 진입 즉시 "View render failed" 에러가 나던 문제.
- 저장소 실제 헬퍼 이름은 **`escapeHtml`** (소문자 HTML 중 H 만 대문자).
- `dist/index.html` 에서 `_escapeHTML(` → `escapeHtml(` 21곳 일괄 치환.

**i18n 14건 누락 번역 보강**
- NAV `desc` 7개 (work 그룹 신규 탭들) — `escapeHtml(t(n.desc))` 경로에 번역이 없어 한국어 원문이 영/중문 모드에서도 그대로 노출되던 문제.
- `confirmModal` 메시지 템플릿 (`총 {n} 건을 ...`, `회 API 호출을 수행합니다 (...`) 의 한글 조각들을 extractor 가 잘못 뽑아 missing 이던 7건.
- `tools/translations_manual_9.py::NEW_EN` / `NEW_ZH` 에 14 키 × 2언어 추가.
- 결과: `build_locales.py` **Missing EN/ZH 0** · `verify-translations.js` 전체 통과 (3,090 키 × 3언어).

## [2.9.0] — 2026-04-23

### 🏁 Model Benchmark — 신규 탭 (work 그룹)

사전 정의 프롬프트 셋 × 선택한 모델들을 교차 실행해 성능·비용을 집계한다.

**기능**
- 프롬프트 셋 3종: 기본 Q&A(5) / 코드 생성(3) / 추론·수학(3)
- 모델 3개 체크박스 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5)
- 실행 전 confirmModal 로 총 호출 수 · 비용 발생 경고
- ThreadPoolExecutor(max_workers=4) 로 prompt × model 조합 병렬 실행
- 모델별 집계 표: 성공 건수 · 평균 지연 · 평균 출력 토큰 · 총 비용(USD)
- 개별 응답 매트릭스 (모델 · 프롬프트 · 응답 미리보기 · 지연 · 비용)
- JSON 다운로드 버튼

**Architecture**
- `server/model_bench.py` 신설 — `api_model_bench_{sets,run}` + `_call_once` + `_PRICING` 테이블
- `server/routes.py` — 2개 라우트 추가
- `server/nav_catalog.py` — `modelBench` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.modelBench`
- `tools/translations_manual_9.py` — 28 키 × ko/en/zh

### 📜 v2.3 ~ v2.9 로드맵 완료

2026-04-23 연속 릴리스로 **Claude API 플레이그라운드 7 탭**을 work 그룹에 추가: `promptCache`(v2.3.0) · `thinkingLab`(v2.4.0) · `toolUseLab`(v2.5.0) · `batchJobs`(v2.6.0) · `apiFiles`(v2.7.0) · `visionLab`(v2.8.0) · `modelBench`(v2.9.0). 원격 v2.2.1 위에 rebase 된 결과 버전 번호를 한 칸 shift 했다.

---

## [2.8.0] — 2026-04-23

### 👁️ Vision / PDF Lab — 신규 탭 (work 그룹)

이미지(PNG/JPG/WebP/GIF) 또는 PDF 를 업로드해 Opus / Sonnet / Haiku 3 모델에 병렬 질의 → 응답 비교.

**기능**
- 파일 선택 → 자동 base64 인코딩 (최대 10MB)
- 이미지: `type:"image"` 블록, PDF: `type:"document"` 블록으로 content 구성
- 3 모델을 **ThreadPoolExecutor** 로 병렬 호출
- 각 모델별 응답/지연/토큰 사용량 카드 나란히 표시
- 총 소요 시간 + 모델 수 요약

**Architecture**
- `server/vision_lab.py` 신설 · `server/routes.py` 라우트 2개 · NAV + `VIEWS.visionLab` · 16 i18n 키 × 3언어

---

## [2.7.0] — 2026-04-23

### 📎 Files API — 신규 탭 (work 그룹)

Anthropic Files API 업로드/목록/삭제 + 메시지 document reference 를 UI 에서 다룬다.

**기능**
- 브라우저 파일 선택 → base64 전송 → 서버 multipart/form-data → Anthropic 업로드 (최대 30MB)
- 업로드된 파일 목록 (filename · size · mime · id)
- 파일 선택 → 모델 선택 → 질문 → `{type:"document", source:{type:"file", file_id}}` 블록으로 질의
- 개별 삭제 + 삭제 전 확인 모달

**Architecture**
- `server/api_files.py` 신설 · stdlib multipart POST 유틸 · 라우트 4개 (GET list · POST upload/delete/test)
- beta header: `anthropic-beta: files-api-2025-04-14`
- i18n 22 키 × 3언어

---

## [2.6.0] — 2026-04-23

### 📦 Batch Jobs — 신규 탭 (work 그룹)

Anthropic Message Batches API 로 대용량 프롬프트 병렬 제출·상태 폴링·JSONL 결과 다운로드.

**기능**
- 원클릭 예시 2종: Q&A 10건 / 요약 5건
- 모델 + max_tokens 조절 · 프롬프트 한 줄당 1건 (최대 1000건)
- 제출 전 **비용 발생 경고** 모달 (confirmModal)
- 최근 배치 목록 + 상태 + request_counts · JSONL 결과 프리뷰
- 진행 중 배치 취소 지원

**Architecture**
- `server/batch_jobs.py` 신설 · 라우트 6개 (GET examples/list/get/results · POST create/cancel)
- beta header: `anthropic-beta: message-batches-2024-09-24`
- i18n 30 키 × 3언어

---

## [2.5.0] — 2026-04-23

### 🛠️ Tool Use Playground — 신규 탭 (work 그룹)

Anthropic Tool Use 의 라운드 트립(user → tool_use → tool_result → next turn)을 수동으로 연습.

**기능**
- 기본 도구 템플릿 3종 원클릭: `get_weather` / `calculator` / `web_search` (mock)
- tools JSON 배열 직접 편집
- 대화 버블 (role · text · tool_use · tool_result 구분 색)
- tool_use 수신 시 인라인 tool_result 입력 폼 → 제출 → 다음 턴 자동 호출
- "새 대화" 버튼으로 messages 초기화

**Architecture**
- `server/tool_use_lab.py` 신설 · 라우트 3개 · i18n 13 키 × 3언어
- 히스토리 `~/.claude-dashboard-tool-use-lab.json`

---

## [2.4.0] — 2026-04-23

### 🧠 Extended Thinking Lab — 신규 탭 (work 그룹)

Claude Opus 4.7 / Sonnet 4.6 의 Extended Thinking 을 실험하고 thinking block 을 분리 시각화.

**기능**
- 원클릭 예시 3종: 수학 추론 / 코드 디버깅 / 설계 플래닝
- `budget_tokens` 슬라이더 (1024 ~ 32000, 512 단위)
- thinking block 과 최종 응답을 **접기/펴기** 로 분리 표시
- Haiku 선택 시 비지원 경고
- 히스토리 최근 20건

**Architecture**
- `server/thinking_lab.py` 신설 · 라우트 4개 (GET examples/history/models · POST test)
- i18n 16 키 × 3언어

---

## [2.3.0] — 2026-04-23

### 🧊 Prompt Cache Lab — 신규 탭 (work 그룹)

Anthropic Messages API 의 `cache_control` 을 실험/관측하는 전용 플레이그라운드.

**기능**
- 원클릭 예시 3종: 시스템 프롬프트 캐시 / 대용량 문서 캐시 / 도구 정의 캐시
- 모델 선택 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) + max_tokens 조절
- system / tools / messages JSON 편집기
- 응답 즉시: input / output / cache_creation / cache_read 토큰 + USD 비용 + 캐시 절감 추정
- 히스토리 최근 20건 (`~/.claude-dashboard-prompt-cache.json`)

**Architecture**
- `server/prompt_cache.py` 신설 (297줄) — `api_prompt_cache_test/history/examples` + `_estimate_cost` (3 모델 가격 테이블)
- `server/routes.py` — 라우트 3개 (GET examples/history · POST test)
- `server/nav_catalog.py` — `promptCache` 탭 등록 + en/zh desc
- `dist/index.html` — NAV + `VIEWS.promptCache`
- `tools/translations_manual_9.py` — 35 키 × ko/en/zh


## [2.2.1] — 2026-04-22

### Fixed — 타이틀 리터럴 노출 + 위자드 테스트 오류

- **`ai_providers_title`/`ai_providers_subtitle` 리터럴 노출 수정** — 기존 `t(ko)` 함수가 1-인자만 받아 `t('ai_providers_title','AI 프로바이더')` 호출 시 fallback 을 무시하고 키 그대로 반환하던 문제. `t(key, fallback)` 2-인자 시그니처로 확장. ko 모드에서 구조화 키(영문 only) 가 오면 fallback 우선 사용.
- **`api_auth_login` NameError 수정** — `server/auth.py:170` 에서 `platform.system()` 호출하면서 `import platform` 이 누락돼 `/api/auth/login` 이 항상 500 을 반환하던 문제.
- **위자드 연결 테스트 UX 개선** — 테스트 결과에 응답 프리뷰(앞 80자) 표시, 404/unknown route 오류 시 "대시보드 서버를 재시작하면 최신 기능이 적용됩니다" 힌트 추가. 신규 라우트가 반영되지 않은 스테일 서버 상태를 사용자가 즉시 인지 가능.
- i18n: 신규 1개 키(ko/en/zh). 총 2,950 키 유지 (audit items 1806→1807).

## [2.2.0] — 2026-04-22

### 🎯 v2.2 — 프로바이더 탭 3종 개선

**프로바이더 CLI 감지 견고화**
- `server/ai_providers.py` 에 `_which()` 헬퍼 신설 — `shutil.which` PATH 탐지 실패 시 `/opt/homebrew/bin`·`~/.local/bin`·nvm/asdf node 버전 디렉터리 등 **11개 fallback 경로** 전수 검색. LaunchAgent·GUI 런치 등 PATH 가 좁혀진 환경에서도 Claude/Codex/Gemini/Ollama CLI 를 정확히 감지.
- `ClaudeCliProvider._bin`, `OllamaProvider._bin`, `GeminiCliProvider._bin`, `CodexCliProvider._bin`, `CustomCLIProvider._bin`, 임베딩 실행 경로 모두 `_which()` 로 교체.

**CLI 설치·로그인 원클릭 (신규)**
- 신규 모듈 `server/cli_tools.py` — 4종 CLI 설치·상태·로그인 통합 관리.
  - `GET /api/cli/status` — 4종(claude/codex/gemini/ollama) 설치 여부·버전·경로 + brew/npm 가용성 반환
  - `POST /api/cli/install` — brew 우선 → npm → 설치 스크립트 자동 선택, AppleScript 로 Terminal 열어 **대화형 설치 수행**
  - `POST /api/cli/login` — `claude auth login` / `codex login` / `gemini` 최초 실행 등을 터미널에서 실행
- 설치 방법 카탈로그: `brew install --cask claude-code` · `npm install -g @openai/codex` · `npm install -g @google/gemini-cli` · `curl ... ollama.com/install.sh`
- AI 프로바이더 탭의 CLI 카드에 상태 배지 추가:
  - 미설치 → `⬇️ 설치 (Homebrew|npm)` 버튼 · 클릭 시 터미널 열림, 10초마다 설치 감지 폴링(최대 5분)
  - 설치 완료 → `✅ 설치 완료 · <버전>` + `🔐 로그인` 버튼

**UI 간소화**
- AI 프로바이더 탭 하단 "💡 워크플로우 & 프로바이더 사용 가이드" 섹션 전체 제거(~50줄 삭제) — 별도 탭의 튜토리얼·노드 카탈로그와 중복.

**i18n**
- `translations_manual_9.py` 에 CLI 설치/로그인 문구 14개 키 등록(EN/ZH). ko/en/zh 각 **2,950 키** · 누락 0 · 한글 잔존 0.

## [2.1.4] — 2026-04-22

### Fixed — 설정 드롭다운 테마 3종 번역 누락
- `Midnight`/`Forest`/`Sunset` 테마 라벨이 하드코딩 영문으로 박혀 있어 ko/zh 선택 시에도 번역되지 않던 문제 수정.
- `dist/index.html` 설정 드롭다운 3개 버튼에 `data-i18n="settings.midnight|forest|sunset"` 속성 추가 (KO 기본값: 미드나잇/포레스트/선셋).
- `tools/translations_manual.py::MANUAL_KO` + `tools/translations_manual_9.py::NEW_EN/NEW_ZH` 에 구조화 키 + 한글-텍스트 키(`미드나잇 → Midnight/午夜`) 동시 등록 → `data-i18n` 경로와 text-node 스캐너 경로 양쪽 대응.
- 결과: ko/en/zh 각 **2,936 키** · 누락 0 · 한글 잔존 0 (기존 2,932 → +4).

## [2.1.3] — 2026-04-22

### Fixed — 워크플로우 탭 UX 정리
- **우측 하단 빈 박스 제거** — 워크플로우 미선택·빈 워크플로우 상태에서 `#wfMinimap` canvas 컨테이너(회색 박스)가 보이던 문제 수정. 기본 `display:none` + `_wfRenderMinimap()` 이 nodes 존재 시에만 표시하도록 변경.
- **캔버스 높이 캡 해제** — `#wfRoot` 의 `height: min(calc(100vh - 160px), 680px)` 캡을 제거하고 `calc(100vh - 230px)` 로 변경. 큰 모니터에서 680px 에 갇혀 스크롤해야 보이던 문제 해소 → 전체 워크플로우가 한눈에 보임.

## [2.1.2] — 2026-04-22

### Docs — 퍼블릭 배포용 README 3종 전면 재작성 + LICENSE 추가
- `README.md` / `README.ko.md` / `README.zh.md` 를 v2.1.1 통계 기준으로 동등 구조(305줄)로 재작성.
- 신규 섹션: Why(전/후 비교 표) · Use Cases(5 시나리오) · Troubleshooting 표 · Quick Start 30초 · Data Stores 표 · Tech Stack · Contributing 7단계.
- 통계 갱신: API 라우트 138 → **143**, i18n 2,893 → **2,932**, 서브에이전트 16 역할 프리셋·38 탭·18 튜토리얼·Rate Limiter 등 v2.1.x 신규 지표 반영.
- 배지 추가: Python 3.10+ · License · Version · Zero Dependencies.
- `LICENSE` 파일 신규 (MIT) — README 의 `./LICENSE` 링크가 404 였던 문제 수정.

## [2.1.1] — 2026-04-22

### Fixed — i18n 잔존 39건 전수 해소
- v2.1.0 신규 기능(HTTP/transform/variable/subworkflow/embedding/loop/retry/error_handler/merge/delay 노드 설명, AI 프로바이더 UI, Modelfile 편집 등)에서 누락됐던 **UI 문구 39개** 를 `translations_manual_9.py::NEW_EN`/`NEW_ZH` 에 등록.
- `tools/translations_manual.py` 에 `_EXTRACTOR_NOISE_OVERRIDES` 추가 — `const _KO_RE = /[가-힣]/` 같이 기존 MANUAL_EN 에 한글 원문으로 고정돼 있던 JS 리터럴을 유니코드 이스케이프(`가-힣`)로 override.
- 결과: **ko/en/zh 각 2,932 키 · 누락 0 · 영문/중문 한글 잔존 0** (origin 대비 값 회귀 0건).

## [2.1.0] — 2026-04-22

### 🎯 v2.1 — 미구현 23개 항목 전면 완료

**백엔드**
- 📌 **변수 스코프 시스템** — variable 노드에 글로벌/로컬 스코프 + `{{변수명}}` 템플릿 치환
- 🔀 **조건부 실행 11종** — contains/equals/not_equals/greater/less/regex/length_gt/length_lt/is_empty/not_empty/expression(AND/OR)
- ⏱️ **Rate Limiter** — 프로바이더별 토큰 버킷 알고리즘 (분당 요청 제한)
- 📝 **Ollama Modelfile 생성** — `POST /api/ollama/create` (커스텀 모델 생성)
- ✅ **에러 메시지 err() 전환 100%** — 모든 한글 에러에 error_key
- 🌍 **nav_catalog 다국어** — 38개 탭 설명 en/zh 동적 전환 구조 (`TAB_DESC_I18N`)

**프론트엔드 UX**
- 📱 **모바일 반응형** — 사이드바 접기, 그리드 반응형, 모달 전체 화면
- ♿ **접근성** — ARIA 레이블, role="dialog", 포커스 트랩
- 🔔 **브라우저 Notification** — 워크플로우 완료/실패, 사용량 초과 알림
- 🎨 **커스텀 테마 5종** — dark/light/midnight/forest/sunset
- 🔀 **조건부 실행 UI** — conditionType 11종 셀렉트
- 📌 **변수 스코프 UI** — scope 선택 + {{변수명}} 참조 안내
- 📝 **Modelfile 편집 UI** — 커스텀 모델 생성 모달
- 📊 **비용 히스토리 상세 차트** — 프로바이더별 일별 스택 차트
- 📦 **노드 그룹핑** — Shift+클릭 다중 선택 → 그룹 생성/접기/펴기
- 🔍 **워크플로우 diff** — 버전 비교 (추가/삭제/변경 노드 표시)

**i18n**
- +36개 키 사전 추가 (UX 신기능) + 전수 검증 0 miss
- 2,711+ 키 × 3언어

### Architecture
- `server/ai_providers.py` — `_RateLimiter` 토큰 버킷, `threading` import
- `server/workflows.py` — `_evaluate_branch_condition()` 11종, `_substitute_variables()`, variable 노드 `var_store` 인자
- `server/ollama_hub.py` — `api_ollama_create_model()`
- `server/nav_catalog.py` — `TAB_DESC_I18N` 38탭, `get_tab_desc()`
- `server/errors.py` — 에러 전환 100% 완료
- GET 75 + POST 63 = 138 라우트

## [2.0.0] — 2026-04-22

### 🎉 v2.0 메이저 릴리스 — 멀티 AI 오케스트라 플랫폼 완성

v1.0.2 → v2.0.0: **+10,800줄, 17개 커밋, 10개 태그**

### Added — Phase 10 (Final)
- 📋 **워크플로우 복제** — 목록에서 원클릭 clone (`POST /api/workflows/clone`)
- 📎 **노드 복사/붙여넣기** — `Ctrl+C`/`Ctrl+V` 선택 노드 복사 (+40px 오프셋, 새 ID)
- ↩️ **실행 취소** — `Ctrl+Z` undo 스택 (최대 30개, 노드/엣지 추가·삭제·이동 추적)
- ⌨️ **키보드 단축키** — `?` 키로 도움말 모달 (Delete/Ctrl+C/V/Z/S/F/Esc)
- 🌍 **i18n +22개 키** — 2,622개 × 3언어, **누락 0**

### v1.0.2 → v2.0.0 전체 누적
- **16개 노드 타입**: start, session, subagent, aggregate, branch, output, http, transform, variable, subworkflow, embedding, loop, retry, error_handler, merge, delay
- **8개 AI 프로바이더** + 커스텀 무제한: Claude CLI, Ollama, Gemini CLI, Codex + OpenAI API, Gemini API, Anthropic API, Ollama API
- **Ollama 모델 허브**: 23개 모델 카탈로그, 검색/다운로드/삭제
- **Embedding**: Ollama bge-m3, OpenAI text-embedding-3, 커스텀
- **워크플로우 엔진**: 병렬 실행, SSE 스트림, Webhook 트리거, Cron 스케줄러, Export/Import, 버전 히스토리, 빌트인 템플릿 8종
- **i18n**: ko/en/zh 2,622키, error_key 시스템 49키
- **API**: GET 73 + POST 59 = 132 라우트

## [1.9.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 9
- 📜 **워크플로우 버전 히스토리** — 저장 시 이전 버전 자동 보관 (최근 20개). Inspector에서 버전 목록 + 복원 버튼
- 📋 **빌트인 템플릿 5종** — 멀티 AI 비교, RAG 파이프라인, 코드 리뷰, 데이터 ETL, 재시도 워크플로우
- 🧙 **프로바이더 설정 위자드** — 3단계 가이드 (프로바이더 선택 → 연결 설정 → 테스트). localStorage "다시 보지 않기"
- 🏷️ **템플릿 갤러리 강화** — 카테고리 필터 (analysis/ai/dev/data/pattern/custom), 빌트인 배지, 삭제 불가 표시
- 🌍 **i18n +56개 키** — 2,599개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — 저장 시 히스토리 보관, `api_workflow_history()`, `api_workflow_restore()`, `BUILTIN_TEMPLATES` 5종
- `server/routes.py` — `/api/workflows/history`, `/api/workflows/restore`
- GET 73 + POST 57 라우트

## [1.8.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 8
- 🦙 **Ollama 모델 허브** (Open WebUI 스타일) — 23개 모델 카탈로그 (LLM/Code/Embedding/Vision 4개 카테고리)
  - 모델 검색 + 카테고리 필터
  - 원클릭 다운로드 (`ollama pull`) + 진행률 바 (2초 폴링)
  - 모델 삭제 + 상세 정보 (modelfile/parameters/template)
  - 설치된 모델 테이블 (크기/패밀리/양자화/수정일)
- ⚙️ **커스텀 프로바이더 완전 관리** — capabilities 배지, 테스트 실행, 편집 모드, embed() 실행 지원
- 🎯 **프로바이더별 기본 모델 설정** — 드롭다운 선택 + 저장 API
- 🔧 **CustomCliProvider.embed()** — embedCommand/embedArgsTemplate 로 임베딩 CLI 실행
- 🌍 **i18n +52개 키** — 2,543개 × 3언어, **누락 0**

### Architecture
- `server/ollama_hub.py` (신규) — 모델 카탈로그 23종, pull/delete/info/pull-status API
- `server/ai_providers.py` — CustomCliProvider.embed() 구현
- `server/ai_keys.py` — api_set_default_model()
- `server/routes.py` — Ollama 5개 + default-model 1개 = 6개 새 라우트
- `dist/index.html` — Ollama 허브 UI, 커스텀 프로바이더 편집, 기본 모델 드롭다운
- GET 72 + POST 56 라우트

## [1.7.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 7
- 🔀 **Merge 노드** — 여러 병렬 경로를 조건부 합류. all(전부)/any(하나라도)/count(N개) 모드 + 타임아웃
- ⏱️ **Delay 노드** — 지정 시간 대기 후 통과. 고정/랜덤 딜레이 모드
- 📊 **워크플로우 통계 대시보드** — 총 실행/성공률/평균 소요시간/활성 스케줄 카드 + 프로바이더별 사용 분포 (접기/펴기)
- 🔍 **노드 검색 필터** — 캔버스 상단 검색창. 이름/타입 매칭 → 하이라이트 (비매칭 노드 dimming)
- 🗺️ **미니맵 색상** — merge(시안 #06b6d4) / delay(회색 #94a3b8) 추가
- 📈 **`/api/workflows/stats`** — 전체 실행 통계 집계 (성공률, 프로바이더별, 트리거별, 워크플로우별)
- 🌍 **i18n +24개 키** — 2,480개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — merge/delay 노드 실행, `api_workflow_stats()` 통계 집계
- `dist/index.html` — merge/delay 편집 패널, 통계 대시보드, 노드 검색, 캔버스 색상
- 16개 노드 타입 · GET 68 + POST 53 라우트

## [1.6.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 6
- 🔄 **Loop 노드** — for_each(배열 순회) / count(횟수 반복) / while(조건 반복). 입력 분할 구분자 + 최대 반복 횟수
- 🔁 **Retry 노드** — 실패 시 자동 재시도. N회 + exponential backoff (초기 대기 × 배수). 지연 미리보기 UI
- 🛡️ **Error Handler 노드** — skip(무시) / default(기본값 반환) / route(에러 라우팅) 3가지 전략
- ⏰ **Cron 스케줄러** — 워크플로우를 cron 표현식으로 자동 실행. 서버 시작 시 스케줄러 스레드 자동 시작. 프리셋(매시/매일/평일/30분) + Inspector 설정 UI
- 🚨 **사용량 알림** — 일일 비용(USD) / 토큰 한도 설정. 초과 시 경고 배너 표시. `/api/ai-providers/usage-alert` API
- 🎨 **노드 캔버스 색상** — loop(연보라 #a78bfa) / retry(오렌지 #fb923c) / error_handler(빨강 #f87171)
- 🌍 **i18n +23개 키** — 2,456개 × 3언어, **누락 0**

### Architecture
- `server/workflows.py` — loop/retry/error_handler 노드 실행, `_cron_matches_now()`, `_scheduler_loop()`, `start_scheduler()`
- `server/ai_keys.py` — `api_usage_alert_check()` / `api_usage_alert_set()`
- `server/server.py` — `start_scheduler()` 부팅 시 호출
- `server/routes.py` — `/api/workflows/schedule/set`, `/schedules`, `/api/ai-providers/usage-alert`, `/usage-alert/set`
- `server/nav_catalog.py` — workflows 탭 키워드 확장 (loop, retry, cron, webhook 등)
- `dist/index.html` — 3종 노드 편집 패널, cron 설정 UI, 사용량 알림 설정/배너
- 14개 노드 타입 · GET 67 + POST 53 라우트

## [1.5.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 5
- 🔗 **Webhook 트리거** (`POST /api/workflows/webhook/{wfId}`) — 외부 시스템(GitHub Actions, Slack, cron 등)에서 HTTP로 워크플로우 실행. 입력 텍스트 주입 지원
- 🩺 **프로바이더 Health 대시보드** — AI 프로바이더 탭 상단에 실시간 초록/빨강 인디케이터 + "N/M 사용 가능" 요약
- 🗺️ **워크플로우 미니맵** — 캔버스 우하단 150×100px 조감도. 노드 타입별 색상 점 + 뷰포트 사각형 + 클릭 이동
- 📋 **Webhook URL 표시** — Inspector에 webhook URL + 클립보드 복사 + curl 예시 코드
- 🌐 **errMsg() 헬퍼** — `error_key` 기반 프론트 에러 번역 표시. 40+ toast 호출 전환
- 🔄 **백엔드 에러 i18n 완전 전환** — agents, skills, hooks, mcp, plugins, projects, features, commands, claude_md, actions 모듈 29개 에러에 `error_key` 추가

### Architecture
- `server/workflows.py` — `api_workflow_webhook()` Webhook 트리거
- `server/ai_keys.py` — `api_provider_health()` 병렬 헬스체크
- `server/agents.py`, `skills.py`, `hooks.py`, `mcp.py`, `plugins.py`, `projects.py`, `features.py`, `commands.py`, `claude_md.py`, `actions.py` — `err()` / `error_key` 전환
- `dist/index.html` — 헬스 바, Webhook URL, 미니맵, errMsg() 헬퍼
- `dist/locales/*.json` — 2,421개 키 × 3언어, **누락 0**

## [1.4.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 4
- 🔬 **멀티 AI 비교 전용 API** (`POST /api/ai-providers/compare`) — 여러 프로바이더에 동일 프롬프트 병렬 전송, 결과 일괄 반환
- 📦 **워크플로우 Export/Import** — JSON 파일로 내보내기/가져오기 (`POST /api/workflows/export`, `/import`). 툴바에 Export/Import 버튼
- 🔎 **노드 Inspector 프로바이더 정보** — 실행 결과 있는 노드 선택 시 프로바이더 아이콘, 모델, 소요 시간, 토큰, 비용 칩 표시
- 📊 **실행 이력 강화** — run 항목에 프로바이더별 색상 태그 + 집계 ("Claude ×3, GPT ×1"), duration 읽기 좋은 형태
- 🎨 **embedding 노드 캔버스 색상** — 분홍 `#f472b6`
- 🏗️ **에러 메시지 i18n 시스템** (`server/errors.py`) — 48개 에러 키 정의 + `err()` 헬퍼. 응답에 `error_key` 포함하여 프론트 번역 가능
- 🌍 **i18n +57개 키** — 48개 에러 키 + 9개 프론트 키 (export/import 등). 2,414개 × 3언어, **누락 0**
- 🔍 nav_catalog 키워드 확장 — aiProviders 탭에 embedding/비용/비교 키워드 추가

### Architecture
- `server/errors.py` (신규) — `ERROR_MESSAGES` dict + `err()`/`msg()` 헬퍼
- `server/ai_keys.py` — `api_provider_compare()` 병렬 비교 API
- `server/workflows.py` — `api_workflow_export()` / `api_workflow_import()`
- `server/actions.py` — 에러 메시지 `error_key` 포함 전환 시작
- `dist/index.html` — Export/Import 버튼, Inspector 프로바이더 칩, 이력 강화, embedding 색상
- `dist/locales/*.json` — 2,414개 키 × 3언어

## [1.3.0] — 2026-04-22

### Added — 멀티 AI 오케스트라 Phase 3
- 🧲 **Embedding 노드** — Ollama bge-m3, OpenAI text-embedding-3 등 임베딩 모델로 텍스트→벡터 변환. RAG/검색 파이프라인 구축용
- 🎯 **프로바이더 Capability 시스템** — chat/embed/code/vision/reasoning 5종 태깅. 모델별·프로바이더별 기능 필터링
  - Ollama API: embedding 모델 자동 감지 (bge, nomic-embed, e5, gte 등 키워드)
  - OpenAI API: embedding 3종 모델 추가 (text-embedding-3-large/small, ada-002)
- ⚙️ **커스텀 프로바이더 완전 통합** — capabilities, embedCommand, embedArgsTemplate 설정 가능. 워크플로우 assignee 드롭다운에 자동 노출
- 💰 **비용 분석 차트** (프론트) — 일별 비용 타임라인 (Chart.js 라인) + 프로바이더별 비용 비교 (도넛) + 총 호출/토큰/비용 요약 카드
- 📡 **워크플로우 SSE 실시간 스트림** (프론트) — EventSource 로 노드 진행률 실시간 반영, 실패 시 폴링 fallback
- 🎨 **노드 타입별 캔버스 색상** — http(초록) / transform(보라) / variable(노랑) / subworkflow(시안) / embedding(분홍)
- 🔬 **멀티 AI 비교 모드** — 동일 프롬프트를 여러 AI에 동시 전송 → 결과 나란히 비교
- 🌍 **i18n 전수 감사 완료** — 32개 누락 키 발견·추가 + embedding 5개 키. 최종 3개 언어 2,357개 키, **누락 0**
- 📋 백엔드 한글 하드코딩 에러 메시지 68개 식별 (향후 i18n 전환 준비 목록)
- 📋 nav_catalog.py 탭 설명 38개의 en/zh 번역 목록 작성

### Architecture
- `server/ai_providers.py` — `EmbeddingResponse`, `CAP_*` 상수, `BaseProvider.embed()` + `supports()`, Ollama/OpenAI embed 구현
- `server/workflows.py` — `embedding` 노드 타입 + `_execute_embedding_node()`
- `server/routes.py` — `/api/ai-providers/by-capability?cap=embed`
- `dist/index.html` — 비용 차트, SSE 스트림, 노드 색상, AI 비교 모드, embedding 편집 패널
- `dist/locales/*.json` — 2,357개 키 × 3개 언어

## [1.2.0] — 2026-04-22

### Added
- 🎛️ **워크플로우 프로바이더 셀렉터** — 노드 편집 패널에서 프로바이더:모델 드롭다운 선택 (그룹화 + 직접 입력 지원)
- 💰 **멀티 AI 비용 추적** — DB `workflow_costs` 테이블 + 프로바이더별/일별 집계 API (`/api/ai-providers/costs`)
- 📡 **워크플로우 실행 SSE 스트림** — `/api/workflows/run-stream?runId=...` SSE 엔드포인트, 실시간 노드 진행률 전송
- 🔁 **Sub-workflow 노드** — 다른 워크플로우를 노드로 호출, 입력 전달 + 결과 반환 (워크플로우 재사용)
- 🌐 **HTTP 노드 UI** — URL/메서드/Body/추출경로 편집 패널
- 🔄 **Transform 노드 UI** — 템플릿/JSON 추출/Regex/결합 4가지 변환 유형 편집
- 📌 **Variable 노드 UI** — 변수 이름 + 기본값 편집
- 🔁 **Sub-workflow 노드 UI** — 워크플로우 목록에서 선택 + 입력 전달 체크박스

### Architecture
- `server/db.py` — `workflow_costs` 테이블 스키마 추가
- `server/workflows.py` — `_execute_subworkflow_node`, `_record_workflow_cost`, `handle_workflow_run_stream` (SSE)
- `server/ai_keys.py` — `api_workflow_costs_summary` 집계 API
- `dist/index.html` — 10개 노드 타입 (4개 신규), 프로바이더 셀렉터, 노드 편집 패널 확장

## [1.1.0] — 2026-04-22

### Added
- 🧠 **AI 프로바이더 탭 (aiProviders)** — 멀티 AI 오케스트라 기반 구축
  - **8개 빌트인 프로바이더**: Claude CLI, Ollama, Gemini CLI, Codex (CLI) + OpenAI API, Gemini API, Anthropic API, Ollama API
  - CLI 자동 감지 (로컬 설치된 claude/ollama/gemini/codex) + API 키 설정
  - **커스텀 CLI 프로바이더** — 임의의 CLI 도구를 AI 프로바이더로 등록
  - **폴백 체인** — 1차 프로바이더 실패 시 대안 자동 전환
  - 연결 테스트 + 모델 카탈로그 + 가격표 내장
- 🔀 **워크플로우 멀티 프로바이더 통합**
  - 노드 assignee: `claude:opus`, `openai:gpt-4.1`, `gemini:2.5-pro`, `ollama:llama3.1`, `codex:o4-mini`
  - 기존 Claude 전용 assignee 완전 호환 유지
- ⚡ **워크플로우 병렬 실행 엔진** — 같은 depth 노드를 ThreadPoolExecutor 로 동시 실행
- 🌐 **새 노드 타입 3종**: HTTP (외부 API 호출), Transform (JSON/regex/템플릿 변환), Variable (변수 저장)
- 🌍 33개 신규 i18n 키 (ko/en/zh)

### Architecture
- `server/ai_providers.py` (신규) — BaseProvider ABC + 8개 구현체 + ProviderRegistry 싱글턴
- `server/ai_keys.py` (신규) — `~/.claude-dashboard-ai-providers.json` 설정 CRUD
- `server/workflows.py` — `_execute_node` 멀티 프로바이더 대응, `_topological_levels` 병렬 실행
- `server/routes.py` — `/api/ai-providers/*` 엔드포인트 7개 추가

## [1.0.2] — 2026-04-22

### Added
- 챗봇 응답 대기 동안 마스코트가 **"잠시만요~! 결과를 불러오고 있어요"** 등 5종 메시지를 2.6초 간격으로 순환 표시. 첫 토큰 도착·에러·완료·finally 시 자동 정리. ko/en/zh 번역 포함.

## [1.0.1] — 2026-04-22

### Changed
- 대시보드 도우미 챗봇 모델을 **Haiku 로 하향** (`--model haiku`). 단순 JSON 라우팅 응답에 최적. 토큰 비용 대폭 절감. `CHAT_MODEL` 환경변수로 오버라이드 가능.

## [1.0.0] — 2026-04-22

첫 공식 릴리스 태그. 누적된 주요 기능을 여기서 하나로 묶어 마감.

### 신규 탭 / 기능
- 🔀 **워크플로우 (workflows)** — n8n 스타일 DAG 에디터
  - 6종 노드 (start · session · subagent · aggregate · branch · output)
  - 포트 드래그 엣지 + DAG 사이클 거부 + 🎯 맞춤(자동 정렬)
  - 🎭 세션 하네스: 페르소나/허용 도구/resume session_id
  - 🖥️ Terminal 새 창 spawn · 🔄 session_id 이어쓰기
  - 📋 템플릿: 팀 개발(리드+프론트+백엔드)/리서치/병렬 3 + 커스텀 저장
  - 🔁 **Repeat** — 반복 횟수/스케줄(HH:MM)/피드백 노트 자동 주입
  - 📜 실행 이력 · 🎬 인터랙티브 14 장면 튜토리얼(typewriter)
- 🚀 **시작하기 (onboarding)** — ~/.claude 상태 실시간 감지 단계별 체크리스트
- 📚 **가이드 & 툴 (guideHub)** — 외부 가이드/유용한 툴/베스트 프랙티스/치트시트

### 전반
- 모든 네이티브 `prompt/confirm` 을 맥 스타일 `promptModal`/`confirmModal` 로 통일
- 3개 언어 (ko/en/zh) 완전 번역 · `verify-translations` 검증 통과
- 모바일 대응: 마스코트 탭 시 챗창 즉시 닫힘 버그 해결, 창 크기 cap, 플로팅 맞춤 버튼
- 챗봇 시스템 프롬프트가 `server/nav_catalog.py` 를 읽어 자동 생성 — 탭 추가 시 자동 반영
