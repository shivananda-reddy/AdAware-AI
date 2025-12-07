# AdAware AI 🧠🛡️

AdAware AI is a browser-based assistant that analyzes online advertisements for safety and transparency.  
It uses Computer Vision, OCR, NLP, and LLMs to understand ad content and provide an explainable verdict.

---

## 🚀 Features

- 🔍 **Ad analysis from webpages**
  - Works on ad images and product page URLs.
- 👁️ **Computer Vision + OCR**
  - Extracts text from ad images.
- 🧠 **LLM-powered reasoning**
  - Summarizes the ad and explains why it is safe / risky.
- 🏷️ **Classification**
  - Labels ads (e.g., safe / potentially misleading, etc. – customizable).
- 🧩 **Chrome extension UI**
  - Hover or click to see verdicts, key info.
- 📊 **Web dashboard (WIP)**
  - Simple interface to test the backend with sample ads.

---

## 🏗️ Project Structure

```text
AdAware-AI/
├─ backend/          # Python backend (API + ML/LLM logic)
│  ├─ main.py        # API entry point (start server from here)
│  ├─ classifier.py  # Ad classification logic
│  ├─ ocr.py         # OCR / text extraction utilities
│  ├─ vision.py      # Vision-related helpers
│  ├─ llm.py         # LLM integration (uses OPENAI_API_KEY env var)
│  └─ ...            # other helpers (nlp, quality, utils, etc.)
│
├─ extension/        # Chrome extension
│  ├─ manifest.json  # Extension manifest
│  ├─ background.js
│  ├─ contentScript.js
│  ├─ popup.html / popup.js
│  ├─ dashboard.html / dashboard.js
│  └─ icons/
│
├─ web_dashboard/    # Simple HTML dashboard (optional)
│  └─ index.html
│
├─ requirements.txt  # Python dependencies
├─ start_backend.bat # Helper script to run backend on Windows
└─ README.md
