// dashboard.js

const API_BASE = "http://127.0.0.1:8000";
const ANALYZE_ENDPOINT = `${API_BASE}/analyze_hover`;

// DOM references
const backendStatusEl = document.getElementById("backendStatus");
const imageFileInput   = document.getElementById("imageFile");
const imageUrlInput    = document.getElementById("imageUrl");
const useLlmCheckbox   = document.getElementById("useLlm");
const btnAnalyze       = document.getElementById("btnAnalyze");
const previewInner     = document.getElementById("previewInner");
const resultArea       = document.getElementById("resultArea");

// --- Optional: sync LLM toggle with extension popup/background (if running as extension) ---
function hasChromeStorage() {
  try {
    return typeof chrome !== "undefined" && chrome.storage && chrome.storage.sync;
  } catch {
    return false;
  }
}

function loadLlmPreferenceIntoDashboard() {
  if (!hasChromeStorage() || !useLlmCheckbox) return;

  chrome.storage.sync.get(["adaware_use_llm"], (data) => {
    if (chrome.runtime && chrome.runtime.lastError) return;
    const val = data.adaware_use_llm;
    if (typeof val === "boolean") {
      useLlmCheckbox.checked = val;
    }
  });
}

function saveLlmPreferenceFromDashboard() {
  if (!hasChromeStorage() || !useLlmCheckbox) return;
  chrome.storage.sync.set({ adaware_use_llm: !!useLlmCheckbox.checked });
}
// ---------- Backend status ----------
async function checkBackend() {
  if (!backendStatusEl) return;
  try {
    const res = await fetch(`${API_BASE}/docs`, { method: "GET" });
    if (res.ok) {
      backendStatusEl.classList.remove("offline");
      backendStatusEl.classList.add("online");
      backendStatusEl.innerHTML = `<span class="status-dot">●</span> Backend online`;
    } else {
      throw new Error("Non-OK status");
    }
  } catch {
    backendStatusEl.classList.remove("online");
    backendStatusEl.classList.add("offline");
    backendStatusEl.innerHTML = `<span class="status-dot">●</span> Backend offline`;
  }
}

// ---------- Image helpers ----------
function renderPreview(src) {
  if (!previewInner) return;
  if (!src) {
    previewInner.innerHTML = `<div class="preview-placeholder">No image selected yet</div>`;
    return;
  }
  previewInner.innerHTML = `<img src="${src}" alt="Ad preview" class="preview-img">`;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result || "";
      const base64 = String(result).split(",")[1] || "";
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ---------- Small UI helpers ----------
function riskPill(level) {
  const l = (level || "unknown").toLowerCase();
  if (l === "low")   return `<span class="pill green">Low risk</span>`;
  if (l === "medium") return `<span class="pill yellow">Medium risk</span>`;
  if (l === "high")  return `<span class="pill red">High risk</span>`;
  return `<span class="pill">Risk: unknown</span>`;
}

function trustPill(auth) {
  const a = (auth || "").toLowerCase();
  if (!a) return `<span class="pill yellow">Authenticity: unknown</span>`;
  if (a.includes("high"))    return `<span class="pill green">Likely authentic</span>`;
  if (a.includes("low") || a.includes("suspicious")) return `<span class="pill red">Suspicious</span>`;
  return `<span class="pill yellow">Authenticity: ${escapeHtml(a)}</span>`;
}

function consistencyPill(label) {
  const l = (label || "").toLowerCase();
  if (l === "consistent") return `<span class="pill green">Visual match</span>`;
  if (l.includes("partial")) return `<span class="pill yellow">Partial match</span>`;
  if (l) return `<span class="pill red">Mismatch</span>`;
  return `<span class="pill">Consistency: unknown</span>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ---------- Render report ----------
function renderReport(report) {
  if (!resultArea) return;

  const riskProfile = report.risk_profile || {};
  const labelFinal = riskProfile.label_final || report.label || "Unknown label";
  const riskLevelFinal =
    riskProfile.risk_level_final ||
    riskProfile.risk_level_inferred ||
    "unknown";

  const credFinal = typeof riskProfile.credibility_final === "number"
    ? riskProfile.credibility_final
    : Number(report.credibility || 0);

  const credClassic = typeof riskProfile.credibility_classic === "number"
    ? riskProfile.credibility_classic
    : null;
  const credLlm = typeof riskProfile.credibility_llm === "number"
    ? riskProfile.credibility_llm
    : null;

  const credScore = Math.max(0, Math.min(100, Math.round(credFinal)));
  const confModel = typeof report.confidence === "number"
    ? `${(report.confidence * 100).toFixed(1)}%`
    : "N/A";

  // Summary: prefer LLM-based
  const finalExpl = report.explanation_final || {};
  const summaryText =
    (typeof report.llm_summary === "string" && report.llm_summary.trim()) ||
    (typeof finalExpl.explanation_text === "string" && finalExpl.explanation_text.trim()) ||
    "Analysis complete, but no text summary was generated.";

  const bullets = Array.isArray(finalExpl.bullets)
    ? finalExpl.bullets
    : (Array.isArray(report.llm_explanation?.bullets)
        ? report.llm_explanation.bullets
        : []);

  const worthIt = finalExpl.worth_it || "unknown";
  const worthReason = finalExpl.worth_reason || "";

  // persuasion info (LLM-aware NLP)
  const persuasion = finalExpl.persuasion || {};
  const ctaStrength = persuasion.call_to_action_strength || "unknown";
  const allPhrases = Array.isArray(persuasion.all_phrases)
    ? persuasion.all_phrases
    : [];

  // Product info
  const pinfo = report.product_info || {};
  const pname = pinfo.product_name || "Unknown product";
  const brand = pinfo.brand_name || "Unknown brand";
  const category = pinfo.category || "Unclassified";
  const price = pinfo.detected_price || "Not found";

  // trust & risk
  const trust = report.trust || {};
  const adAuth = trust.ad_authenticity || "";
  const urlTrust = trust.url_trust || "";
  const reasons = Array.isArray(riskProfile.reasons)
    ? riskProfile.reasons
    : (Array.isArray(trust.reasons) ? trust.reasons : []);
  const riskSignals = Array.isArray(riskProfile.risk_signals)
    ? riskProfile.risk_signals
    : (Array.isArray(trust.risk_signals) ? trust.risk_signals : []);

  // fusion / vision
  const fusion = report.fusion_consistency || {};
  const fusionScore =
    typeof fusion.consistency_score_final === "number"
      ? fusion.consistency_score_final.toFixed(2)
      : "N/A";
  const fusionLabel = fusion.overall_consistency_final || "";
  const fusionReason = fusion.reasoning || "";

  const imgSim =
    typeof report.image_text_similarity === "number"
      ? report.image_text_similarity.toFixed(2)
      : "N/A";

  const imgQuality = report.image_quality || {};
  const blurScore =
    typeof imgQuality.blur_score === "number"
      ? imgQuality.blur_score.toFixed(1)
      : "N/A";
  const isBlurry = imgQuality.is_blurry === true;

  // Credibility color for progress
  let credColorClass = "green";
  if (credScore <= 40) credColorClass = "red";
  else if (credScore <= 70) credColorClass = "yellow";

  // JSON pretty (escaped)
  const jsonPretty = escapeHtml(JSON.stringify(report, null, 2));

  // Build HTML
  resultArea.innerHTML = `
    <div class="results-grid">
      <!-- LEFT: Summary -->
      <div class="summary-panel">
        <div class="section-heading">
          <span class="dot"></span>
          AI Summary
        </div>
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:6px;">
          <div style="font-weight:600; font-size:0.95rem;">
            ${escapeHtml(labelFinal)}
          </div>
          <div>
            ${riskPill(riskLevelFinal)}
          </div>
        </div>

        <div class="summary-text">${escapeHtml(summaryText)}</div>

        ${
          bullets && bullets.length
            ? `
          <ul style="margin-top:10px; padding-left:18px; font-size:0.8rem; color:#d1d5db;">
            ${bullets
              .slice(0, 6)
              .map(b => `<li>${escapeHtml(b)}</li>`)
              .join("")}
          </ul>`
            : ""
        }

        ${
          report.ad_hash
            ? `<div class="id-chip">
                 <span>ID</span>
                 <span>${escapeHtml(report.ad_hash)}</span>
               </div>`
            : ""
        }
      </div>

      <!-- RIGHT: Metrics & product -->
      <div class="details-panel">
        <div class="section-heading">
          <span class="dot"></span>
          Trust & Metrics
        </div>

        <div class="metric-row">
          <span class="metric-label">Trust score (final)</span>
          <span class="metric-value">${credScore}/100</span>
        </div>
        <div class="progress-wrapper">
          <div class="progress-bg">
            <div class="progress-fill" style="width:${credScore}%;"></div>
          </div>
        </div>

        ${
          credClassic !== null || credLlm !== null
            ? `<div style="margin-top:4px; font-size:0.7rem; color:#9ca3af;">
                 ${
                   credLlm !== null
                     ? `LLM: ${Math.round(credLlm)}`
                     : ""
                 }
                 ${
                   credClassic !== null
                     ? `${credLlm !== null ? " • " : ""}Classic: ${Math.round(
                         credClassic
                       )}`
                     : ""
                 }
               </div>`
            : ""
        }

        <div class="metric-row" style="margin-top:10px;">
          <span class="metric-label">Model confidence</span>
          <span class="metric-value">${confModel}</span>
        </div>

        <div class="metric-row">
          <span class="metric-label">Image-text similarity</span>
          <span class="metric-value">${imgSim}</span>
        </div>

        <div class="metric-row">
          <span class="metric-label">Fusion consistency</span>
          <span class="metric-value">${fusionScore}</span>
        </div>

        <div class="pill-row" style="margin-top:8px;">
          ${trustPill(adAuth)}
          ${consistencyPill(fusionLabel)}
          ${
            urlTrust
              ? `<span class="pill">URL trust: ${escapeHtml(
                  urlTrust.toLowerCase()
                )}</span>`
              : ""
          }
        </div>

        <div class="metric-row" style="margin-top:10px;">
          <span class="metric-label">Image blur score</span>
          <span class="metric-value">
            ${blurScore}${blurScore !== "N/A" ? (isBlurry ? " (blurry)" : " (sharp)") : ""}
          </span>
        </div>

        <!-- Product -->
        <div class="section-heading" style="margin-top:14px;">
          <span class="dot"></span>
          Product & Pricing
        </div>
        <div style="font-size:0.8rem;">
          <div class="metric-row">
            <span class="metric-label">Product</span>
            <span class="metric-value">${escapeHtml(pname)}</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">Brand</span>
            <span class="metric-value">${escapeHtml(brand)}</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">Category</span>
            <span class="metric-value">${escapeHtml(category)}</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">Detected price</span>
            <span class="metric-value">${escapeHtml(price)}</span>
          </div>
        </div>

        <!-- Persuasion / CTA -->
        <div class="section-heading" style="margin-top:14px;">
          <span class="dot"></span>
          Persuasion & Advice
        </div>
        <div style="font-size:0.8rem; color:#e5e7eb;">
          <div class="metric-row">
            <span class="metric-label">Call-to-action strength</span>
            <span class="metric-value">${escapeHtml(ctaStrength)}</span>
          </div>
          <div style="margin-top:6px;">
            Is it worth it?
            <strong>${escapeHtml(worthIt)}</strong>
            ${
              worthReason
                ? `<span style="display:block; margin-top:3px; color:#9ca3af;">${escapeHtml(
                    worthReason
                  )}</span>`
                : ""
            }
          </div>

          ${
            allPhrases && allPhrases.length
              ? `<div style="margin-top:8px;">
                   <span class="metric-label">Strong / manipulative phrases:</span>
                   <div class="pill-row" style="margin-top:4px;">
                     ${allPhrases
                       .slice(0, 8)
                       .map(p => `<span class="pill">${escapeHtml(p)}</span>`)
                       .join("")}
                   </div>
                 </div>`
              : ""
          }

          ${
            fusionReason
              ? `<div style="margin-top:8px; font-size:0.75rem; color:#9ca3af;">
                   Visual reasoning: ${escapeHtml(fusionReason)}
                 </div>`
              : ""
          }
        </div>
      </div>
    </div>

    <!-- Raw JSON -->
    <details class="json-toggle" style="margin-top:12px;">
      <summary>Raw JSON payload</summary>
      <pre>${jsonPretty}</pre>
    </details>
  `;

  // apply trust color to progress bar fill
  const fillEl = resultArea.querySelector(".progress-fill");
  if (fillEl) {
    if (credColorClass === "red") {
      fillEl.style.background = "linear-gradient(90deg, #ef4444, #fb7185)";
    } else if (credColorClass === "yellow") {
      fillEl.style.background = "linear-gradient(90deg, #f97316, #facc15)";
    } else {
      fillEl.style.background = "linear-gradient(90deg, #22c55e, #4ade80)";
    }
  }
}

// ---------- Main analyze handler ----------
async function runAnalysis() {
  if (!btnAnalyze) return;

  try {
    btnAnalyze.disabled = true;
    btnAnalyze.textContent = "Analyzing…";

    // optimistic placeholder
    if (resultArea) {
      resultArea.innerHTML = `
        <div class="results-placeholder">
          Running OCR, NLP, vision & LLM (if enabled)…
        </div>
      `;
    }

    let imageBase64 = null;
    let imageUrl = null;

    if (imageFileInput && imageFileInput.files && imageFileInput.files[0]) {
      const file = imageFileInput.files[0];
      imageBase64 = await fileToBase64(file);
      renderPreview(URL.createObjectURL(file));
    } else if (imageUrlInput && imageUrlInput.value.trim()) {
      imageUrl = imageUrlInput.value.trim();
      renderPreview(imageUrl);
    } else {
      if (resultArea) {
        resultArea.innerHTML = `
          <div class="results-placeholder">
            Please select an image or paste an image URL before running analysis.
          </div>
        `;
      }
      return;
    }

    const payload = {
      image_base64: imageBase64,
      image_url: imageUrl,
      caption_text: imageUrl ? `Ad URL: ${imageUrl}` : "",
      page_origin: "ChromeExtensionDashboard",
      consent: !!(useLlmCheckbox && useLlmCheckbox.checked),
    };

    const res = await fetch(ANALYZE_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(txt || `HTTP ${res.status}`);
    }

    const data = await res.json();
    const report = data.result || data;

    renderReport(report);
    saveHistory(report, imageUrl, imageBase64);
  } catch (err) {
    console.error(err);
    if (resultArea) {
      resultArea.innerHTML = `
        <div class="results-placeholder" style="color:#fca5a5;">
          Analysis failed: ${escapeHtml(String(err))}
        </div>
      `;
    }
  } finally {
    btnAnalyze.disabled = false;
    btnAnalyze.textContent = "Run Analysis";
  }
}

// ---------- Event wiring ----------
window.addEventListener("DOMContentLoaded", () => {
  checkBackend();
  loadHistory();

  if (imageFileInput) {
    imageFileInput.addEventListener("change", () => {
      if (imageFileInput.files && imageFileInput.files[0]) {
        const fileUrl = URL.createObjectURL(imageFileInput.files[0]);
        renderPreview(fileUrl);
        if (imageUrlInput) imageUrlInput.value = "";
      } else {
        renderPreview(null);
      }
    });
  }

  if (imageUrlInput) {
    imageUrlInput.addEventListener("input", () => {
      const val = imageUrlInput.value.trim();
      if (val) {
        renderPreview(val);
        if (imageFileInput) imageFileInput.value = "";
      } else if (!imageFileInput || !imageFileInput.files.length) {
        renderPreview(null);
      }
    });
  }

  if (btnAnalyze) {
    btnAnalyze.addEventListener("click", () => {
      runAnalysis();
    });
  }
});

// ---------- History ----------
const historyList = document.getElementById("historyList");
const btnClearHistory = document.getElementById("btnClearHistory");

function getStorage() {
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    return "chrome";
  }
  return "local";
}

async function saveHistory(report, imgUrl, imgBase64) {
  const item = {
    id: Date.now(),
    timestamp: new Date().toISOString(),
    report: report,
    imgUrl: imgUrl,
    isBase64: !!imgBase64
  };

  if (getStorage() === "chrome") {
    chrome.storage.local.get(["adaware_history"], (data) => {
      const list = data.adaware_history || [];
      list.unshift(item);
      if (list.length > 10) list.pop();
      chrome.storage.local.set({ adaware_history: list }, () => {
        loadHistory();
      });
    });
  } else {
    const raw = localStorage.getItem("adaware_history");
    const list = raw ? JSON.parse(raw) : [];
    list.unshift(item);
    if (list.length > 10) list.pop();
    localStorage.setItem("adaware_history", JSON.stringify(list));
    loadHistory();
  }
}

function loadHistory() {
  if (!historyList) return;

  if (getStorage() === "chrome") {
    chrome.storage.local.get(["adaware_history"], (data) => {
      renderHistoryList(data.adaware_history || []);
    });
  } else {
    const raw = localStorage.getItem("adaware_history");
    renderHistoryList(raw ? JSON.parse(raw) : []);
  }
}

function renderHistoryList(list) {
  if (!list || list.length === 0) {
    historyList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem; padding: 10px;">No history yet.</div>`;
    return;
  }

  historyList.innerHTML = list.map(item => {
    const r = item.report || {};
    const risk = (r.risk_profile?.risk_level_final || "unknown").toUpperCase();
    const label = r.risk_profile?.label_final || r.label || "Unknown";
    const date = new Date(item.timestamp).toLocaleString();
    
    let color = "#9ca3af";
    if (risk === "LOW") color = "#22c55e";
    if (risk === "MEDIUM") color = "#f97316";
    if (risk === "HIGH") color = "#ef4444";

    return `
      <div class="card" style="padding: 12px; border: 1px solid rgba(148,163,184,0.2);">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
          <span style="font-size:0.7rem; color:var(--text-muted);">${date}</span>
          <span style="font-size:0.7rem; font-weight:bold; color:${color}; border:1px solid ${color}; padding:1px 6px; border-radius:99px;">${risk}</span>
        </div>
        <div style="font-size:0.85rem; font-weight:600; margin-bottom:4px;">${escapeHtml(label)}</div>
        <div style="font-size:0.75rem; color:var(--text-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
           ${item.imgUrl ? escapeHtml(item.imgUrl) : (item.isBase64 ? "Uploaded Image" : "No Image")}
        </div>
      </div>
    `;
  }).join("");
}

if (btnClearHistory) {
  btnClearHistory.addEventListener("click", () => {
    if (getStorage() === "chrome") {
      chrome.storage.local.remove("adaware_history", loadHistory);
    } else {
      localStorage.removeItem("adaware_history");
      loadHistory();
    }
  });
}
