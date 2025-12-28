
// Basic Content Script for AdAware AI Extension
// Now includes: Page-level caching + Debounce + Highlighting

let CACHE = new Map(); // Key: imageSrc, Value: AnalysisResult
let PENDING = new Map(); // Key: imageSrc, Value: Promise

// Debounce helper
function debounce(func, wait) {
  let timeout;
  return function (...args) {
    const context = this;
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(context, args), wait);
  };
}

// Hover listener
document.addEventListener("mouseover", debounce(handleHover, 500));

async function handleHover(e) {
  const target = e.target;
  // Check if image and large enough
  if (target.tagName !== "IMG") return;
  if (target.width < 150 || target.height < 150) return;

  const src = target.src;
  if (!src) return;

  // Check Cache (Success or Error)
  if (CACHE.has(src)) {
    const cached = CACHE.get(src);
    // If it was a recent error (less than 10s ago), skip
    if (cached.error && (Date.now() - cached.timestamp < 10000)) {
      return;
    }
    // If valid result, show it
    if (!cached.error) {
      showOverlay(target, cached);
      return;
    }
    // If old error, we might retry, so proceed...
  }

  // Check Pending Dedupe
  if (PENDING.has(src)) {
    return; // Already fetching
  }

  // Read settings from Chrome Storage
  let settings = { use_llm: false, backend_url: "http://127.0.0.1:8000" };
  try {
    settings = await new Promise((resolve) => {
      chrome.storage.sync.get({
        backend_url: 'http://127.0.0.1:8000',
        use_llm: false
      }, (items) => resolve(items));
    });
  } catch (e) {
    console.warn("Could not read chrome.storage, using defaults.", e);
  }

  showOverlay(target, { loading: true });

  const promise = fetchAnalysis(src, settings);
  PENDING.set(src, promise);

  try {
    const result = await promise;
    CACHE.set(src, result);
    showOverlay(target, result);
  } catch (err) {
    console.error("AdAware Analysis failed", err);
    // Cache the error with timestamp to prevent immediate retry
    CACHE.set(src, { error: err.message, timestamp: Date.now() });
    showOverlay(target, { error: err.message });
  } finally {
    PENDING.delete(src);
  }
}

async function fetchAnalysis(imageSrc, settings) {
  const res = await fetch(`${settings.backend_url}/analyze_hover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_url: imageSrc,
      page_origin: window.location.href,
      use_llm: settings.use_llm
    })
  });
  if (!res.ok) throw new Error("Backend Error");
  return await res.json();
}

// Overlay UI
let overlay = null;

// --- STYLES INJECTION ---
function injectStyles() {
  if (document.getElementById('adaware-styles')) return;
  const style = document.createElement('style');
  style.id = 'adaware-styles';
  style.textContent = `
        #adaware-overlay {
            position: fixed; z-index: 2147483647;
            background: rgba(15, 15, 15, 0.85);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 16px;
            width: 340px;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            color: #ededed;
            box-shadow: 0 10px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.05);
            opacity: 0;
            transform: translateY(10px) scale(0.98);
            transition: opacity 0.2s cubic-bezier(0.2, 0.8, 0.2, 1), transform 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
            pointer-events: none;
        }
        #adaware-overlay.visible {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
        .adjw-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .adjw-title { font-weight: 700; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; display:flex; align-items:center; gap:6px; }
        .adjw-score { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 14px; background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; }
        .adjw-body { font-size: 13px; line-height: 1.5; color: #ccc; }
        .adjw-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
        .adjw-tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1); text-transform:uppercase; }
        .adjw-list { margin: 8px 0 0 0; padding-left: 16px; font-size: 12px; color: #aaa; }
        .adjw-list li { margin-bottom: 4px; }
        .adjw-footer { font-size: 10px; color: #555; margin-top: 12px; display:flex; justify-content:space-between; }
        
        /* Colors */
        .safe { color: #00ff9d; }
        .risk { color: #ff003c; }
        .mod { color: #ffb800; }
        .dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
    `;
  document.head.appendChild(style);
}

function createOverlay() {
  injectStyles();
  let div = document.getElementById("adaware-overlay");
  if (!div) {
    div = document.createElement("div");
    div.id = "adaware-overlay";
    document.body.appendChild(div);
  }
  return div;
}

function showOverlay(targetRect, data) {
  if (!overlay) overlay = createOverlay();

  const rect = targetRect.getBoundingClientRect();
  // Smart positioning (prevent going off-screen)
  let top = rect.top + window.scrollY + 10;
  let left = rect.right + window.scrollX + 10;

  if (rect.right + 340 > window.innerWidth) {
    left = rect.left + window.scrollX - 350; // flip to left
  }

  overlay.style.top = `${top}px`;
  overlay.style.left = `${left}px`;
  overlay.classList.add('visible');

  if (data.loading) {
    overlay.innerHTML = `
        <div class="adjw-body" style="display:flex; align-items:center; gap:10px;">
            <div class="dot" style="background:#00f0ff; box-shadow:0 0 8px #00f0ff; animation: pulse 1s infinite"></div>
            Analyzing content...
        </div>
    `;
    return;
  }

  if (data.error) {
    overlay.innerHTML = `
        <div class="adjw-header" style="border-color:rgba(255,0,60,0.3)">
            <span class="adjw-title risk">Backend Error</span>
        </div>
        <div class="adjw-body">
            Unable to connect to AdAware. Check extension settings.
            <br><small style="opacity:0.6">${data.error}</small>
        </div>
    `;
    return;
  }

  // Success Render
  const scoreVal = (data.risk_score * 100).toFixed(0);
  let labelClass = "mod";
  let labelColor = "#ffb800";

  const labelRaw = (data.final_label || "unknown").toLowerCase();

  if (labelRaw === 'safe') {
    labelClass = "safe";
    labelColor = "#00ff9d";
  } else if (labelRaw.includes('risk') || labelRaw.includes('scam')) {
    labelClass = "risk";
    labelColor = "#ff003c";
  }

  const labelDisplay = labelRaw.replace(/-/g, ' ').toUpperCase();

  // Tags
  let tagsHtml = "";
  if (data.rule_triggers && data.rule_triggers.length) {
    tagsHtml = data.rule_triggers.slice(0, 3).map(r => `<span class="adjw-tag">${r.rule_id}</span>`).join("");
  }

  // Evidence
  let evidenceHtml = "";
  if (data.evidence && data.evidence.risky_phrases && data.evidence.risky_phrases.length > 0) {
    evidenceHtml = `<ul class="adjw-list">` +
      data.evidence.risky_phrases.slice(0, 3).map(p =>
        `<li>"${p.text || p.phrase}" <span style="opacity:0.5">- ${p.reason}</span></li>`
      ).join("") +
      `</ul>`;
  }

  overlay.innerHTML = `
      <div class="adjw-header">
          <span class="adjw-title ${labelClass}">
              <span class="dot" style="background:${labelColor}; box-shadow:0 0 8px ${labelColor}"></span>
              ${labelDisplay}
          </span>
          <span class="adjw-score ${labelClass}">${scoreVal}/100</span>
      </div>
      
      ${tagsHtml ? `<div class="adjw-tags">${tagsHtml}</div>` : ""}
      
      <div class="adjw-body">
          ${data.explanation_text || "Analysis complete. No obvious risks found."}
      </div>
      
      ${evidenceHtml}
      
      <div class="adjw-footer">
          <span>${data.llm_used ? "✦ Enhanced AI" : "⚡ Standard"}</span>
          <span>AdAware</span>
      </div>
  `;
}

// Hide on mouseout
document.addEventListener("mouseout", (e) => {
  if (e.target.tagName === "IMG" && overlay) {
    overlay.classList.remove('visible');
  }
});
