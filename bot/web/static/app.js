// BotControl - Dashboard Logic and Real-time WebSockets

let currentTab = 'resin';
let selectedRuns = 6;
let ws = null;
let isTaskRunning = false;
let isTaskPaused = false;

// DOM Elements
const deviceBadge = document.getElementById('device-badge');
const deviceStatusText = document.getElementById('device-status-text');
const taskBadge = document.getElementById('task-badge');
const taskStatusText = document.getElementById('task-status-text');
const resolutionInfo = document.getElementById('resolution-info');

const btnStart = document.getElementById('btn-start');
const btnPause = document.getElementById('btn-pause');
const btnStop = document.getElementById('btn-stop');
const btnClearLogs = document.getElementById('btn-clear-logs');
const consoleLogs = document.getElementById('console-logs');

const screenWrapper = document.getElementById('screen-wrapper');
const streamImg = document.getElementById('stream-img');
const touchRipple = document.getElementById('touch-ripple');
const btnRefreshStream = document.getElementById('btn-refresh-stream');

// Initialize Tabs
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));

    btn.classList.add('active');
    currentTab = btn.getAttribute('data-tab');
    document.getElementById(`tab-${currentTab}`).classList.add('active');
  });
});

// Initialize Run Selector
document.querySelectorAll('.btn-run').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.btn-run').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    selectedRuns = parseInt(btn.getAttribute('data-runs'), 10);
  });
});

// Refresh Stream
btnRefreshStream.addEventListener('click', () => {
  streamImg.src = `/api/stream?t=${Date.now()}`;
});

// Click to Touch on iPad Screen
screenWrapper.addEventListener('click', (e) => {
  const rect = screenWrapper.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const clickY = e.clientY - rect.top;

  const normX = Math.max(0, Math.min(1, clickX / rect.width));
  const normY = Math.max(0, Math.min(1, clickY / rect.height));

  // Show ripple effect
  touchRipple.style.left = `${clickX}px`;
  touchRipple.style.top = `${clickY}px`;
  touchRipple.classList.add('active');
  setTimeout(() => {
    touchRipple.classList.remove('active');
  }, 300);

  // Send touch to backend
  fetch('/api/touch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ x: normX, y: normY, normalized: true }),
  }).catch((err) => console.error('Lỗi gửi touch:', err));
});

// Append Log to Console
function appendLog(message, level = 'info') {
  const entry = document.createElement('div');
  entry.className = `log-entry log-${level}`;
  entry.textContent = message;
  consoleLogs.appendChild(entry);
  consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

btnClearLogs.addEventListener('click', () => {
  consoleLogs.innerHTML = '';
});

// WebSocket Connection for Real-time Logs
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

  ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      appendLog(data.message, data.level);
    } catch (e) {
      appendLog(event.data);
    }
  };

  ws.onclose = () => {
    setTimeout(initWebSocket, 2000);
  };
}

// Poll Status
async function updateStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    // Update Device Status
    if (data.device_connected) {
      deviceBadge.className = 'badge badge-online';
      deviceStatusText.textContent = `iPad M5 Đã Kết Nối (${data.device_wda_url})`;
    } else {
      deviceBadge.className = 'badge badge-offline';
      deviceStatusText.textContent = 'iPad M5 Chưa Kết Nối (WDA Offline)';
    }

    if (data.resolution) {
      resolutionInfo.textContent = `Độ phân giải: ${data.resolution.width} × ${data.resolution.height}`;
    }

    // Update Task Status
    isTaskRunning = data.task_running;
    isTaskPaused = data.task_paused;

    if (isTaskRunning) {
      taskBadge.className = 'badge badge-running';
      taskStatusText.textContent = isTaskPaused
        ? `Đang tạm dừng (${data.task_name})`
        : `Đang chạy: ${data.task_name}`;
      btnStart.disabled = true;
      btnPause.disabled = false;
      btnStop.disabled = false;
      btnPause.innerHTML = isTaskPaused
        ? '<span class="btn-icon">▶</span> Tiếp Tục'
        : '<span class="btn-icon">⏸</span> Tạm Dừng';
    } else {
      taskBadge.className = 'badge badge-idle';
      taskStatusText.textContent = 'Đang chờ tác vụ';
      btnStart.disabled = false;
      btnPause.disabled = true;
      btnStop.disabled = true;
      btnPause.innerHTML = '<span class="btn-icon">⏸</span> Tạm Dừng';
    }
  } catch (err) {
    console.error('Lỗi cập nhật status:', err);
  }
}

// Start Task
btnStart.addEventListener('click', async () => {
  let taskName = currentTab;
  let config = {};

  if (currentTab === 'resin') {
    config = {
      category: document.getElementById('resin-category').value,
      sub_target: 'exp',
      runs: selectedRuns,
      use_fuel: document.getElementById('resin-use-fuel').checked,
      ensure_auto_battle: document.getElementById('resin-auto-battle').checked,
    };
  } else if (currentTab === 'daily') {
    config = {
      claim_assignments: document.getElementById('daily-assignments').checked,
      claim_training: document.getElementById('daily-training').checked,
    };
  } else if (currentTab === 'dialogue') {
    config = {
      interval: parseFloat(document.getElementById('dialogue-interval').value),
      auto_skip: document.getElementById('dialogue-auto-skip').checked,
    };
  }

  btnStart.disabled = true;
  try {
    const res = await fetch('/api/task/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: taskName, config: config }),
    });
    const result = await res.json();
    if (result.status !== 'started') {
      alert(`Không thể bắt đầu: ${result.message || 'Lỗi không xác định'}`);
    }
  } catch (e) {
    alert(`Lỗi: ${e.message}`);
  }
  updateStatus();
});

// Pause / Resume Task
btnPause.addEventListener('click', async () => {
  const endpoint = isTaskPaused ? '/api/task/resume' : '/api/task/pause';
  await fetch(endpoint, { method: 'POST' });
  updateStatus();
});

// Stop Task
btnStop.addEventListener('click', async () => {
  if (confirm('Bạn có chắc chắn muốn dừng tác vụ ngay lập tức không?')) {
    await fetch('/api/task/stop', { method: 'POST' });
    updateStatus();
  }
});

// Initial bootstrap
initWebSocket();
updateStatus();
setInterval(updateStatus, 1500);
