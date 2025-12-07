// background.js

const CONTEXT_MENU_ID = "adaware-analyze-image";

// Create context menu on install / update
chrome.runtime.onInstalled.addListener(() => {
  // Use a callback to suppress "checked runtime.lastError" warnings if it already exists
  chrome.contextMenus.create({
    id: CONTEXT_MENU_ID,
    title: "Analyze image with AdAware AI",
    contexts: ["image"]
  }, () => {
    if (chrome.runtime.lastError) {
      // Ignore error if item already exists
      console.log("Context menu warning:", chrome.runtime.lastError.message);
    }
  });

  if (chrome.storage && chrome.storage.sync) {
    chrome.storage.sync.get(["adaware_hover_enabled"], (data) => {
      if (chrome.runtime.lastError) return;
      if (typeof data.adaware_hover_enabled !== "boolean") {
        chrome.storage.sync.set({ adaware_hover_enabled: true });
      }
    });
  }
});

// Ensure contextMenus API is available
if (chrome.contextMenus && chrome.contextMenus.onClicked) {
  // When user clicks the context menu on an image
  chrome.contextMenus.onClicked.addListener((info, tab) => {
    try {
      if (info.menuItemId !== CONTEXT_MENU_ID) return;
      if (!tab || !tab.id) return;

      const imageUrl = info.srcUrl || null;
      if (!imageUrl) return;

      // Helper to proceed with analysis
      const proceed = (consent) => {
        chrome.tabs.sendMessage(
          tab.id,
          {
            type: "AD_AWARE_ANALYZE_IMAGE_URL",
            payload: {
              imageUrl,
              consent
            }
          },
          () => {
            // ignore response; contentScript handles UI
            if (chrome.runtime.lastError) {
              console.warn("AdAware: content script not available:", chrome.runtime.lastError.message);
            }
          }
        );
      };

      // Read LLM preference from sync storage (same key as popup)
      if (chrome.storage && chrome.storage.sync) {
        chrome.storage.sync.get(["adaware_use_llm"], (data) => {
          if (chrome.runtime.lastError) {
            console.warn("Storage error:", chrome.runtime.lastError.message);
            proceed(false); // Fallback to false
            return;
          }
          const consent = !!(data && data.adaware_use_llm);
          proceed(consent);
        });
      } else {
        // Fallback if storage not available
        proceed(false);
      }
    } catch (err) {
      console.error("Error in context menu handler:", err);
    }
  });
}

// Listen for messages from content script or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "OPEN_DASHBOARD") {
    chrome.tabs.create({ url: "dashboard.html" });
  }
});
