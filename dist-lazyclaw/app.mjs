// LazyClaw chat front-end. Settings persist via localStorage.
// Provider streaming is consumed via async iteration so the bot bubble
// grows incrementally character by character.

const KEYS = { apiKey: 'lc.apiKey', model: 'lc.model', provider: 'lc.provider' };

const els = {
  apiKey: document.getElementById('apiKey'),
  model: document.getElementById('model'),
  provider: document.getElementById('provider'),
  save: document.getElementById('saveSettings'),
  msgs: document.getElementById('messages'),
  input: document.getElementById('input'),
  send: document.getElementById('send'),
  error: document.getElementById('error'),
};

function loadSettings() {
  const apiKey = localStorage.getItem(KEYS.apiKey);
  const model = localStorage.getItem(KEYS.model);
  const provider = localStorage.getItem(KEYS.provider);
  if (apiKey !== null) els.apiKey.value = apiKey;
  if (model !== null) els.model.value = model;
  if (provider !== null) els.provider.value = provider;
}

function saveSettings() {
  localStorage.setItem(KEYS.apiKey, els.apiKey.value);
  localStorage.setItem(KEYS.model, els.model.value);
  localStorage.setItem(KEYS.provider, els.provider.value);
}

async function* mockChunks(text, delay = 5) {
  for (const ch of text) {
    await new Promise(r => setTimeout(r, delay));
    yield ch;
  }
}

const PROVIDERS = {
  mock: {
    name: 'mock',
    async *sendMessage(messages) {
      const last = messages[messages.length - 1];
      yield* mockChunks(`mock-reply: ${last?.content ?? ''}`);
    },
  },
  anthropic: {
    name: 'anthropic',
    async *sendMessage(messages, opts) {
      if (!opts || !opts.apiKey) {
        const e = new Error('invalid api key');
        e.code = 'INVALID_KEY';
        throw e;
      }
      const last = messages[messages.length - 1];
      yield* mockChunks(`anthropic[${opts.model || 'default'}]: ${last?.content ?? ''}`);
    },
  },
};

window.__lc = { PROVIDERS };

const messages = [];

function appendMsg(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role === 'user' ? 'user' : 'bot'}`;
  div.dataset.role = role;
  div.textContent = text;
  els.msgs.appendChild(div);
  return div;
}

async function send() {
  els.error.textContent = '';
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = '';
  appendMsg('user', text);
  messages.push({ role: 'user', content: text });

  const provName = els.provider.value;
  const prov = (window.__lc.PROVIDERS && window.__lc.PROVIDERS[provName]) || PROVIDERS[provName];
  if (!prov) { els.error.textContent = `unknown provider: ${provName}`; return; }

  const opts = { apiKey: els.apiKey.value, model: els.model.value };
  if (provName === 'anthropic' && !opts.apiKey) {
    els.error.textContent = 'invalid api key';
    return;
  }

  const botDiv = appendMsg('assistant', '');
  try {
    let acc = '';
    for await (const chunk of prov.sendMessage(messages, opts)) {
      acc += chunk;
      botDiv.textContent = acc;
    }
    messages.push({ role: 'assistant', content: acc });
  } catch (err) {
    els.error.textContent = err && err.message ? err.message : String(err);
    botDiv.remove();
  }
}

els.save.addEventListener('click', saveSettings);
els.send.addEventListener('click', send);
els.input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

loadSettings();
