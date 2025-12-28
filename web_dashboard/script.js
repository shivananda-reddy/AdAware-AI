
const API_BASE = "http://127.0.0.1:8000";

// --- Tab Navigation ---
const tabs = {
  analyze: document.getElementById('view-analyze'),
  history: document.getElementById('view-history'),
  stats: document.getElementById('view-stats')
};
const btns = {
  analyze: document.getElementById('btn-analyze-tab'),
  history: document.getElementById('btn-history-tab'),
  stats: document.getElementById('btn-stats-tab')
};

function switchTab(name) {
  Object.values(tabs).forEach(el => el.style.display = 'none');
  Object.values(btns).forEach(el => el.classList.remove('active'));
  tabs[name].style.display = 'block';
  btns[name].classList.add('active');

  if (name === 'history') loadHistory();
  if (name === 'stats') loadStats();
}

btns.analyze.addEventListener('click', () => switchTab('analyze'));
btns.history.addEventListener('click', () => switchTab('history'));
btns.stats.addEventListener('click', () => switchTab('stats'));

// --- Analyze Logic (Legacy + New) ---
const fileInput = document.getElementById("file-input");
const dropZone = document.getElementById("drop-zone");
const urlInput = document.getElementById("url-input");
const captionInput = document.getElementById("caption-input");
const btnAnalyze = document.getElementById("btn-analyze");
const backendStatus = document.getElementById("backend-status");

const resultContainer = document.getElementById("result-container");
const resContent = document.getElementById("res-content");
const resLabel = document.getElementById("res-label");
const resScore = document.getElementById("res-score");

// Status Check
async function checkBackend() {
  try {
    await fetch(API_BASE + "/docs", { method: "HEAD" });
    backendStatus.textContent = "Backend: Online";
    backendStatus.style.color = "#0f0";
  } catch (e) {
    backendStatus.textContent = "Backend: Offline";
    backendStatus.style.color = "#f00";
  }
}
checkBackend();

// File handling
dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", handleFile);
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.style.borderColor = "#0ff"; });
dropZone.addEventListener("dragleave", (e) => { e.preventDefault(); dropZone.style.borderColor = "#333"; });
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.style.borderColor = "#333";
  if (e.dataTransfer.files.length) handleFile({ target: { files: e.dataTransfer.files } });
});

let currentImageBase64 = null;

function handleFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (evt) => {
    currentImageBase64 = evt.target.result.split(',')[1];
    dropZone.innerHTML = `<img src="${evt.target.result}" style="max-height:150px; border-radius:8px">`;
  };
  reader.readAsDataURL(file);
}

// Analyze Call
btnAnalyze.addEventListener("click", async () => {
  const payload = {
    image_base64: currentImageBase64,
    image_url: urlInput.value.trim() || null,
    caption_text: captionInput.value.trim() || null,
    use_llm: document.getElementById('chk-use-llm').checked,
    consent: document.getElementById('chk-consent').checked,
    page_origin: "dashboard"
  };

  if (!payload.image_base64 && !payload.image_url && !payload.caption_text) {
    alert("Please provide an image or text.");
    return;
  }

  resultContainer.style.display = "block";
  resLabel.className = "label-badge";
  resLabel.textContent = "Analyzing...";
  resContent.innerHTML = '<div class="spinner"></div>';

  try {
    const res = await fetch(API_BASE + "/analyze_hover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    renderResult(data);
  } catch (e) {
    resLabel.textContent = "Error";
    resContent.innerHTML = `<p style="color:red">${e.message}</p>`;
  }
});

function renderResult(data) {
  const label = data.final_label.replace('-', ' ').toUpperCase();
  resLabel.textContent = label;
  resScore.textContent = `Risk Score: ${(data.risk_score * 100).toFixed(0)}/100`;

  // Color code
  if (data.final_label === "safe") resLabel.style.background = "green";
  else if (data.final_label === "high-risk" || data.final_label === "scam-suspected") resLabel.style.background = "red";
  else resLabel.style.background = "orange";

  let html = `<div class="p-4">`;

  // Explanation
  if (data.explanation_text) {
    html += `<p class="explanation">${data.explanation_text}</p>`;
  }

  // Evidence
  const evidence = data.evidence || {};
  if (evidence.risky_phrases && evidence.risky_phrases.length > 0) {
    html += `<h4>Risky Phrases Detected:</h4><ul>`;
    evidence.risky_phrases.forEach(p => {
      html += `<li>"${p.phrase}" - <small>${p.reason}</small></li>`;
    });
    html += `</ul>`;
  }

  // Rules
  if (data.rule_triggers && data.rule_triggers.length > 0) {
    html += `<h4>Policy Violations:</h4><ul>`;
    data.rule_triggers.forEach(r => {
      html += `<li><span class="badge-${r.severity}">${r.rule_id}</span> ${r.description}</li>`;
    });
    html += `</ul>`;
  }

  // Source Reputation
  if (data.source_reputation && data.source_reputation.flags.length > 0) {
    html += `<h4>Source Reputation Flags:</h4><ul>`;
    data.source_reputation.flags.forEach(f => html += `<li>${f}</li>`);
    html += `</ul>`;
  }

  html += `</div>`;
  resContent.innerHTML = html;
}

// --- History Logic ---
let historyData = []; // Store fetched list for detail retrieval

async function loadHistory() {
  const tbody = document.getElementById('history-tbody');
  tbody.innerHTML = '<tr><td colspan="4">Loading...</td></tr>';

  try {
    const res = await fetch(API_BASE + "/api/v1/history?limit=20");
    historyData = await res.json();

    tbody.innerHTML = '';
    if (historyData.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4">No history yet.</td></tr>';
      return;
    }

    historyData.forEach((item, idx) => {
      const row = document.createElement('tr');
      row.style.cursor = "pointer";
      row.innerHTML = `
                <td>${new Date(item.timestamp).toLocaleTimeString()}</td>
                <td>${item.source_reputation?.domain || item.domain || "Unknown"}</td>
                <td><span class="badgex ${item.final_label}">${item.final_label}</span></td>
                <td>${(item.risk_score * 100).toFixed(0)}</td>
            `;
      row.addEventListener('click', () => showDetails(idx));
      tbody.appendChild(row);
    });

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:red">Failed to load history: ${e.message}</td></tr>`;
  }
}

function showDetails(idx) {
  const item = historyData[idx];
  if (!item) return;

  document.querySelector('#details-pane .placeholder-text').style.display = 'none';
  document.getElementById('details-content').style.display = 'block';

  document.getElementById('det-id').textContent = item.request_id || item.id || "N/A";
  document.getElementById('det-label').textContent = item.final_label;
  document.getElementById('det-score').textContent = `${(item.risk_score * 100).toFixed(0)}/100`;
  document.getElementById('det-explanation').textContent = item.explanation_text || "No explanation available.";
  document.getElementById('det-ocr').textContent = item.ocr_text || "N/A";

  // Evidence list
  const evidenceUl = document.getElementById('det-evidence');
  evidenceUl.innerHTML = '';
  const ev = item.evidence || {};
  if (ev.risky_phrases && ev.risky_phrases.length > 0) {
    ev.risky_phrases.forEach(p => {
      const li = document.createElement('li');
      li.innerHTML = `<mark>${p.text || p.phrase}</mark> - ${p.reason}`;
      evidenceUl.appendChild(li);
    });
  } else {
    evidenceUl.innerHTML = '<li>No specific evidence spans recorded.</li>';
  }
}

document.getElementById('btn-refresh-history').addEventListener('click', loadHistory);

// --- Stats Logic ---
async function loadStats() {
  try {
    const res = await fetch(API_BASE + "/api/v1/stats");
    const stats = await res.json();

    document.getElementById('stat-total').textContent = stats.total_analyses;

    const ul = document.getElementById('stat-labels-list');
    ul.innerHTML = '';
    Object.entries(stats.label_counts).forEach(([k, v]) => {
      const li = document.createElement('li');
      li.textContent = `${k}: ${v}`;
      ul.appendChild(li);
    });

    const correct = stats.confusion_matrix.correct || 0;
    const total = correct + (stats.confusion_matrix.incorrect || 0);
    const acc = total ? ((correct / total) * 100).toFixed(1) + "%" : "N/A";
    document.getElementById('stat-accuracy').textContent = acc;

  } catch (e) {
    console.error(e);
  }
}