// popup.js

const API_BASE = "http://127.0.0.1:8000";

const statusEl = document.getElementById("popupBackendStatus");
const btnAnalyzeThisPage = document.getElementById("btnAnalyzeThisPage");
const btnOpenDashboard = document.getElementById("btnOpenDashboard");
const linkOpenOptions = document.getElementById("openOptionsLink");
const checkboxUseLlm = document.getElementById("popupUseLlm");
const checkboxHover = document.getElementById("popupEnableHover");
const errorEl = document.getElementById("popupError");

// --- Backend status check ---
async function checkBackendFromPopup() {
  if (!statusEl) return;
  try {
    const res = await fetch(`${API_BASE}/docs`, { method: "GET" });
    if (res.ok) {
      statusEl.classList.remove("offline");
      statusEl.classList.add("online");
      statusEl.innerHTML = `<span class="status-dot">●</span><span>Backend online</span>`;
    } else {
      throw new Error("HTTP " + res.status);
    }
  } catch (e) {
    statusEl.classList.remove("online");
    statusEl.classList.add("offline");
    statusEl.innerHTML = `<span class="status-dot">●</span><span>Backend offline</span>`;
  }
}

// --- Storage helpers ---
function loadPreferences() {
  if (!chrome.storage || !chrome.storage.sync) return;
  chrome.storage.sync.get(["adaware_use_llm", "adaware_hover_enabled"], (data) => {
    if (chrome.runtime.lastError) return;

    if (checkboxUseLlm) {
      if (typeof data.adaware_use_llm === "boolean") {
        checkboxUseLlm.checked = data.adaware_use_llm;
      } else {
        chrome.storage.sync.set({ adaware_use_llm: checkboxUseLlm.checked });
      }
    }

    if (checkboxHover) {
      const enabled = typeof data.adaware_hover_enabled === "boolean" ? data.adaware_hover_enabled : true;
      checkboxHover.checked = enabled;
      if (typeof data.adaware_hover_enabled !== "boolean") {
        chrome.storage.sync.set({ adaware_hover_enabled: enabled });
      }
    }
  });
}

function saveLlmPreference(value) {
  if (!chrome.storage || !chrome.storage.sync) return;
  chrome.storage.sync.set({ adaware_use_llm: !!value });
}

function saveHoverPreference(value) {
  if (!chrome.storage || !chrome.storage.sync) return;
  chrome.storage.sync.set({ adaware_hover_enabled: !!value });
}

// --- UI actions ---

function openOptionsPage() {
  if (chrome.runtime && chrome.runtime.openOptionsPage) {
    chrome.runtime.openOptionsPage();
  } else {
    // Fallback: try to open dashboard.html directly
    chrome.tabs.create({ url: "dashboard.html" });
  }
}

// Ask the content script to capture the current ad / image
function analyzeThisPage() {
  hideError();
  btnAnalyzeThisPage.disabled = true;
  btnAnalyzeThisPage.textContent = "Sending to backend...";

  const consent = !!(checkboxUseLlm && checkboxUseLlm.checked);

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (!tab || !tab.id) {
      showError("No active tab found.");
      resetAnalyzeButton();
      return;
    }

    chrome.tabs.sendMessage(
      tab.id,
      {
        type: "AD_AWARE_ANALYZE_PAGE",
        payload: {
          consent
        }
      },
      (response) => {
        if (chrome.runtime.lastError) {
          // Likely no content script on this page yet
          showError("Content script not available on this page.");
          resetAnalyzeButton();
          return;
        }
        if (!response || !response.ok) {
          showError(response && response.error ? response.error : "Analysis failed.");
        }
        resetAnalyzeButton();
      }
    );
  });
}

function resetAnalyzeButton() {
  btnAnalyzeThisPage.disabled = false;
  btnAnalyzeThisPage.textContent = "Analyze selected ad on this page";
}

function showError(msg) {
  if (!errorEl) return;
  errorEl.textContent = String(msg);
  errorEl.style.display = "block";
}

function hideError() {
  if (!errorEl) return;
  errorEl.textContent = "";
  errorEl.style.display = "none";
}

// --- Event wiring ---
document.addEventListener("DOMContentLoaded", () => {
  checkBackendFromPopup();
  loadPreferences();

  if (checkboxUseLlm) {
    checkboxUseLlm.addEventListener("change", () => {
      saveLlmPreference(checkboxUseLlm.checked);
    });
  }

  if (checkboxHover) {
    checkboxHover.addEventListener("change", () => {
      saveHoverPreference(checkboxHover.checked);
    });
  }

  if (btnOpenDashboard) {
    btnOpenDashboard.addEventListener("click", () => {
      openOptionsPage();
    });
  }

  if (linkOpenOptions) {
    linkOpenOptions.addEventListener("click", (e) => {
      e.preventDefault();
      openOptionsPage();
    });
  }

  if (btnAnalyzeThisPage) {
    btnAnalyzeThisPage.addEventListener("click", () => {
      analyzeThisPage();
    });
  }
});
