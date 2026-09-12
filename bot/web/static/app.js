// BotControl - Advanced Dashboard Logic, Dynamic Categories & Telemetry

let currentTab = 'resin';
let selectedRuns = 6;
let currentResinMode = 'character_target'; // 'character_target' or 'category'
let ws = null;
let isTaskRunning = false;
let isTaskPaused = false;

// Subtarget options dictionary
const subtargetsMap = {
  calyx_golden: [
    { value: 'Nu Hoa Hoi Uc', label: 'EXP Nhân Vật (Nụ Hoa Hồi Ức - Sách EXP)' },
    { value: 'Nu Hoa Bau Vat', label: 'Điểm Tín Dụng (Nụ Hoa Báu Vật - Tiền Credits)' },
    { value: 'Nu Hoa Di Thai', label: 'EXP Nón Ánh Sáng (Nụ Hoa Dĩ Thái - Aether)' },
  ],
  calyx_crimson: [
    { value: 'Ky Uc', label: '🌸 Ký Ức (Nụ Hoa Hồi Ức - Robin / Kremnos)' },
    { value: 'Huy Diet', label: '⚔️ Hủy Diệt (Nụ Hoa Hủy Diệt - Suối Ẩn / Lân Uyên Cảnh)' },
    { value: 'San Ban', label: '🏹 Săn Bắn (Nụ Hoa Săn Bắn - Mũi Tên Tinh Linh)' },
    { value: 'Tri Thuc', label: '📜 Tri Thức (Nụ Hoa Tri Thức - Chìa Khóa Linh Hồn)' },
    { value: 'Hoa Hop', label: '🎵 Hòa Hợp (Nụ Hoa Hòa Hợp - Giai Điệu Trên Bầu Trời)' },
    { value: 'Hu Vo', label: '🌌 Hư Vô (Nụ Hoa Hư Vô - Mầm Mống Hư Vô)' },
    { value: 'Bao Ho', label: '🛡️ Bảo Hộ (Nụ Hoa Bảo Hộ - Bền Bỉ Hổ Phách)' },
    { value: 'Tru Phu', label: '🌿 Trù Phú (Nụ Hoa Trù Phú - Mầm Mống Sinh Mệnh)' },
  ],
  planar: [
    { value: 'De Xuat Phu Kien', label: 'Phụ Kiện Vị Diện Đề Xuất (Theo Nhân Vật)' },
    { value: 'Duran', label: 'Duran - Vương Quốc Đom Đóm & Thợ Rèn' },
    { value: 'Cong Vien Chuoi', label: 'Công Viên Chuối Tuyệt Diệu' },
    { value: 'Dau Truong Ngoi Sao', label: 'Đấu Trường Ngôi Sao & Rutilant Arena' },
    { value: 'Salsotto', label: 'Salsotto Trơ Trọi & Belobog Của Đấng Kiến Tạo' },
  ],
  stagnant_shadow: [
    { value: 'Vat Ly', label: 'Thuộc tính Vật Lý (Răng Nanh Sắt / Bánh Răng)' },
    { value: 'Hoa', label: 'Thuộc tính Hỏa (Lưỡi Dao Rực Lửa / Đuốc Cháy)' },
    { value: 'Bang', label: 'Thuộc tính Băng (Mũi Tên Băng / Tinh Thể Tuyết)' },
    { value: 'Loi', label: 'Thuộc tính Lôi (Mão Vương Miện Sấm Sét)' },
    { value: 'Phong', label: 'Thuộc tính Phong (Đôi Cánh Bão Tố)' },
    { value: 'Luong Tu', label: 'Thuộc tính Lượng Tử (Hư Ảnh Hạt Nhân)' },
    { value: 'So Ao', label: 'Thuộc tính Số Ảo (Dây Leo Quá Khứ)' },
  ],
  cavern_corrosion: [
    { value: 'De Xuat Di Vat', label: 'Di Vật Hang Động Đề Xuất (Theo Nhân Vật)' },
    { value: 'Con Duong Nam Dam', label: 'Con Đường Nắm Đấm (Thiện Xạ Rừng Già & Quyền Vương)' },
    { value: 'Con Duong Gio Tuyet', label: 'Con Đường Gió Tuyết (Thợ Săn Băng & Chim Ưng)' },
    { value: 'Con Duong Duoc Si', label: 'Con Đường Dược Sĩ (Môn Đồ Trường Thọ & Tín Sứ)' },
    { value: 'Con Duong Bong Toi', label: 'Con Đường Bóng Tối (Tiên Phong Nước Chết & Tử Thần)' },
    { value: 'Con Duong Hiep Si', label: 'Con Đường Hiệp Sĩ (Dũng Sĩ Bão Tố & Thánh Sứ)' },
  ],
  echo_of_war: [
    { value: 'Quai Thu Tan The', label: 'Quái Thú Tận Thế (Doomsday Beast)' },
    { value: 'Cocolia', label: 'Tàn Dư Rét Căm (Cocolia)' },
    { value: 'Phantylia', label: 'Hạt Giống Bất Diệt (Phantylia)' },
    { value: 'Skaracabaz', label: 'Lỗ Hổng Tận Cùng (Vua Đom Đóm Skaracabaz)' },
    { value: 'Sunday', label: 'Triết Gia Hòa Hợp (Sunday - Harmonious Choir)' },
  ],
};

// DOM Elements
const deviceBadge = document.getElementById('device-badge');
const deviceStatusText = document.getElementById('device-status-text');
const taskBadge = document.getElementById('task-badge');
const taskStatusText = document.getElementById('task-status-text');
const resolutionInfo = document.getElementById('resolution-info');

const powerVal = document.getElementById('power-val');
const powerProgressFill = document.getElementById('power-progress-fill');
const fuelVal = document.getElementById('fuel-val');

const btnStart = document.getElementById('btn-start');
const btnPause = document.getElementById('btn-pause');
const btnStop = document.getElementById('btn-stop');
const btnClearLogs = document.getElementById('btn-clear-logs');
const consoleLogs = document.getElementById('console-logs');

const screenWrapper = document.getElementById('screen-wrapper');
const streamImg = document.getElementById('stream-img');
const touchRipple = document.getElementById('touch-ripple');
const btnRefreshStream = document.getElementById('btn-refresh-stream');
const btnInspectScreen = document.getElementById('btn-inspect-screen');
const btnRunInspect = document.getElementById('btn-run-inspect');

// Mode Switcher Elements
const modeCharTarget = document.getElementById('mode-char-target');
const modeCategory = document.getElementById('mode-category');
const viewCharTarget = document.getElementById('view-char-target');
const viewCategory = document.getElementById('view-category');
const resinCategory = document.getElementById('resin-category');
const resinSubtarget = document.getElementById('resin-subtarget');

// Initialize Tabs
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));

    btn.classList.add('active');
    currentTab = btn.getAttribute('data-tab');
    const targetContent = document.getElementById(`tab-${currentTab}`);
    if (targetContent) targetContent.classList.add('active');
  });
});

// Mode Switcher (Character Target vs Category)
modeCharTarget.addEventListener('click', () => {
  modeCharTarget.classList.add('active');
  modeCategory.classList.remove('active');
  viewCharTarget.classList.add('active');
  viewCategory.classList.remove('active');
  currentResinMode = 'character_target';
});

modeCategory.addEventListener('click', () => {
  modeCategory.classList.add('active');
  modeCharTarget.classList.remove('active');
  viewCategory.classList.add('active');
  viewCharTarget.classList.remove('active');
  currentResinMode = 'category';
});

// Dynamic Subtarget Selector
function updateSubtargets() {
  const cat = resinCategory.value;
  const options = subtargetsMap[cat] || [];
  resinSubtarget.innerHTML = '';
  options.forEach((opt) => {
    const el = document.createElement('option');
    el.value = opt.value;
    el.textContent = opt.label;
    resinSubtarget.appendChild(el);
  });
}
resinCategory.addEventListener('change', updateSubtargets);
updateSubtargets();

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

// Quick Action Shortcuts
document.querySelectorAll('.btn-quick').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const action = btn.getAttribute('data-action');
    try {
      await fetch('/api/quick_action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
    } catch (e) {
      console.error('Lỗi quick action:', e);
    }
  });
});

// Click to Touch on iPad Screen
screenWrapper.addEventListener('click', (e) => {
  const rect = screenWrapper.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const clickY = e.clientY - rect.top;

  const normX = Math.max(0, Math.min(1, clickX / rect.width));
  const normY = Math.max(0, Math.min(1, clickY / rect.height));

  touchRipple.style.left = `${clickX}px`;
  touchRipple.style.top = `${clickY}px`;
  touchRipple.classList.add('active');
  setTimeout(() => {
    touchRipple.classList.remove('active');
  }, 250);

  fetch('/api/touch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ x: normX, y: normY, normalized: true }),
  }).catch((err) => console.error('Lỗi gửi touch:', err));
});

// OCR Inspector Function
async function runScreenInspection() {
  const tbody = document.getElementById('inspector-tbody');
  const inspectCount = document.getElementById('inspect-count');
  tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;">Đang phân tích hình ảnh...</td></tr>';

  try {
    const res = await fetch('/api/inspect');
    const data = await res.json();
    if (data.status === 'ok') {
      if (data.power) {
        updatePowerDisplay(data.power.current, data.power.max);
      }
      if (data.fuel !== null && data.fuel !== undefined) {
        fuelVal.textContent = `${data.fuel} bình`;
      }

      inspectCount.textContent = `Phát hiện ${data.items_count} thành phần văn bản`;
      tbody.innerHTML = '';
      data.items.forEach((it) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${it.text}</strong></td>
          <td><span style="color:${it.score > 0.8 ? '#10b981' : '#f59e0b'}">${(it.score * 100).toFixed(0)}%</span></td>
          <td>(${it.center[0]}, ${it.center[1]})</td>
        `;
        tbody.appendChild(tr);
      });
    } else {
      tbody.innerHTML = `<tr><td colspan="3" style="color:#ef4444;">Lỗi: ${data.message}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="3" style="color:#ef4444;">Lỗi kết nối: ${err.message}</td></tr>`;
  }
}

btnInspectScreen.addEventListener('click', () => {
  // Switch to inspector tab
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));
  document.querySelector('[data-tab="inspector"]').classList.add('active');
  document.getElementById('tab-inspector').classList.add('active');
  currentTab = 'inspector';
  runScreenInspection();
});

btnRunInspect.addEventListener('click', runScreenInspection);

// Update Trailblaze Power Progress Display
function updatePowerDisplay(curr, maxVal) {
  powerVal.textContent = `${curr} / ${maxVal}`;
  const pct = Math.min(100, Math.max(0, (curr / maxVal) * 100));
  powerProgressFill.style.width = `${pct}%`;
  if (pct >= 80) {
    powerProgressFill.style.background = 'linear-gradient(90deg, #ef4444, #f59e0b)';
  } else {
    powerProgressFill.style.background = 'linear-gradient(90deg, #c084fc, #38bdf8)';
  }
}

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
      deviceStatusText.textContent = `iPad M5 Online (${data.device_wda_url})`;
    } else {
      deviceBadge.className = 'badge badge-offline';
      deviceStatusText.textContent = 'iPad M5 Offline (Chờ WDA)';
    }

    if (data.resolution) {
      resolutionInfo.textContent = `Độ phân giải: ${data.resolution.width} × ${data.resolution.height}`;
    }

    // Telemetry
    if (data.trailblaze_power) {
      updatePowerDisplay(data.trailblaze_power.current, data.trailblaze_power.max);
    }
    if (data.fuel_count !== null && data.fuel_count !== undefined) {
      fuelVal.textContent = `${data.fuel_count} bình`;
    }

    // Anti-Ban Status Badge
    const antibanBadge = document.getElementById('antiban-badge');
    const antibanText = document.getElementById('antiban-status-text');
    if (antibanBadge && antibanText) {
      if (data.antiban_active) {
        antibanBadge.className = 'badge badge-active';
        antibanBadge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        antibanText.textContent = '🛡️ Anti-Ban: Bật';
      } else {
        antibanBadge.className = 'badge badge-offline';
        antibanBadge.style.borderColor = 'rgba(239, 68, 68, 0.4)';
        antibanText.textContent = '🛡️ Anti-Ban: Tắt';
      }
    }

    // Task Status
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
      mode: currentResinMode,
      category: resinCategory.value,
      sub_target: resinSubtarget.value,
      character_item: document.getElementById('char-target-item').value,
      runs: selectedRuns,
      use_fuel: document.getElementById('resin-use-fuel').checked,
      ensure_auto_battle: document.getElementById('resin-auto-battle').checked,
    };
  } else if (currentTab === 'simulated') {
    taskName = 'simulated_universe';
    config = {
      mode: document.getElementById('su-mode').value,
      preferred_path: document.getElementById('su-path').value,
      runs: parseInt(document.getElementById('su-runs').value, 10),
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

// Anti-Ban Toggle Listener
const antibanBadgeEl = document.getElementById('antiban-badge');
if (antibanBadgeEl) {
  antibanBadgeEl.addEventListener('click', async () => {
    try {
      await fetch('/api/antiban/toggle', { method: 'POST' });
      updateStatus();
    } catch (e) {
      console.error('Lỗi toggle anti-ban:', e);
    }
  });
}

// Bootstrap
initWebSocket();
updateStatus();
setInterval(updateStatus, 1500);
