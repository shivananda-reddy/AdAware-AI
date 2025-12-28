# AdAware AI 🧠🛡️

AdAware AI is an advanced agentic assistant that analyzes online advertisements for safety, transparency, and deceptive patterns. It employs a hybrid pipeline combining Computer Vision (OCR + CLIP/GPT-4o Vision), NLP (Transformers), and Rule-Based logic to provide explainable risk assessments.

---

## 🚀 Key Features

*   **🛡️ Risk Taxonomy Classification**: Categorizes ads into **Safe**, **Low Risk**, **Moderate Risk**, **High Risk**, and **Scam Suspected**.
*   **📜 Policy Rule Engine**: Detects specific violations like "Guaranteed Cure" (Health) or "Double Your Money" (Financial).
*   **👁️ Hybrid Vision Pipeline**: logical fusion of OCR text, visual object detection, and optional LLM context.
*   **💾 Persistent Analysis History**: Stores results in a local SQLite database (`adaware_history.db`) for review and audit.
*   **📊 Interactive Dashboard**: View analysis history, statistics, accuracy metrics, and detailed evidence reports.
*   **🧩 Smart Chrome Extension**: 
    *   Page-level caching & debouncing for performance.
    *   "Why Flagged" evidence highlights.
    *   Privacy-focused mode.

---

## 🏗️ Architecture & Project Structure

The project was recently refactored into a modular services-based architecture:

```text
AdAware-AI/
├─ backend/                  # Python FastAPI Backend
│  ├─ core/                  # Configuration & Logging
│  ├─ services/              # Business Logic Modules
│  │  ├─ pipeline.py         # Main orchestration logic
│  │  ├─ classifier.py       # Hybrid classification
│  │  ├─ policy_rules.py     # Static rule definitions
│  │  ├─ reputation.py       # Domain heuristics
│  │  ├─ storage.py          # SQLite persistence
│  │  ├─ ocr.py, vision.py   # Perception modules
│  │  └─ llm.py              # LLM Integration
│  ├─ api.py                 # API Routes Definition
│  ├─ schemas.py             # Pydantic Models (Risk Taxonomy)
│  └─ main.py                # App Bootstrap
│
├─ extension/                # Chrome Extension
│  ├─ contentScript.js       # Overlay logic & Page Caching
│  ├─ popup.html/js          # Settings (Backend URL, Sensitivity)
│  ├─ background.js
│  └─ manifest.json
│
├─ web_dashboard/            # Standalone Web UI
│  ├─ index.html             # Tabs: Analyze, History, Stats
│  ├─ script.js
│  └─ styles.css
│
├─ adaware_history.db        # auto-generated SQLite DB
└─ requirements.txt          # Python dependencies
```

---

## 🛠️ Setup & Installation

### 1. Prerequisites
- **Python 3.10+**
- **Tesseract OCR** installed and added to system PATH.
- **OpenAI API Key** (optional, recommended for full capabilities).

### 2. Backend Setup
1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Set environment variables (Windows PowerShell):
    ```powershell
    $env:OPENAI_API_KEY="sk-..."
    ```
4.  Run the server:
    ```bash
    python backend/main.py
    ```
    *The server runs on `http://127.0.0.1:8000`.*
    *API Documentation is available at `http://127.0.0.1:8000/docs`.*

### 3. Chrome Extension Setup
1.  Open Chrome and navigate to `chrome://extensions/`.
2.  Enable **Developer mode** (top right).
3.  Click **Load unpacked** and select the `extension/` folder.
4.  Pin the extension icon. You can configure settings (like Backend URL) by clicking the icon.

### 4. Web Dashboard
1.  Open `web_dashboard/index.html` in your browser.
2.  Ensure the backend is running.
3.  Use the dashboard to upload images or view your analysis history.

---

## 📡 API Usage

The backend provides a RESTful API. Key endpoints:

-   `POST /analyze_hover`: Main analysis endpoint. Accepts JSON with `image_url` or `image_base64`.
-   `GET /api/v1/history`: Retrieve past analyses.
-   `GET /api/v1/stats`: Global statistics and confusion matrix.
-   `POST /api/v1/feedback`: Submit user feedback for results.

### Example Usage

**Request:**
```json
POST /analyze_hover
{
  "image_url": "https://example.com/suspicious-ad.jpg",
  "page_origin": "https://social-media.com",
  "use_llm": false
}
```

**Response:**
```json
{
  "final_label": "high-risk",
  "risk_score": 0.95,
  "subcategories": ["health-claim", "urgency"],
  "evidence": {
    "risky_phrases": [
      { "phrase": "guaranteed cure", "reason": "Strong urgency/sales language" }
    ]
  },
  "rule_triggers": [
    { "rule_id": "H1", "description": "Guaranteed cure/remedy claim detected" }
  ]
}
```


---

## 🧪 Development Status

-   [x] Core Classification Pipeline
-   [x] Extension Overlay & Caching
-   [x] SQLite Persistence
-   [x] Policy Rules Engine
-   [x] Interactive Dashboard
-   [ ] User Accounts / Cloud Sync
-   [ ] Advanced Threat Intelligence Feeds

---

**AdAware AI** — Making the web transparent, one ad at a time.
