/* ReplitAI WebApp Frontend */

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const API_BASE = window.location.origin;
let userId = tg?.initDataUnsafe?.user?.id || 0;
let activeProject = 'default';
let terminal = null;
let terminalWs = null;
let isDark = true;

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  messages: [],
  files: [],
  projects: [],
  selectedFile: null,
};

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const chatMessages = $('chatMessages');
const chatInput = $('chatInput');
const sendBtn = $('sendBtn');

// ─── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    $(`tab-${target}`).classList.add('active');
    if (target === 'terminal') initTerminal();
    if (target === 'files') loadFiles();
    if (target === 'projects') loadProjects();
  });
});

// ─── Theme ─────────────────────────────────────────────────────────────────────
$('themeToggle').addEventListener('click', () => {
  isDark = !isDark;
  document.body.classList.toggle('light', !isDark);
  $('themeToggle').textContent = isDark ? '🌙' : '☀️';
});

// ─── Chat ──────────────────────────────────────────────────────────────────────
function renderMarkdown(text) {
  try {
    return marked.parse(text, { breaks: true, gfm: true });
  } catch { return text; }
}

function addMessage(role, content, isLoading = false) {
  const msg = document.createElement('div');
  msg.className = `msg ${role}`;
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const avatarText = role === 'user' ? '👤' : '⚡';

  let bodyContent;
  if (isLoading) {
    bodyContent = `<div class="msg-content">
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
        <span style="font-size:.8rem;color:var(--text-dim);margin-left:6px">${content}</span>
      </div>
    </div>`;
  } else {
    const rendered = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);
    const codeBlocks = extractCodeBlocks(content);
    const actionsHtml = codeBlocks.length > 0
      ? `<div class="msg-actions">
          ${codeBlocks.map((b, i) => `<button class="msg-action-btn" onclick="openCodeModal('${escapeHtml(b.lang)}', ${i}, event)">▶️ ${b.lang || 'code'}</button>`).join('')}
          <button class="msg-action-btn" onclick="copyText(\`${escapeJs(content)}\`)">📋 Copy</button>
        </div>`
      : `<div class="msg-actions"><button class="msg-action-btn" onclick="copyText(\`${escapeJs(content)}\`)">📋 Copy</button></div>`;

    bodyContent = `<div class="msg-content">${rendered}</div>${actionsHtml}<div class="msg-time">${time}</div>`;
  }

  msg.innerHTML = `
    <div class="msg-avatar">${avatarText}</div>
    <div class="msg-body">${bodyContent}</div>
  `;
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  document.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  return msg;
}

function extractCodeBlocks(text) {
  const blocks = [];
  const regex = /```(\w*)\n([\s\S]*?)```/g;
  let m;
  while ((m = regex.exec(text)) !== null) {
    blocks.push({ lang: m[1] || 'python', code: m[2] });
  }
  return blocks;
}

window._codeBlocks = {};
function openCodeModal(lang, idx, event) {
  const btn = event.target;
  const msgBody = btn.closest('.msg-body');
  const content = msgBody?.querySelector('.msg-content')?.textContent || '';
  const blocks = extractCodeBlocks(msgBody?.closest('.msg')?.querySelector('.msg-content')?.innerHTML?.replace(/<[^>]+>/g, '') || content);
  const block = blocks[idx];
  if (!block) return;
  $('modalTitle').textContent = `${block.lang || 'code'} — ready to run`;
  $('modalCode').className = `language-${block.lang}`;
  $('modalCode').textContent = block.code;
  hljs.highlightElement($('modalCode'));
  window._currentCode = block;
  $('codeOutput').className = 'code-output';
  $('codeOutput').textContent = '';
  $('codeModal').classList.add('open');
}
$('closeModal').addEventListener('click', () => $('codeModal').classList.remove('open'));
$('codeModal').addEventListener('click', e => { if (e.target === $('codeModal')) $('codeModal').classList.remove('open'); });
$('copyCode').addEventListener('click', () => {
  if (window._currentCode) copyText(window._currentCode.code);
});
$('runCode').addEventListener('click', async () => {
  if (!window._currentCode) return;
  const output = $('codeOutput');
  output.className = 'code-output has-output';
  output.textContent = '⏳ Running...';
  try {
    const res = await fetch(`${API_BASE}/api/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'run_code',
        args: [window._currentCode.code, window._currentCode.lang],
        user_id: userId,
        project: activeProject,
      }),
    });
    const data = await res.json();
    output.textContent = data.output || '(no output)';
    output.style.color = data.success ? 'var(--accent2)' : 'var(--error)';
  } catch (e) {
    output.textContent = `Error: ${e.message}`;
  }
});

async function sendMessage() {
  const msg = chatInput.value.trim();
  if (!msg || sendBtn.disabled) return;
  sendBtn.disabled = true;
  chatInput.value = '';
  addMessage('user', msg);
  const loadingMsg = addMessage('assistant', 'Thinking...', true);
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, user_id: userId, project: activeProject }),
    });
    const data = await res.json();
    loadingMsg.remove();
    addMessage('assistant', data.response || 'Error getting response');
  } catch (e) {
    loadingMsg.remove();
    addMessage('assistant', `❌ Connection error: ${e.message}\n\nMake sure the backend is running.`);
  } finally {
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
document.querySelectorAll('.quick-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    chatInput.value = btn.dataset.msg;
    sendMessage();
  });
});

// ─── Terminal ──────────────────────────────────────────────────────────────────
function initTerminal() {
  if (terminal) return;
  terminal = new Terminal({
    theme: {
      background: '#0d1117', foreground: '#e6edf3',
      cursor: '#58a6ff', selection: '#264f78',
    },
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: 13,
    cursorBlink: true,
    allowTransparency: true,
  });
  const fitAddon = new FitAddon.FitAddon();
  terminal.loadAddon(fitAddon);
  terminal.open($('terminal'));
  fitAddon.fit();
  window.addEventListener('resize', () => fitAddon.fit());
  connectTerminalWs();
}

function connectTerminalWs() {
  const wsUrl = `${API_BASE.replace('http', 'ws')}/ws/terminal/${userId}/${activeProject}`;
  terminalWs = new WebSocket(wsUrl);
  terminalWs.onopen = () => terminal?.write('\r\n\x1b[32m✅ Connected to sandbox\x1b[0m\r\n$ ');
  terminalWs.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'output') terminal?.write('\r\n' + msg.data);
    else if (msg.type === 'welcome') terminal?.write('\x1b[36m' + msg.data + '\x1b[0m');
  };
  terminalWs.onclose = () => terminal?.write('\r\n\x1b[31m[Disconnected]\x1b[0m\r\n');
  terminalWs.onerror = () => terminal?.write('\r\n\x1b[31m[Connection error]\x1b[0m\r\n');
}

function sendTerminalCommand(cmd) {
  if (terminalWs?.readyState === WebSocket.OPEN) {
    terminal?.write(`\r\n\x1b[33m$ ${cmd}\x1b[0m`);
    terminalWs.send(JSON.stringify({ type: 'command', data: cmd }));
  } else {
    toast('Terminal not connected. Reconnecting...');
    connectTerminalWs();
  }
}

$('terminalSend').addEventListener('click', () => {
  const cmd = $('terminalInput').value.trim();
  if (!cmd) return;
  $('terminalInput').value = '';
  sendTerminalCommand(cmd);
});
$('terminalInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const cmd = $('terminalInput').value.trim();
    $('terminalInput').value = '';
    sendTerminalCommand(cmd);
  }
});
$('clearTerminal').addEventListener('click', () => terminal?.clear());
$('reconnectTerminal').addEventListener('click', () => {
  terminalWs?.close();
  connectTerminalWs();
});

// ─── Files ─────────────────────────────────────────────────────────────────────
const FILE_ICONS = {
  py: '🐍', js: '🟨', ts: '🔷', html: '🌐', css: '🎨',
  json: '📋', md: '📝', txt: '📄', yml: '⚙️', yaml: '⚙️',
  sh: '🔧', go: '🔵', rs: '🦀', java: '☕', cpp: '⚡',
  dockerfile: '🐳', toml: '⚙️', env: '🔑', sql: '🗄️',
};

function getFileIcon(path) {
  const ext = path.split('.').pop()?.toLowerCase();
  if (path.toLowerCase() === 'dockerfile') return '🐳';
  return FILE_ICONS[ext] || '📄';
}

async function loadFiles() {
  const tree = $('fileTree');
  tree.innerHTML = '<div class="file-item"><span>Loading...</span></div>';
  try {
    const res = await fetch(`${API_BASE}/api/files/${userId}/${activeProject}`);
    const data = await res.json();
    tree.innerHTML = '';
    if (!data.files?.length) {
      tree.innerHTML = '<div class="file-item" style="color:var(--text-dim)">No files yet</div>';
      return;
    }
    data.files.filter(f => f.type === 'file').forEach(f => {
      const item = document.createElement('div');
      item.className = 'file-item';
      item.innerHTML = `<span class="file-icon">${getFileIcon(f.path)}</span><span>${f.path}</span>`;
      item.addEventListener('click', () => loadFileContent(f.path, item));
      tree.appendChild(item);
    });
  } catch (e) {
    tree.innerHTML = `<div class="file-item" style="color:var(--error)">Error: ${e.message}</div>`;
  }
}

async function loadFileContent(path, el) {
  document.querySelectorAll('.file-item').forEach(i => i.classList.remove('selected'));
  el.classList.add('selected');
  const viewer = $('fileViewer');
  viewer.innerHTML = '<div style="color:var(--text-dim)">Loading...</div>';
  try {
    const res = await fetch(`${API_BASE}/api/file/${userId}/${activeProject}?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (data.success) {
      const ext = path.split('.').pop();
      viewer.innerHTML = `<pre><code class="language-${ext}">${escapeHtml(data.content)}</code></pre>`;
      document.querySelectorAll('#fileViewer pre code').forEach(el => hljs.highlightElement(el));
    } else {
      viewer.innerHTML = `<div style="color:var(--error)">${data.content}</div>`;
    }
  } catch (e) {
    viewer.innerHTML = `<div style="color:var(--error)">Error: ${e.message}</div>`;
  }
}

$('refreshFiles').addEventListener('click', loadFiles);

// ─── Projects ──────────────────────────────────────────────────────────────────
async function loadProjects() {
  const list = $('projectList');
  list.innerHTML = '<div style="color:var(--text-dim);padding:16px">Loading...</div>';
  try {
    const res = await fetch(`${API_BASE}/api/projects/${userId}`);
    const data = await res.json();
    list.innerHTML = '';
    if (!data.projects?.length) {
      list.innerHTML = '<div style="color:var(--text-dim);padding:16px">No projects yet. Create one from the Telegram bot with /new</div>';
      return;
    }
    data.projects.forEach(p => {
      const card = document.createElement('div');
      card.className = `project-card${p.name === activeProject ? ' active-project' : ''}`;
      card.innerHTML = `
        <div class="project-name">${p.name}${p.name === activeProject ? ' <span style="color:var(--accent2);font-size:.75rem">● active</span>' : ''}</div>
        <div class="project-meta">${p.language || 'python'}</div>
      `;
      card.addEventListener('click', () => switchProject(p.name));
      list.appendChild(card);
    });
  } catch (e) {
    list.innerHTML = `<div style="color:var(--error);padding:16px">Error: ${e.message}</div>`;
  }
}

function switchProject(name) {
  activeProject = name;
  $('projectBadge').textContent = name;
  loadProjects();
  toast(`Switched to project: ${name}`);
}

$('newProject').addEventListener('click', () => {
  const name = prompt('Project name (lowercase, no spaces):');
  if (name) {
    const clean = name.toLowerCase().replace(/[^a-z0-9-]/g, '-');
    addMessage('user', `/new ${clean}`);
    const loadingMsg = addMessage('assistant', 'Creating project...', true);
    fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: `Create project ${clean}`, user_id: userId, project: 'default' }),
    }).then(r => r.json()).then(d => {
      loadingMsg.remove();
      addMessage('assistant', d.response || 'Project created!');
      loadProjects();
    }).catch(e => { loadingMsg.remove(); addMessage('assistant', `Error: ${e.message}`); });
    document.querySelector('[data-tab="chat"]').click();
  }
});

// ─── Status ────────────────────────────────────────────────────────────────────
$('statusBtn').addEventListener('click', async () => {
  addMessage('user', 'Show bot status');
  const loadingMsg = addMessage('assistant', 'Fetching status...', true);
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: '/status', user_id: userId, project: activeProject }),
    });
    const data = await res.json();
    loadingMsg.remove();
    addMessage('assistant', data.response);
  } catch (e) {
    loadingMsg.remove();
    addMessage('assistant', `Error: ${e.message}`);
  }
  document.querySelector('[data-tab="chat"]').click();
});

// ─── Helpers ───────────────────────────────────────────────────────────────────
function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escapeJs(text) {
  return String(text).replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$');
}
function copyText(text) {
  navigator.clipboard?.writeText(text).then(() => toast('Copied!')).catch(() => toast('Copy failed'));
}
function toast(msg, duration = 2500) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

// ─── Load history on start ─────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/history/${userId}/${activeProject}`);
    const data = await res.json();
    if (data.history?.length) {
      data.history.slice(-15).forEach(m => addMessage(m.role === 'user' ? 'user' : 'assistant', m.content));
    } else {
      addMessage('assistant', '⚡ **Welcome to ReplitAI WebApp!**\n\nI\'m your AI coding agent. Send me any coding task and I\'ll handle it — write code, run tests, deploy, search the web, and more.\n\nTry the quick action buttons below!');
    }
  } catch {
    addMessage('assistant', '⚡ **ReplitAI ready.** Ask me anything!');
  }
}

// ─── Init ──────────────────────────────────────────────────────────────────────
(async function init() {
  if (tg?.colorScheme === 'light') {
    isDark = false;
    document.body.classList.add('light');
    $('themeToggle').textContent = '☀️';
  }
  if (tg?.initDataUnsafe?.user?.id) {
    userId = tg.initDataUnsafe.user.id;
  }
  $('projectBadge').textContent = activeProject;
  await loadHistory();
})();
