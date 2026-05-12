// Orchestrator provider — "openclaw-style" multi-agent dispatch.
//
// A user message arriving at PROVIDERS.orchestrator is NOT forwarded
// 1:1 to a single backend. Instead the provider performs three phases:
//
//   1. PLAN     — the configured planner provider decomposes the task
//                 into 2–5 self-contained subtasks (JSON shape).
//   2. EXECUTE  — each subtask is dispatched to a worker provider
//                 (round-robin over cfg.orchestrator.workers). Workers
//                 stream their replies; the orchestrator surfaces them
//                 inline so the user can watch progress.
//   3. SYNTHESIS — the planner re-enters with all subtask outputs and
//                 produces the final answer.
//
// Provider/model spec is "<provider>:<model>" (same shape as the chat
// REPL's `/model anthropic/claude-opus-4-7` after normalisation). When
// the model part is omitted, the worker's defaultModel from
// PROVIDER_INFO is used.
//
// Config (~/.lazyclaw/config.json):
//   {
//     "orchestrator": {
//       "planner": "claude-cli:claude-opus-4-7",
//       "workers": [
//         "claude-cli:claude-sonnet-4-6",
//         "openai:gpt-4o",
//         "gemini:gemini-2.5-pro"
//       ],
//       "maxSubtasks": 5,       // optional, default 5
//       "concurrency": 0        // optional, 0 = sequential (visible streaming)
//     }
//   }
//
// Defaults: planner = the user's currently configured `cfg.provider`
// (so `lazyclaw onboard --provider claude-cli` works without any extra
// step), workers = [planner] (degenerates to a single-agent chain that
// still benefits from plan + synthesis structure).

import { PROVIDERS, PROVIDER_INFO } from './registry.mjs';

function _parseSpec(spec) {
  if (!spec || typeof spec !== 'string') return { provider: '', model: '' };
  const colon = spec.indexOf(':');
  if (colon < 0) return { provider: spec.trim(), model: '' };
  return { provider: spec.slice(0, colon).trim(), model: spec.slice(colon + 1).trim() };
}

function _lookupProvider(spec) {
  const { provider, model } = _parseSpec(spec);
  const prov = PROVIDERS[provider];
  if (!prov) return null;
  const info = PROVIDER_INFO[provider] || {};
  return {
    name: provider,
    model: model || info.defaultModel || '',
    prov,
    info,
  };
}

function _bestPlanArray(text) {
  // Planners sometimes wrap the JSON in prose / code fences. Try the
  // raw response first, then the largest [...] / [...]-shaped span.
  const tryParse = (s) => {
    try { return JSON.parse(s); } catch { return null; }
  };
  let arr = tryParse(text);
  if (Array.isArray(arr)) return arr;
  // Strip ```json fences
  const fence = text.match(/```(?:json)?\s*([\s\S]+?)```/);
  if (fence) {
    arr = tryParse(fence[1].trim());
    if (Array.isArray(arr)) return arr;
  }
  // Largest [...] substring
  const start = text.indexOf('[');
  const end = text.lastIndexOf(']');
  if (start >= 0 && end > start) {
    arr = tryParse(text.slice(start, end + 1));
    if (Array.isArray(arr)) return arr;
  }
  return null;
}

const PLANNER_SYSTEM = `You are an orchestrator that decomposes a user request into independent subtasks for parallel worker agents.

Rules:
- Output ONLY a JSON array. No prose, no markdown, no code fences.
- Each entry has shape { "id": <int>, "task": "<one-sentence imperative>", "rationale": "<why this is a useful slice>" }.
- 2 to 5 subtasks. Each must be doable WITHOUT seeing the others' outputs (parallel-safe).
- If the request is genuinely atomic (e.g. "say hi"), return a single-element array.
- Do not add a synthesis / merge step — that runs separately after workers complete.
- Subtasks must be self-contained: include any context a worker needs to act on the task alone.`;

const SYNTHESIS_SYSTEM = `You are an orchestrator producing the final answer for the user.

You receive: (1) the user's original request, (2) the subtask plan you produced, (3) each worker's response.

Rules:
- Synthesize a single coherent answer. Distill — do not echo each worker verbatim.
- Cite worker findings briefly when they meaningfully diverge ("Worker A found …, Worker B confirmed").
- If a worker failed, acknowledge it but do not let it block the rest of the answer.
- Match the tone and length the user implied (one-line question → one-line answer; deep dive → deep dive).
- No JSON; this is the human-facing reply.`;

/**
 * Build an orchestrator provider. The chat REPL / agent / daemon path
 * treats it like any other provider — the `sendMessage` async iterable
 * yields markdown chunks describing plan + subtasks + synthesis.
 *
 * @param {Object} [opts]
 * @param {() => Record<string, unknown>} [opts.cfgGetter] reads ~/.lazyclaw/config.json
 * @param {(cfg, provider) => string} [opts.keyResolver] returns api-key for a worker provider (mirrors cli.mjs::_resolveAuthKey)
 */
export function makeOrchestratorProvider(opts = {}) {
  const cfgGetter = typeof opts.cfgGetter === 'function' ? opts.cfgGetter : () => ({});
  const keyResolver = typeof opts.keyResolver === 'function' ? opts.keyResolver : () => '';

  return {
    name: 'orchestrator',
    async *sendMessage(messages, callerOpts = {}) {
      const cfg = cfgGetter() || {};
      const o = cfg.orchestrator && typeof cfg.orchestrator === 'object' ? cfg.orchestrator : {};
      const fallbackSpec = cfg.provider && cfg.provider !== 'orchestrator'
        ? `${cfg.provider}${cfg.model ? ':' + cfg.model : ''}`
        : 'claude-cli';
      const plannerSpec = String(o.planner || fallbackSpec);
      const workerSpecs = Array.isArray(o.workers) && o.workers.length
        ? o.workers.map(String)
        : [plannerSpec];
      const maxSubtasks = Number.isFinite(o.maxSubtasks) && o.maxSubtasks > 0 ? Math.min(10, o.maxSubtasks) : 5;

      const planner = _lookupProvider(plannerSpec);
      if (!planner) {
        yield `⚠ orchestrator: planner provider "${plannerSpec}" is not registered. ` +
          `Set cfg.orchestrator.planner to a valid "provider:model" (e.g. "claude-cli:claude-opus-4-7").\n`;
        return;
      }
      // Self-recursion guard: a misconfigured cfg.orchestrator.planner =
      // "orchestrator" would otherwise spin forever, with each call
      // dispatching back to itself.
      if (planner.name === 'orchestrator') {
        yield `⚠ orchestrator: planner cannot be "orchestrator" — set cfg.orchestrator.planner to a real provider (e.g. "claude-cli:claude-opus-4-7").\n`;
        return;
      }
      const workers = workerSpecs.map(_lookupProvider).filter(Boolean).filter(w => w.name !== 'orchestrator');
      if (workers.length === 0) {
        yield `⚠ orchestrator: no usable workers (cfg.orchestrator.workers is empty, all unknown, or only references "orchestrator" itself).\n`;
        return;
      }

      const userText = (() => {
        // Most recent user message becomes the orchestration target. We
        // pass earlier turns as context to the planner only — workers
        // see a self-contained subtask string, not chat history.
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === 'user') return String(messages[i].content || '');
        }
        return '';
      })();

      // ── Phase 1: PLAN ───────────────────────────────────────────────
      yield `## 🦞 Orchestrator\n\n`;
      yield `Planner: \`${planner.name}${planner.model ? ':' + planner.model : ''}\`  ·  Workers: ${workers.map(w => `\`${w.name}${w.model ? ':' + w.model : ''}\``).join(', ')}\n\n`;
      yield `### 1. Planning\n\n`;

      const plannerMessages = [
        { role: 'system', content: PLANNER_SYSTEM },
        ...messages.filter(m => m.role === 'user' || m.role === 'assistant'),
      ];
      let planRaw = '';
      try {
        for await (const chunk of planner.prov.sendMessage(plannerMessages, {
          apiKey: keyResolver(cfg, planner.name),
          model: planner.model || undefined,
          signal: callerOpts.signal,
          maxTokens: 1024,
        })) {
          planRaw += String(chunk);
        }
      } catch (e) {
        yield `⚠ planner error: ${e?.message || String(e)}\n\n`;
        // Fallback: hand the user message to the first worker directly.
        const w = workers[0];
        yield `Falling back to direct call on \`${w.name}${w.model ? ':' + w.model : ''}\`:\n\n`;
        for await (const chunk of w.prov.sendMessage(messages, {
          apiKey: keyResolver(cfg, w.name),
          model: w.model || undefined,
          signal: callerOpts.signal,
        })) yield String(chunk);
        return;
      }

      const plan = _bestPlanArray(planRaw);
      if (!plan || plan.length === 0) {
        yield `⚠ planner returned no parseable JSON plan. Raw output:\n\n\`\`\`\n${planRaw.trim().slice(0, 800)}\n\`\`\`\n\nFalling back to single-shot on \`${planner.name}${planner.model ? ':' + planner.model : ''}\`:\n\n`;
        for await (const chunk of planner.prov.sendMessage(messages, {
          apiKey: keyResolver(cfg, planner.name),
          model: planner.model || undefined,
          signal: callerOpts.signal,
        })) yield String(chunk);
        return;
      }
      const trimmed = plan.slice(0, maxSubtasks).map((p, i) => ({
        id: Number.isFinite(p?.id) ? p.id : i + 1,
        task: String(p?.task || '').trim(),
        rationale: String(p?.rationale || '').trim(),
      })).filter(p => p.task);
      if (trimmed.length === 0) {
        yield `⚠ plan parsed but contained no usable subtasks. Falling back.\n\n`;
        for await (const chunk of planner.prov.sendMessage(messages, {
          apiKey: keyResolver(cfg, planner.name),
          model: planner.model || undefined,
          signal: callerOpts.signal,
        })) yield String(chunk);
        return;
      }

      for (const p of trimmed) {
        yield `${p.id}. **${p.task}**${p.rationale ? ` _— ${p.rationale}_` : ''}\n`;
      }
      yield `\n`;

      // ── Phase 2: EXECUTE ────────────────────────────────────────────
      yield `### 2. Executing ${trimmed.length} subtask${trimmed.length === 1 ? '' : 's'}\n\n`;
      const results = [];
      for (let i = 0; i < trimmed.length; i++) {
        const sub = trimmed[i];
        const worker = workers[i % workers.length];
        yield `**Subtask ${sub.id}** \`${worker.name}${worker.model ? ':' + worker.model : ''}\` — ${sub.task}\n\n`;
        let res = '';
        try {
          for await (const chunk of worker.prov.sendMessage([{ role: 'user', content: sub.task }], {
            apiKey: keyResolver(cfg, worker.name),
            model: worker.model || undefined,
            signal: callerOpts.signal,
          })) {
            const s = String(chunk);
            res += s;
            yield s;
          }
          results.push({ ...sub, worker: `${worker.name}${worker.model ? ':' + worker.model : ''}`, result: res, error: null });
        } catch (e) {
          const msg = e?.message || String(e);
          yield `\n⚠ worker error: ${msg}\n`;
          results.push({ ...sub, worker: `${worker.name}${worker.model ? ':' + worker.model : ''}`, result: '', error: msg });
        }
        yield `\n\n---\n\n`;
      }

      // ── Phase 3: SYNTHESIS ──────────────────────────────────────────
      yield `### 3. Synthesis\n\n`;
      const synthUser = [
        `Original request:\n${userText}`,
        `\nSubtask plan and worker outputs:`,
        ...results.map(r => `\n#### Subtask ${r.id} — ${r.task}\nWorker: ${r.worker}\n${r.error ? `Error: ${r.error}` : r.result.trim()}`),
        `\nNow write the final answer for the user.`,
      ].join('\n');
      try {
        for await (const chunk of planner.prov.sendMessage([
          { role: 'system', content: SYNTHESIS_SYSTEM },
          { role: 'user', content: synthUser },
        ], {
          apiKey: keyResolver(cfg, planner.name),
          model: planner.model || undefined,
          signal: callerOpts.signal,
        })) yield String(chunk);
      } catch (e) {
        yield `⚠ synthesis error: ${e?.message || String(e)}. Worker outputs above are the final material — please review them directly.\n`;
      }
    },
  };
}
