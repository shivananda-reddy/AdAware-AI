const API_BASE = "http://127.0.0.1:8000";
const ANALYZE_ENDPOINT = API_BASE + "/analyze_hover";

const backendStatusEl = document.getElementById("backendStatus");
const imageFileInput = document.getElementById("imageFile");
const imageUrlInput = document.getElementById("imageUrl");
const useLlmCheckbox = document.getElementById("useLlm");
const btnAnalyze = document.getElementById("btnAnalyze");
const previewInner = document.getElementById("previewInner");
const resultArea = document.getElementById("resultArea");

// --- 1. Backend Check ---
async function checkBackend() {
    try {
        const res = await fetch(API_BASE + "/docs", { method: "GET" });
        if (res.ok) {
            backendStatusEl.innerHTML = '<span class="status-dot"></span> System Online';
            backendStatusEl.className = 'status-capsule online';
        } else {
            throw new Error("Backend error");
        }
    } catch {
        backendStatusEl.innerHTML = '<span class="status-dot"></span> Backend Offline';
        backendStatusEl.className = 'status-capsule offline';
    }
}

// --- 2. Image Helpers ---
async function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function renderPreview(imageSrc) {
    if (!imageSrc) {
        previewInner.innerHTML = `
    <div class="flex-col flex-center text-muted">
       <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.3; margin-bottom:12px;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
       <span class="text-xs">No image selected</span>
    </div>`;
        return;
    }
    previewInner.innerHTML = `<img src="${imageSrc}" alt="Ad preview" />`;
}

// Handle Drag & Drop / File Input visuals
const dropZone = document.querySelector('.upload-card');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});
function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
});
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
});

dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files[0]) {
        imageFileInput.files = files;
        renderPreview(URL.createObjectURL(files[0]));
    }
});

imageFileInput.addEventListener('change', () => {
    if (imageFileInput.files[0]) renderPreview(URL.createObjectURL(imageFileInput.files[0]));
});

// --- 3. Render Report (Bento Grid) ---
function renderReport(report) {
    // --- Helpers ---
    const safe = (val, def = "N/A") => (val !== undefined && val !== null && val !== "") ? val : def;
    const listToTags = (list, cls = "tag") => (list || []).map(x => `<span class="${cls}">${x}</span>`).join('');

    // Risk Color Logic
    const riskColor = (l) => {
        l = (l || "").toLowerCase();
        if (l.includes("low") || l.includes("safe") || l.includes("minimal")) return "green";
        if (l.includes("medium") || l.includes("moderate")) return "yellow";
        return "red";
    };

    // Score Logic
    const getScoreClass = (s) => s > 75 ? 'good' : s > 40 ? 'info' : 'bad';

    // --- Data Extraction ---
    const label = report.label_llm || report.label || "Unknown";
    const credScore = Math.round(report.credibility_llm !== undefined ? report.credibility_llm : (report.credibility || 0));
    const riskLevel = report.trust?.risk_level_llm || "Unknown";
    const summary = report.llm_summary || report.explanation?.short_takeaway || "No summary available.";

    const prod = report.product_info || {};
    const vision = report.vision || {};
    const visionLLM = vision.llm || {};
    const imgQual = report.image_quality || {};
    const nlp = report.nlp || {};
    const nlpLLM = nlp.llm || {};
    const trust = report.trust || {};
    const fusion = report.fusion_llm || {};
    const valJudge = report.value_judgement || {};
    const ocr = report.ocr_text_llm || report.ocr_text || "";

    // --- HTML Construction ---
    resultArea.innerHTML = `
  <div class="bento-grid">
    
    <!-- 1. Hero Summary (Span 4) -->
    <div class="glass-card summary-hero col-span-4" style="position:relative; min-height:220px; justify-content:center;">
      <!-- Action Buttons -->
      <div style="position:absolute; top:24px; right:24px; display:flex; gap:12px;">
         <button class="btn-ghost" onclick="window.print()" title="Print / Save PDF">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
         </button>
      </div>

      <div class="flex-between" style="align-items: flex-start; margin-bottom: 20px;">
         <div class="flex-col">
           <div class="text-xs uppercase" style="color:var(--accent-primary); letter-spacing:0.15em; font-weight:800; margin-bottom:8px;">Detection Result</div>
           <h2 class="metric-big" style="background: linear-gradient(to right, #fff, #aaa); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${label}</h2>
         </div>
         
         <div class="flex-col" style="align-items:flex-end;">
           <span class="tag ${riskColor(riskLevel) === 'red' ? 'red' : ''}" style="border-color: currentColor; color: var(--${riskColor(riskLevel)}); font-weight:700;">
              ${riskLevel} Risk
           </span>
           <div class="flex-center gap-4 mt-4">
              <div class="flex-col" style="align-items:flex-end;">
                <span class="text-xs text-muted">Trustworthiness</span>
                <span style="font-size:1.5rem; font-weight:800;">${credScore}/100</span>
              </div>
              <div class="score-circle ${getScoreClass(credScore)}">
                ${credScore}
              </div>
           </div>
         </div>
      </div>
      
      <div class="summary-content" style="border-top:1px solid rgba(255,255,255,0.05); padding-top:20px;">
        ${summary}
      </div>
      
      ${report.ad_hash ? `<div class="text-xs font-mono text-muted mt-4 opacity-50">ID: ${report.ad_hash}</div>` : ''}
    </div>

    <!-- 2. Product Intelligence -->
    <div class="glass-card col-span-2">
      <div class="section-label">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"></path><line x1="16" y1="8" x2="2" y2="22"></line><line x1="17.5" y1="15" x2="9" y2="15"></line></svg>
        Product Context
      </div>
      <div class="flex-col gap-2" style="flex:1;">
        <div class="flex-between glass-panel">
          <span class="text-xs text-muted">Detected Product</span>
          <span class="text-sm font-bold">${safe(prod.product_name)}</span>
        </div>
        <div class="flex-between glass-panel">
          <span class="text-xs text-muted">Brand Entity</span>
          <span class="text-sm font-bold">${safe(prod.brand_name)}</span>
        </div>
        <div class="flex-between glass-panel">
          <span class="text-xs text-muted">Category</span>
          <span class="text-sm font-bold">${safe(prod.category)}</span>
        </div>
        <div class="flex-between glass-panel" style="border-color:rgba(0,255,157,0.2);">
          <span class="text-xs text-muted">Price Analysis</span>
          <span class="text-sm font-bold" style="color:var(--success);">${safe(prod.detected_price)}</span>
        </div>
        
        ${valJudge.worth_it ? `
        <div class="mt-auto glass-panel" style="background:rgba(255,255,255,0.03);">
           <div class="text-xs uppercase text-muted mb-2">Value Verdict</div>
           <div class="font-bold text-main mb-1">${valJudge.worth_it}</div>
           <div class="text-xs text-muted" style="line-height:1.4;">${safe(valJudge.reason)}</div>
        </div>
        ` : ''}
      </div>
    </div>

    <!-- 3. Forensics & Trust -->
    <div class="glass-card col-span-2">
      <div class="section-label">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
        Safety & Forensics
      </div>
      
      <div class="flex-col gap-2" style="flex:1;">
        <div class="grid grid-cols-2 gap-2" style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
           <div class="glass-panel text-center">
              <div class="text-xs text-muted mb-1">Authenticity</div>
              <div class="font-bold text-sm">${safe(trust.ad_authenticity)}</div>
           </div>
           <div class="glass-panel text-center">
              <div class="text-xs text-muted mb-1">Domain Trust</div>
              <div class="font-bold text-sm">${safe(trust.url_trust)}</div>
           </div>
        </div>
        
        ${(trust.risk_signals && trust.risk_signals.length) ? `
          <div class="mt-4">
            <div class="text-xs uppercase text-muted mb-2" style="color:var(--danger);">Detected Risks</div>
            <div class="glass-panel" style="border-color:rgba(255,0,60,0.2); background:rgba(255,0,60,0.05);">
              <ul class="text-xs text-muted" style="padding-left:16px; line-height:1.6;">
                ${(trust.risk_signals || []).map(x => `<li>${x}</li>`).join('')}
              </ul>
            </div>
          </div>
        ` : ''}

        ${(nlpLLM.claims && nlpLLM.claims.length) ? `
          <div class="mt-auto">
            <div class="text-xs uppercase text-muted mb-2">Key Claims</div>
            <ul class="text-xs text-muted" style="padding-left:16px; line-height:1.6;">
              ${(nlpLLM.claims.slice(0, 3)).map(x => `<li>${x}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
      </div>
    </div>

    <!-- 4. Visual Analysis -->
    <div class="glass-card col-span-2">
      <div class="section-label">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
        Visual Diagnostics
      </div>
      
      <div class="flex-col gap-2" style="flex:1;">
         <div class="flex-between glass-panel">
            <span class="text-xs text-muted">Quality Score</span>
            <span class="text-sm font-bold">${Math.round(imgQual.blur_score || 0)} <span class="text-muted font-normal">(${imgQual.is_blurry ? "Blurry" : "Sharp"})</span></span>
         </div>
         <div class="flex-between glass-panel">
            <span class="text-xs text-muted">Consistency</span>
            <span class="text-sm font-bold">${safe(fusion.overall_consistency, "N/A")}</span>
         </div>

         <div class="mt-4">
            <div class="text-xs uppercase text-muted mb-2">Scene Description</div>
            <div class="text-xs text-muted" style="line-height:1.5;">${safe(vision.visual_description, "No description generated.")}</div>
         </div>

         ${(visionLLM.suspicious_visual_cues && visionLLM.suspicious_visual_cues.length) ? `
           <div class="mt-auto">
              <div class="text-xs uppercase text-muted mb-2" style="color:var(--warning);">Suspicious Visuals</div>
              <div class="flex-wrap gap-2" style="display:flex;">${listToTags(visionLLM.suspicious_visual_cues, "tag red")}</div>
           </div>
         ` : ''}
      </div>
    </div>

    <!-- 5. Deep Dive Details -->
    <div class="glass-card col-span-2">
       <div class="section-label">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
         Deep Dive & Semantics
       </div>
        
        <div class="flex-col gap-4" style="flex:1;">
            <div>
               <div class="text-xs uppercase text-muted mb-2">Psychological Triggers</div>
               <div class="grid grid-cols-2 gap-2" style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                  <div class="glass-panel">
                     <div class="text-xs text-muted">Sentiment</div>
                     <div class="font-bold text-sm">${safe(nlp.sentiment?.label)}</div>
                  </div>
                  <div class="glass-panel">
                     <div class="text-xs text-muted">Urgency</div>
                     <div class="font-bold text-sm">${safe(nlpLLM.call_to_action_strength)}</div>
                  </div>
               </div>
               
               ${(nlpLLM.manipulative_phrases && nlpLLM.manipulative_phrases.length) ? `
                 <div class="mt-2 text-xs text-muted">
                    Detected manipulative phrasing:
                    <div class="flex-wrap gap-1 mt-1" style="display:flex;">${listToTags(nlpLLM.manipulative_phrases)}</div>
                 </div>
               ` : ''}
            </div>

            <div>
               <div class="text-xs uppercase text-muted mb-2">Object Detection</div>
               <div class="flex-wrap gap-1" style="display:flex;">
                  ${listToTags(vision.objects)}
               </div>
            </div>

            <div class="mt-auto">
               <div class="text-xs uppercase text-muted mb-2">OCR Extraction</div>
               <div class="glass-panel text-xs text-muted font-mono" style="max-height:80px; overflow-y:auto; white-space:pre-wrap;">${ocr || "No text detected."}</div>
            </div>
        </div>
    </div>

  </div>

  <!-- Raw JSON -->
  <div class="glass-card json-container">
     <details>
       <summary class="text-xs uppercase font-bold" style="color:var(--text-muted); cursor:pointer;">View Raw Analysis Payload</summary>
       <pre class="mt-4">${JSON.stringify(report, null, 2)}</pre>
     </details>
  </div>
`;
}

// --- 4. Main Execution ---
btnAnalyze.addEventListener("click", async () => {
    btnAnalyze.disabled = true;
    btnAnalyze.innerHTML = `<span class="status-dot" style="background:var(--accent-primary); box-shadow:0 0 10px var(--accent-primary); animation:pulse 1s infinite"></span> Processing...`;

    // Loading State
    resultArea.innerHTML = `
  <div class="glass-card flex-center" style="height:300px; color:var(--text-muted);">
     <div class="flex-col flex-center gap-4">
        <div style="width:50px; height:50px; border:3px solid rgba(255,255,255,0.1); border-top-color:var(--accent-primary); border-radius:50%; animation: spin 0.8s linear infinite;"></div>
        <div class="text-sm uppercase" style="letter-spacing:0.1em;">Analyzing Media...</div>
     </div>
  </div>
  <style>@keyframes spin { 100% { transform: rotate(360deg); } } @keyframes pulse { 50% { opacity:0.5; } }</style>
`;

    try {
        let imageBase64 = null;
        let imageUrl = null;

        if (imageFileInput.files[0]) {
            imageBase64 = await fileToBase64(imageFileInput.files[0]);
        } else if (imageUrlInput.value.trim()) {
            imageUrl = imageUrlInput.value.trim();
        } else {
            renderPreview(null);
        }

        const payload = {
            image_base64: imageBase64,
            image_url: imageUrl,
            caption_text: imageUrl ? "Ad URL: " + imageUrl : "",
            page_origin: "WebDashboard",
            consent: !!useLlmCheckbox.checked
        };

        const res = await fetch(ANALYZE_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error(await res.text());

        const data = await res.json();
        renderReport(data.result || data);

    } catch (err) {
        console.error(err);
        resultArea.innerHTML = `
    <div class="glass-card center-text" style="border-color:var(--danger); text-align:center;">
      <div class="section-label" style="justify-content:center; color:var(--danger);">Analysis Failed</div>
      <p class="text-sm text-muted">${String(err)}</p>
      <button onclick="location.reload()" class="btn-analyze" style="width:auto; margin:20px auto; background:var(--card-bg); border:1px solid var(--card-border); color:var(--text-main);">Try Again</button>
    </div>
  `;
    } finally {
        btnAnalyze.disabled = false;
        btnAnalyze.innerHTML = `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
    Run Diagnostics
  `;
    }
});

checkBackend();