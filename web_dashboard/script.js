// dashboard.js (mapped to script.js for web dashboard)

const API_BASE = "http://127.0.0.1:8000";
const ANALYZE_ENDPOINT = `${API_BASE}/analyze_hover`;
const EXPORT_ENDPOINT = `${API_BASE}/api/v1/export_pdf`;

// DOM references
const backendStatusEl = document.getElementById("backendStatus");
const imageFileInput = document.getElementById("imageFile");
const imageUrlInput = document.getElementById("imageUrl");
const useLlmCheckbox = document.getElementById("useLlm");
const btnAnalyze = document.getElementById("btnAnalyze");
const btnDownloadPdf = document.getElementById("btnDownloadPdf");
const previewInner = document.getElementById("previewInner");
const resultArea = document.getElementById("resultArea");
let lastReport = null;
let lastImageUrl = null;
let lastImageBase64 = null;

// --- Optional: sync LLM toggle with extension popup/background (if running as extension) ---
function hasChromeStorage() {
  try {
    return typeof chrome !== "undefined" && chrome.storage && chrome.storage.sync;
  } catch {
    return false;
  }
}

// ---------- Backend status ----------
async function checkBackend() {
  if (!backendStatusEl) return;
  try {
    const res = await fetch(`${API_BASE}/health`, { method: "GET" });
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
  // Use a unique ID for the image to style it or debug it easily
  const imgId = "preview-" + Date.now();
  previewInner.innerHTML = `<img id="${imgId}" src="${src}" alt="Ad preview" class="preview-img">`;

  // Attach error handler immediately
  const img = document.getElementById(imgId);
  if (img) {
    img.onerror = () => {
      console.error("Preview image failed to load:", src);
      previewInner.innerHTML = `<div class="preview-placeholder" style="color:#f87171">Failed to load preview image</div>`;
    };
    // Keep object-fit contain
    img.style.objectFit = "contain";
    img.style.width = "100%";
    img.style.height = "100%";
  }
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
  if (l === "low") return `<span class="pill green">Low risk</span>`;
  if (l === "medium") return `<span class="pill yellow">Medium risk</span>`;
  if (l === "high") return `<span class="pill red">High risk</span>`;
  return `<span class="pill">Risk: unknown</span>`;
}

function trustPill(auth) {
  const a = (auth || "").toLowerCase();
  if (!a) return `<span class="pill yellow">Authenticity: unknown</span>`;
  if (a.includes("high")) return `<span class="pill green">Likely authentic</span>`;
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

  // Schema Adapter: Handle both nested (legacy/extension) and flat (new backend) schemas
  const riskProfile = report.risk_profile || {};
  const explanationRef = report.explanation_final || {};

  // 1. Label & Risk
  // Backend returns "final_label" (enum), Extension used "risk_profile.label_final"
  // formatting label: replace - with space
  const rawLabel = report.final_label || riskProfile.label_final || report.label || "Unknown label";
  const labelFinal = rawLabel.replace(/-/g, ' ');

  let riskLevelFinal =
    report.risk_level || // if added to backend
    riskProfile.risk_level_final ||
    riskProfile.risk_level_inferred;

  if (!riskLevelFinal && rawLabel) {
    if (rawLabel.includes("low") || rawLabel.includes("safe")) riskLevelFinal = "low";
    else if (rawLabel.includes("moderate") || rawLabel.includes("medium")) riskLevelFinal = "medium";
    else if (rawLabel.includes("high") || rawLabel.includes("scam")) riskLevelFinal = "high";
    else riskLevelFinal = "unknown";
  }
  riskLevelFinal = riskLevelFinal || "unknown";

  // 2. Credibility / Legitimacy Score
  // New backend uses 'legitimacy_score' (0..1, high=good)
  // Fallback to old (1 - risk_score)
  let credScore = 0;
  if (typeof report.legitimacy_score === "number") {
    credScore = Math.round(report.legitimacy_score * 100);
  } else if (typeof report.risk_score === "number") {
    credScore = Math.round((1.0 - report.risk_score) * 100);
  } else {
    credScore = 50; // default unknown
  }
  credScore = Math.max(0, Math.min(100, credScore));

  const healthAdvisories = report.health_advisory || [];
  const hasHealthWarnings = healthAdvisories.length > 0;

  // 3. Confidence
  const confModel = typeof report.confidence === "number"
    ? `${(report.confidence * 100).toFixed(1)}%`
    : "N/A";

  // 4. Summary Text
  const summaryText =
    report.explanation_text ||
    (typeof report.llm_summary === "string" && report.llm_summary.trim()) ||
    (typeof explanationRef.explanation_text === "string" && explanationRef.explanation_text.trim()) ||
    "Analysis complete, but no text summary was generated.";

  // 5. Bullets (Evidence)
  // Backend returns "evidence" object with "risky_phrases". Extension used "bullets" array.
  let bullets = [];
  if (report.evidence && Array.isArray(report.evidence.risky_phrases)) {
    bullets = report.evidence.risky_phrases.map(p => `"${p.text}" (${p.reason})`);
  }

  // 6. Product Info
  const pinfo = report.product_info || {};
  const pname = pinfo.product_name || "Unknown product";
  const brand = pinfo.brand_name || (report.brand_entities && report.brand_entities[0]) || "Unknown brand";
  const category = pinfo.category || "Unclassified";

  // Price Logic: Honest Display
  let priceDisplay = "Not detected";
  let priceClass = "muted";
  let priceTooltip = "No price information found in image";
  
  if (pinfo.detected_price && pinfo.detected_price !== "Not found" && pinfo.detected_price !== "Not detected") {
    priceDisplay = pinfo.detected_price;
    priceClass = "text-white";
    priceTooltip = `Detected in image: ${pinfo.detected_price}`;
  } else if (pinfo.formatted_price && pinfo.formatted_price !== "Not found") {
    priceDisplay = `~${pinfo.formatted_price}`;
    priceClass = "text-yellow";
    priceTooltip = `Estimated range from catalog: ${pinfo.formatted_price}`;
  }

  // 7. Trust & Risk signals
  // Backend "source_reputation" -> Extension "ad_authenticity" / "url_trust"
  const rep = report.source_reputation || {};
  const adAuth = rep.flags && rep.flags.length > 0 ? "Suspicious" : "Likely authentic";
  const urlTrust = rep.domain ? `${rep.domain} (${rep.domain_age_days || '?'} days)` : "";

  // Backend "subcategories" -> Risk Signals
  const riskSignals = report.subcategories || [];

  // 8. Fusion / Image Stats
  // Handle Null/Unavailable explicitly
  let imgSimDisplay = "Unavailable";
  let imgSimClass = "muted";
  let imgSimTooltip = "CLIP model not loaded";

  if (typeof report.image_text_similarity === "number") {
    imgSimDisplay = report.image_text_similarity.toFixed(2);
    imgSimClass = "text-white";
    imgSimTooltip = `Similarity score: ${imgSimDisplay}`;
  } else if (report.image_text_similarity === null) {
    imgSimDisplay = "Unavailable";
    imgSimClass = "muted";
    imgSimTooltip = "Image-text similarity unavailable (CLIP model not loaded)";
  }

  const fusionScore = "N/A";
  const fusionLabel = "N/A";

  const imgQuality = report.image_quality || {};
  const blurScore = typeof imgQuality.blur_score === "number" ? imgQuality.blur_score.toFixed(1) : "N/A";
  const isBlurry = false;

  // Template Compatibility: Define missing vars used in HTML
  const credClassic = null;
  const credLlm = null;
  const fusionReason = "";
  const allPhrases = [];

  // Credibility color for progress
  let credColorClass = "green";
  if (credScore <= 40) credColorClass = "red";
  else if (credScore <= 70) credColorClass = "yellow";

  // Persuasion / Advice
  const worthIt = "Unknown"; // Not in new AnalysisResult yet
  const worthReason = "";
  const ctaStrength = report.sentiment || "neutral";
  
  // Category source (not sent by backend currently, so leave undefined for optional display)
  const category_source = undefined;

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

        ${hasHealthWarnings ? `
        <div style="margin-top:12px; padding:10px; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:8px;">
          <div style="font-size:0.75rem; font-weight:600; color:#fca5a5; margin-bottom:4px; text-transform:uppercase;">Health Advisories</div>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            ${healthAdvisories.map(h => `<span class="pill red" style="background:rgba(239,68,68,0.2); border-color:rgba(239,68,68,0.5); color:#fecaca;">${escapeHtml(h)}</span>`).join("")}
          </div>
        </div>
        ` : ""}

        ${bullets && bullets.length
      ? `
          <ul style="margin-top:10px; padding-left:18px; font-size:0.8rem; color:#d1d5db;">
            ${bullets
        .slice(0, 6)
        .map(b => `<li>${escapeHtml(b)}</li>`)
        .join("")}
          </ul>`
      : ""
    }

        ${report.ad_hash
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

        ${credClassic !== null || credLlm !== null
      ? `<div style="margin-top:4px; font-size:0.7rem; color:#9ca3af;">
                 ${credLlm !== null
        ? `LLM: ${Math.round(credLlm)}`
        : ""
      }
                 ${credClassic !== null
        ? `${credLlm !== null ? " • " : ""}Classic: ${Math.round(
          credClassic
        )}`
        : ""
      }
               </div>`
      : ""
    }

        <div class="metric-row">
          <span class="metric-label">Model confidence (computed)</span>
          <span class="metric-value">${confModel}</ title="${imgSimTooltip}"span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Image-text similarity</span>
          <span class="metric-value ${imgSimClass}">${imgSimDisplay}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Fusion consistency</span>
          <span class="metric-value">N/A</span>
        </div>

        <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
          ${riskSignals.map(s => `<span class="pill red">${escapeHtml(s)}</span>`).join("")}
          ${adAuth === "Suspicious" ? `<span class="pill red">Suspicious Source</span>` : ""}
          ${urlTrust ? `<span class="pill gray">URL trust: ${escapeHtml(urlTrust)}</span>` : ""}
        </div>

        <div class="metric-row" style="margin-top:12px;">
          <span class="metric-label">Image blur score</span>
          <span class="metric-value">${blurScore}</span>
        </div>

        <div class="section-heading" style="margin-top:16px;">
          <span class="dot"></span>
          Product & Pricing
        </div>
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
          <span class="metric-value">${escapeHtml(category)}${category !== "Unclassified" && category_source ? ` (${category_source})` : ""}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Price</span>
          <span class="metric-value ${priceClass}" title="${priceTooltip}">${escapeHtml(priceDisplay)}</span>
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
            ${worthReason
      ? `<span style="display:block; margin-top:3px; color:#9ca3af;">${escapeHtml(
        worthReason
      )}</span>`
      : ""
    }
          </div>

          ${allPhrases && allPhrases.length
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

          ${fusionReason
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
      ad_text: imageUrl ? `Ad URL: ${imageUrl}` : "",
      page_url: "WebDashboard", // Changed from ExtensionDashboard
      use_llm: !!(useLlmCheckbox && useLlmCheckbox.checked),
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
    // API returns AnalysisResult directly, so data is the report
    const report = data;

    renderReport(report);
    saveHistory(report, imageUrl, imageBase64);
    lastReport = report;
    lastImageUrl = imageUrl;
    lastImageBase64 = imageBase64;
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

  // Prevent accidental page navigation when dragging files or images onto the page
  [document, window].forEach(el => {
    el.addEventListener("dragover", (e) => e.preventDefault());
    el.addEventListener("drop", (e) => e.preventDefault());
  });

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

  if (btnDownloadPdf) {
    btnDownloadPdf.addEventListener("click", () => {
      downloadPdf();
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
    if (list.length > 20) list.pop(); // Increased limit for web
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
    // Handle old report format or new AnalysisResult
    const r = item.report || {};
    // Try new schema fields first, fallback to old
    const risk = (r.final_label || r.label || "unknown").toUpperCase();
    const label = (r.final_label || r.label || "Unknown").replace(/-/g, ' ');
    const date = new Date(item.timestamp).toLocaleString();

    let color = "#9ca3af";
    if (risk.includes("LOW") || risk.includes("SAFE")) color = "#22c55e";
    else if (risk.includes("MEDIUM") || risk.includes("MODERATE")) color = "#f97316";
    else if (risk.includes("HIGH") || risk.includes("SCAM")) color = "#ef4444";

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

// ---------- PDF Export ----------
async function downloadPdf() {
  try {
    if (!lastReport) {
      alert("Run an analysis first, then export the PDF.");
      return;
    }

    // Build payload using last analysis and image source
    const payload = {
      analysis: lastReport,
      image_url: lastImageUrl || null,
      image_base64: lastImageBase64 || null,
      page_url: "WebDashboard",
      use_llm: !!(useLlmCheckbox && useLlmCheckbox.checked),
    };

    const res = await fetch(EXPORT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(txt || `HTTP ${res.status}`);
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const label = (lastReport.final_label || "report").replace(/\s+/g, "_");
    const ts = (lastReport.timestamp || "").replace(/[:\s]/g, "_");
    a.href = url;
    a.download = `adaware_report_${label}_${ts}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("PDF export failed:", err);
    alert("PDF export failed. Ensure backend is running and reportlab is installed.");
  }
}