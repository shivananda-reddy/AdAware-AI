
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
document.addEventListener("mouseover", debounce(handleHover, 300));

async function handleHover(e) {
  const target = e.target;
  // Check if image and large enough
  if (target.tagName !== "IMG") return;
  if (target.width < 150 || target.height < 150) return;

  const src = target.src;
  if (!src) return;

  // Check Cache
  if (CACHE.has(src)) {
    showOverlay(target, CACHE.get(src));
    return;
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

function createOverlay() {
  const div = document.createElement("div");
  div.id = "adaware-overlay";
  div.style.cssText = `
        position: fixed; z-index: 9999;
        background: rgba(10, 10, 10, 0.95);
        color: #fff; padding: 16px; border-radius: 8px;
        width: 320px; font-family: sans-serif;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        backdrop-filter: blur(10px); border: 1px solid #333;
        pointer-events: none; opacity: 0; transition: opacity 0.2s;
    `;
  document.body.appendChild(div);
  return div;
}

function showOverlay(targetRect, data) {
  if (!overlay) overlay = createOverlay();

  const rect = targetRect.getBoundingClientRect();
  overlay.style.top = `${rect.top + window.scrollY + 10}px`;
  overlay.style.left = `${rect.right + window.scrollX + 10}px`;
  overlay.style.opacity = "1";

  if (data.loading) {
    overlay.innerHTML = `<div>Scanning ad content...</div>`;
    return;
  }

  if (data.error) {
    overlay.innerHTML = `<div style="color:#f66"><strong>Backend Unreachable</strong><p style="font-size:11px; color:#aaa">Check Backend URL in extension popup settings.</p><small>${data.error}</small></div>`;
    return;
  }

  // Success Render
  const scoreVal = (data.risk_score * 100).toFixed(0);
  const color = data.final_label === 'safe' ? '#0f0' : (data.final_label.includes('risk') || data.final_label.includes('scam') ? '#f00' : 'orange');

  let subcats = "";
  if (data.rule_triggers && data.rule_triggers.length) {
    subcats = data.rule_triggers.map(r => `<span style="background:#333; padding:2px 4px; font-size:10px; border-radius:4px; margin-right:4px">${r.description}</span>`).join("");
  }

  let bullets = "";
  // Evidence highlights could be injected into an HTML view of text
  // For overlay, just list bullet points
  if (data.evidence && data.evidence.risky_phrases) {
    bullets = data.evidence.risky_phrases.map(p => `<li>Found phrase: "${p.phrase}"</li>`).join("");
  }

  overlay.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px">
            <h3 style="margin:0; font-size:16px; color:${color}">${data.final_label.toUpperCase().replace('-', ' ')}</h3>
            <span style="font-weight:bold">${scoreVal}/100</span>
        </div>
        <div style="margin-bottom:8px">${subcats}</div>
        <p style="font-size:12px; line-height:1.4; color:#ccc">${data.explanation_text || "No details available."}</p>
        ${bullets ? `<ul style="font-size:11px; padding-left:16px; margin:4px 0; color:#aaa">${bullets}</ul>` : ""}
        <div style="font-size:10px; color:#666; margin-top:8px">AdAware AI Analysis</div>
    `;
}

// Hide on mouseout
document.addEventListener("mouseout", (e) => {
  if (e.target.tagName === "IMG" && overlay) {
    overlay.style.opacity = "0";
  }
});
