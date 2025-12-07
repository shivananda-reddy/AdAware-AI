// contentScript.js

const API_BASE = "http://127.0.0.1:8000";
const ANALYZE_ENDPOINT = `${API_BASE}/analyze_hover`;

const ANALYSIS_CACHE = new Map();
const HOVER_CACHE_TTL_MS = 15000;
const HOVER_DEBOUNCE_MS = 500;

let hoverEnabled = true;
let hoverConsent = false;
let hoverTimer = null;
let hoverTarget = null;
const hoverCooldownMap = new Map();

// --- Utility: find largest visible image on the page ---
function findMainImage() {
  const imgs = Array.from(document.querySelectorAll("img"));
  let best = null;
  let bestArea = 0;

  for (const img of imgs) {
    if (!img.src) continue;

    const rect = img.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    if (w <= 40 || h <= 40) continue; // skip tiny icons

    // Check visibility
    const style = window.getComputedStyle(img);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") continue;

    const area = w * h;
    if (area > bestArea) {
      bestArea = area;
      best = img;
    }
  }
  return best;
}

// --- Utility: create / update overlay ---
let overlayEl = null;
let overlayAnchor = null; // last hovered image rect to position overlay near

function ensureOverlay() {
  if (overlayEl && overlayEl.isConnected) return overlayEl;

  overlayEl = document.createElement("div");
  overlayEl.id = "adaware-overlay";

  overlayEl.innerHTML = `
    <style>
      #adaware-overlay {
        position: fixed;
        top: 16px;
        left: 16px;
        width: 300px;
        z-index: 2147483647; /* Max z-index */
        font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        animation: adaware-fade-in 0.3s ease-out;
      }
      @keyframes adaware-fade-in {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      #adaware-overlay .card {
        background: rgba(15, 23, 42, 0.98);
        color: #f8fafc;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.3);
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
        padding: 16px;
        font-size: 13px;
        backdrop-filter: blur(16px);
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      /* Header */
      #adaware-overlay .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      #adaware-overlay .brand {
        font-weight: 700;
        font-size: 14px;
        color: #e2e8f0;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      #adaware-overlay .brand span {
        color: #6366f1;
      }
      #adaware-overlay .close-btn {
        background: transparent;
        border: none;
        color: #94a3b8;
        cursor: pointer;
        font-size: 16px;
        padding: 0;
        line-height: 1;
      }
      #adaware-overlay .close-btn:hover { color: #fff; }

      /* Main Stats Grid */
      #adaware-overlay .stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.15);
      }
      #adaware-overlay .stat-item {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      #adaware-overlay .stat-label {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
      }
      #adaware-overlay .stat-value {
        font-weight: 600;
        font-size: 13px;
      }
      
      /* Risk Pill */
      #adaware-overlay .risk-pill {
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: 99px;
        font-size: 11px;
        font-weight: 600;
        border: 1px solid transparent;
      }
      #adaware-overlay .risk-pill.low { background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: rgba(34, 197, 94, 0.3); }
      #adaware-overlay .risk-pill.medium { background: rgba(249, 115, 22, 0.15); color: #fb923c; border-color: rgba(249, 115, 22, 0.3); }
      #adaware-overlay .risk-pill.high { background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
      #adaware-overlay .risk-pill.unknown { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border-color: rgba(148, 163, 184, 0.3); }

      /* Trust Score Bar */
      #adaware-overlay .trust-row {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 11px;
        color: #cbd5e1;
      }
      #adaware-overlay .progress-bg {
        flex: 1;
        height: 6px;
        background: rgba(30, 41, 59, 0.8);
        border-radius: 99px;
        overflow: hidden;
      }
      #adaware-overlay .progress-fill {
        height: 100%;
        width: 0%;
        border-radius: 99px;
        transition: width 0.6s ease-out;
      }

      /* Summary */
      #adaware-overlay .summary {
        font-size: 12px;
        line-height: 1.5;
        color: #cbd5e1;
      }
      #adaware-overlay .summary strong { color: #fff; }

      /* Product Info (Mini) */
      #adaware-overlay .product-mini {
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(30, 41, 59, 0.4);
        padding: 8px;
        border-radius: 8px;
        font-size: 11px;
      }
      #adaware-overlay .product-icon { font-size: 14px; }
      #adaware-overlay .product-details { display: flex; flex-direction: column; }
      #adaware-overlay .product-name { font-weight: 600; color: #e2e8f0; }
      #adaware-overlay .product-price { color: #94a3b8; }

      /* Footer Actions */
      #adaware-overlay .footer {
        margin-top: 4px;
        display: flex;
        justify-content: flex-end;
      }
      #adaware-overlay .btn-dashboard {
        background: linear-gradient(135deg, #4f46e5, #6366f1);
        color: white;
        border: none;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 500;
        cursor: pointer;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        transition: opacity 0.2s;
      }
      #adaware-overlay .btn-dashboard:hover { opacity: 0.9; }
    </style>

    <div class="card">
      <!-- Header -->
      <div class="header">
        <div class="brand">AdAware <span>AI</span></div>
        <button class="close-btn" id="adaware-close">×</button>
      </div>

      <!-- Stats Grid -->
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">Risk Level</span>
          <span class="risk-pill unknown" id="adaware-risk-pill">Analyzing...</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Label</span>
          <span class="stat-value" id="adaware-label">...</span>
        </div>
      </div>

      <!-- Trust Score -->
      <div class="stat-item">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
           <span class="stat-label">Trust Score</span>
           <span class="stat-label" id="adaware-trust-val">0/100</span>
        </div>
        <div class="progress-bg">
          <div class="progress-fill" id="adaware-bar" style="width: 0%; background: #94a3b8;"></div>
        </div>
      </div>

      <!-- Summary -->
      <div class="summary" id="adaware-summary">
        Scanning ad content...
      </div>

      <!-- Product Mini (Hidden by default) -->
      <div class="product-mini" id="adaware-product" style="display:none;">
        <div class="product-icon">🛍️</div>
        <div class="product-details">
          <span class="product-name" id="adaware-prod-name">Unknown Product</span>
          <span class="product-price" id="adaware-prod-price"></span>
        </div>
      </div>

      <!-- Footer -->
      <div class="footer">
        <a href="#" class="btn-dashboard" id="adaware-open-dash">
          Open Full Report ↗
        </a>
      </div>
    </div>
  `;

  document.documentElement.appendChild(overlayEl);

  // If we have an anchor image, position the overlay near its top-right
  positionOverlayNearAnchor();
  
  // Event listeners
  const closeBtn = overlayEl.querySelector("#adaware-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      if (overlayEl && overlayEl.parentNode) {
        overlayEl.parentNode.removeChild(overlayEl);
      }
      overlayEl = null;
      hoverTarget = null;
    });
  }

  const dashBtn = overlayEl.querySelector("#adaware-open-dash");
  if (dashBtn) {
    dashBtn.addEventListener("click", (e) => {
      e.preventDefault();
      try {
        chrome.runtime.sendMessage({ type: "OPEN_DASHBOARD" });
      } catch (err) {
        // ignore if chrome.runtime not available
      }
    });
  }

  return overlayEl;
}

function positionOverlayNearAnchor() {
  if (!overlayEl) return;
  if (!overlayAnchor) return;
  const rect = overlayAnchor.getBoundingClientRect();
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
  let top = rect.top + scrollTop + 8;
  let left = rect.right + scrollLeft + 8;
  // keep on screen
  const maxLeft = scrollLeft + window.innerWidth - 320;
  const maxTop = scrollTop + window.innerHeight - 220;
  if (left > maxLeft) left = rect.left + scrollLeft - 320 - 8;
  if (top > maxTop) top = scrollTop + window.innerHeight - 220 - 8;
  overlayEl.style.top = `${top}px`;
  overlayEl.style.left = `${left}px`;
}

function setOverlayLoading() {
  const root = ensureOverlay();
  root.querySelector("#adaware-risk-pill").className = "risk-pill unknown";
  root.querySelector("#adaware-risk-pill").textContent = "Analyzing...";
  root.querySelector("#adaware-label").textContent = "...";
  root.querySelector("#adaware-trust-val").textContent = "";
  root.querySelector("#adaware-bar").style.width = "30%";
  root.querySelector("#adaware-bar").style.background = "#94a3b8"; // gray
  root.querySelector("#adaware-summary").textContent = "Analyzing image content, text, and trust signals...";
  root.querySelector("#adaware-product").style.display = "none";
}

function setOverlayError(msg) {
  const root = ensureOverlay();
  root.querySelector("#adaware-risk-pill").className = "risk-pill high";
  root.querySelector("#adaware-risk-pill").textContent = "Error";
  root.querySelector("#adaware-summary").textContent = String(msg || "Analysis failed.");
  root.querySelector("#adaware-bar").style.width = "0%";
}

// --- Do analysis with backend ---
async function analyzeImageUrl(imageUrl, consent, options = {}) {
  if (!imageUrl) {
    setOverlayError("No image URL found.");
    return;
  }

  const cacheKey = `${imageUrl}::${consent ? "llm" : "classic"}`;
  const force = options.force === true;

  if (!force && ANALYSIS_CACHE.has(cacheKey)) {
    const cachedReport = ANALYSIS_CACHE.get(cacheKey);
    updateOverlayFromReport(cachedReport);
    return;
  }

  setOverlayLoading();

  const payload = {
    image_base64: null,
    image_url: imageUrl,
    caption_text: "Ad URL: " + imageUrl,
    page_origin: window.location.hostname || "ContentScript",
    consent: !!consent
  };

  try {
    const res = await fetch(ANALYZE_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }

    const data = await res.json();
    const report = data.result || data;
    ANALYSIS_CACHE.set(cacheKey, report);
    if (ANALYSIS_CACHE.size > 30) {
      const oldestKey = ANALYSIS_CACHE.keys().next().value;
      ANALYSIS_CACHE.delete(oldestKey);
    }
    updateOverlayFromReport(report);
  } catch (err) {
    console.error("AdAware analyze error:", err);
    setOverlayError("Failed to reach AdAware backend.");
  }
}

// --- Overlay: fill with report data ---
function updateOverlayFromReport(report) {
  const root = ensureOverlay();

  const riskProfile = report.risk_profile || {};
  const labelFinal = riskProfile.label_final || report.label || "Unknown";
  const riskLevelFinal = (riskProfile.risk_level_final || riskProfile.risk_level_inferred || "unknown").toLowerCase();
  
  const credFinal = typeof riskProfile.credibility_final === "number"
    ? riskProfile.credibility_final
    : Number(report.credibility || 0);
  const credScore = Math.max(0, Math.min(100, Math.round(credFinal)));

  // Summary
  const finalExpl = report.explanation_final || {};
  const shortTakeaway =
    (typeof finalExpl.short_takeaway === "string" && finalExpl.short_takeaway.trim()) ||
    (typeof report.llm_summary === "string" ? report.llm_summary : "Analysis complete.");

  // Product Info
  const pinfo = report.product_info || {};
  const pname = pinfo.product_name || "";
  const pprice = pinfo.detected_price || "";

  // 1. Risk Pill
  const pillEl = root.querySelector("#adaware-risk-pill");
  pillEl.className = `risk-pill ${riskLevelFinal}`;
  pillEl.textContent = riskLevelFinal.toUpperCase();

  // 2. Label
  root.querySelector("#adaware-label").textContent = labelFinal;

  // 3. Trust Score
  root.querySelector("#adaware-trust-val").textContent = `${credScore}/100`;
  const barEl = root.querySelector("#adaware-bar");
  barEl.style.width = `${credScore}%`;
  
  // Color logic
  if (credScore <= 40) {
    barEl.style.background = "linear-gradient(90deg, #ef4444, #fb7185)"; // red
  } else if (credScore <= 70) {
    barEl.style.background = "linear-gradient(90deg, #f97316, #facc15)"; // orange
  } else {
    barEl.style.background = "linear-gradient(90deg, #22c55e, #4ade80)"; // green
  }

  // 4. Summary
  root.querySelector("#adaware-summary").innerHTML = `<strong>Takeaway:</strong> ${shortTakeaway}`;

  // 5. Product (if exists)
  const prodEl = root.querySelector("#adaware-product");
  if (pname) {
    prodEl.style.display = "flex";
    root.querySelector("#adaware-prod-name").textContent = pname;
    root.querySelector("#adaware-prod-price").textContent = pprice ? `Price: ${pprice}` : "";
  } else {
    prodEl.style.display = "none";
  }
}

// --- Message listener from popup & background ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message.type !== "string") return;

  if (message.type === "AD_AWARE_ANALYZE_PAGE") {
    const consent = !!(message.payload && message.payload.consent);
    const mainImg = findMainImage();
    const url = mainImg ? mainImg.src : null;

    if (!url) {
      setOverlayError("Could not find a suitable ad image on this page.");
      sendResponse && sendResponse({ ok: false, error: "No image found" });
      return;
    }

    overlayAnchor = mainImg;
    analyzeImageUrl(url, consent);
    sendResponse && sendResponse({ ok: true });
    return true; // keep channel open for async if needed
  }

  if (message.type === "AD_AWARE_ANALYZE_IMAGE_URL") {
    const payload = message.payload || {};
    const url = payload.imageUrl || null;
    const consent = !!payload.consent;

    if (!url) {
      setOverlayError("No image URL provided.");
      sendResponse && sendResponse({ ok: false, error: "No image URL" });
      return;
    }

    analyzeImageUrl(url, consent);
    sendResponse && sendResponse({ ok: true });
    return true;
  }
});

// --- Hover Feature ---
function initializeHoverPreferences() {
  if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.sync) {
    hoverEnabled = true;
    hoverConsent = false;
    return;
  }

  chrome.storage.sync.get(["adaware_hover_enabled", "adaware_use_llm"], (data) => {
    if (chrome.runtime.lastError) return;
    if (typeof data.adaware_hover_enabled === "boolean") {
      hoverEnabled = data.adaware_hover_enabled;
    }
    if (typeof data.adaware_use_llm === "boolean") {
      hoverConsent = data.adaware_use_llm;
    }
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "sync") return;
    if (Object.prototype.hasOwnProperty.call(changes, "adaware_hover_enabled")) {
      hoverEnabled = !!changes.adaware_hover_enabled.newValue;
    }
    if (Object.prototype.hasOwnProperty.call(changes, "adaware_use_llm")) {
      hoverConsent = !!changes.adaware_use_llm.newValue;
    }
  });
}

initializeHoverPreferences();

function shouldAnalyzeHoverImage(img) {
  if (!img || !img.src) return false;
  const rect = img.getBoundingClientRect();
  if (rect.width < 100 || rect.height < 100) return false;
  const style = window.getComputedStyle(img);
  if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
  return true;
}

function extractImageUrlFromElement(el) {
  if (!el) return null;

  // Prioritize lazy-loading attributes on the element itself
  const lazySrc = el.getAttribute("data-src") || el.getAttribute("data-srcset") || el.getAttribute("srcset");
  if (lazySrc) return lazySrc.split(" ")[0]; // Handle srcset by taking the first URL

  // 1) Direct <img>
  if (el.tagName === "IMG" && el.src) return el.src;

  // 2) Background-image on element
  const style = window.getComputedStyle(el);
  const bg = style.backgroundImage;
  if (bg && bg !== "none") {
    const m = bg.match(/url\(["']?(.*?)["']?\)/);
    if (m && m[1]) return m[1];
  }

  // 3) Look for child <img> (also checking for lazy attributes)
  const childImg = el.querySelector("img");
  if (childImg) {
    const childLazySrc = childImg.getAttribute("data-src") || childImg.getAttribute("data-srcset") || childImg.getAttribute("srcset");
    if (childLazySrc) return childLazySrc.split(" ")[0];
    if (childImg.src) return childImg.src;
  }

  // 4) Search up the DOM for nearest image container
  let parent = el.parentElement;
  for (let i = 0; i < 4 && parent; i++) {
    const pStyle = window.getComputedStyle(parent);
    const pBg = pStyle.backgroundImage;
    if (pBg && pBg !== "none") {
      const pm = pBg.match(/url\(["']?(.*?)["']?\)/);
      if (pm && pm[1]) return pm[1];
    }
    const pImg = parent.querySelector("img");
    if (pImg) {
       const pImgLazy = pImg.getAttribute("data-src") || pImg.getAttribute("data-srcset") || pImg.getAttribute("srcset");
       if (pImgLazy) return pImgLazy.split(" ")[0];
       if (pImg.src) return pImg.src;
    }
    parent = parent.parentElement;
  }
  return null;
}

function scheduleHoverAnalysis(img) {
  if (!hoverEnabled) return;
  if (!shouldAnalyzeHoverImage(img)) return;

  hoverTarget = img;
  overlayAnchor = img;

  if (hoverTimer) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }

  // Show overlay immediately in loading state near the image
  setOverlayLoading();
  positionOverlayNearAnchor();

  hoverTimer = window.setTimeout(() => {
    hoverTimer = null;
    if (!hoverEnabled) return;
    if (!hoverTarget || hoverTarget !== img) return;

    const cacheKey = `${img.src}::${hoverConsent ? "llm" : "classic"}`;
    const now = Date.now();
    const lastSeen = hoverCooldownMap.get(cacheKey) || 0;

    if (now - lastSeen < HOVER_CACHE_TTL_MS) {
      const cachedReport = ANALYSIS_CACHE.get(cacheKey);
      if (cachedReport) {
        updateOverlayFromReport(cachedReport);
      }
      return;
    }

    hoverCooldownMap.set(cacheKey, now);
    console.log("AdAware: hover analyzing", img.src);
    analyzeImageUrl(img.src, hoverConsent);
  }, HOVER_DEBOUNCE_MS);
}

document.addEventListener("mouseover", (event) => {
  if (!hoverEnabled) return;
  const target = event.target;
  if (!target) return;
  let imgEl = null;
  if (target.tagName === "IMG") {
    imgEl = target;
  } else {
    const url = extractImageUrlFromElement(target);
    if (url) {
      // Create a transient Image element wrapper to reuse geometry checks
      const fakeImg = new Image();
      fakeImg.src = url;
      // Try to position near the hovered element itself
      Object.defineProperty(fakeImg, "getBoundingClientRect", { value: () => target.getBoundingClientRect() });
      Object.defineProperty(fakeImg, "tagName", { value: "IMG" });
      imgEl = fakeImg;
      // Keep an anchor to real element for overlay positioning
      overlayAnchor = target;
    }
  }
  if (imgEl) scheduleHoverAnalysis(imgEl);
}, true);

document.addEventListener("mouseout", (event) => {
  if (!hoverTarget) return;

  // 🔹 PATCH: if mouse is leaving the image *into* the overlay, do NOT cancel
  const toEl = event.relatedTarget;
  if (overlayEl && toEl && (toEl === overlayEl || overlayEl.contains(toEl))) {
    // user is moving from image into the AdAware dialog → keep it alive
    return;
  }

  if (event.target === hoverTarget) {
    if (hoverTimer) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }
    hoverTarget = null;
  }
}, true);

window.addEventListener("scroll", () => {
  if (!hoverTarget || !hoverTimer) return;
  const rect = hoverTarget.getBoundingClientRect();
  if (rect.bottom < 0 || rect.top > window.innerHeight) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
    hoverTarget = null;
  }

  // keep overlay positioned near anchor while scrolling
  if (overlayEl && overlayAnchor) {
    positionOverlayNearAnchor();
  }
}, { passive: true });
