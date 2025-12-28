# AdAware AI - Testing Guide

## Quick Start Testing

### 1. Start the Backend
```bash
cd "c:\Users\shiva\AdAware AI"
python -m backend.main
```

**Expected Startup Output**:
```
============================================================
AdAware AI Backend Starting...
============================================================
INFO:adaware.config:OpenAI configured with model: gpt-4o
INFO:adaware:Database initialized at adaware_history.db
INFO:adaware:Pre-loading ML models...
INFO:adaware.nlp:Loading sentiment model...
```

Watch for:
- ✓ = Model loaded successfully
- ✗ = Model failed (will use fallback)

### 2. Open Web Dashboard
```
http://localhost:8000
```
or use the web dashboard:
```
Open: web_dashboard/index.html in browser
```

### 3. Test with Red Bull Image

**Option A: Use Image URL**
1. Find a Red Bull can image online (e.g., product photo)
2. Paste URL in "Ad image URL" field
3. Check "Enable LLM-enhanced summary"
4. Click "Run Analysis"

**Option B: Upload Local Image**
1. Download a Red Bull product image
2. Click "Click or drag an ad image"
3. Select the image file
4. Click "Run Analysis"

### Expected Results for Red Bull:

```
✅ Brand: Red Bull
✅ Category: Energy Drink (Catalog)
✅ Trust Score: 85-95/100
✅ Model Confidence: 80-90%
✅ Risk Level: Low Risk or Safe
✅ Health Advisory: High Caffeine, Not recommended for children
✅ Price: ~2.00 - 5.00 USD
✅ No "Suspicious" tags
```

**If CLIP not loaded**:
```
ℹ️ Image-text similarity: Unavailable (CLIP model not loaded)
```
This is OK! Similarity should show as "Unavailable" not "0.00"

---

## Test Scenarios

### Scenario 1: Known Brand (Red Bull)
**Purpose**: Verify catalog matching, high trust, health advisory separation

**Steps**:
1. Use Red Bull can image
2. Check backend logs for "✓ Brand matched in catalog: Red Bull"
3. Verify UI shows:
   - Trust 85+
   - Confidence 80+
   - Category "Energy Drink (Catalog)"
   - Health advisory present but separate from trust

**Pass Criteria**:
- No "Suspicious" tag
- Trust > 80
- Confidence > 0.75
- Category identified

### Scenario 2: Unknown Brand
**Purpose**: Verify graceful handling of unknown products

**Steps**:
1. Use random product image (not in catalog)
2. Check that system doesn't crash
3. Verify UI shows:
   - Trust ~50-70 (neutral)
   - Confidence varies
   - Category "Inferred" or "Unclassified"

**Pass Criteria**:
- No crash
- Honest "unknown" labels
- No fake high confidence

### Scenario 3: Offline Mode (No HuggingFace)
**Purpose**: Verify fallbacks work when models can't load

**Steps**:
1. Set environment variable:
   ```bash
   set ADAWARE_HF_OFFLINE=1
   ```
2. Restart backend
3. Verify startup logs show:
   ```
   ✗ Failed to load sentiment model (Offline=True)
   Will use fallback heuristic sentiment analysis
   ```
4. Run analysis on any image
5. Check similarity shows "Unavailable" not "0.00"

**Pass Criteria**:
- Backend starts successfully
- Analysis completes
- UI clearly shows unavailable features
- No crash or hang

### Scenario 4: No OpenAI Key
**Purpose**: Verify system works without LLM

**Steps**:
1. Remove or comment out OPENAI_API_KEY
2. Restart backend
3. Uncheck "Enable LLM-enhanced summary"
4. Run analysis

**Pass Criteria**:
- Analysis completes
- Basic features work (OCR, catalog lookup, scoring)
- No LLM-dependent features crash

---

## Debugging Commands

### Check Model Status
```python
# In Python console
from backend.services import nlp, fusion

# Check NLP models
print("Sentiment:", "Loaded" if nlp._sentiment_pipe else "Not loaded")
print("NER:", "Loaded" if nlp._ner_pipe else "Not loaded")

# Check CLIP
print("CLIP:", "Loaded" if fusion._CLIP_MODEL else "Not loaded")
```

### View Logs
Backend logs will show:
```
INFO:adaware.pipeline:✓ Brand matched in catalog: Red Bull (Energy Drink)
INFO:adaware.pipeline:Image-text similarity: 0.745
INFO:adaware.pipeline:Domain trust: neutral (local/extension origin)
```

### Check Database
```bash
sqlite3 adaware_history.db
.tables
SELECT final_label, COUNT(*) FROM analyses GROUP BY final_label;
```

---

## Common Issues & Fixes

### Issue: "Image-text similarity: 0.00"
**Old Behavior**: Shows 0.00 even when unavailable  
**New Behavior**: Shows "Unavailable (CLIP model not loaded)"  
**Fix Applied**: ✅ Done in this update

### Issue: "Trust Score always ~50%"
**Old Behavior**: Even known brands show 50%  
**New Behavior**: Red Bull shows 85-95%  
**Fix Applied**: ✅ Done - catalog matching, confidence scoring fixed

### Issue: "Product: Unknown" for Red Bull
**Old Behavior**: Catalog matched but product_info not populated  
**New Behavior**: Product: Red Bull, Category: Energy Drink  
**Fix Applied**: ✅ Done - product_info population rewritten

### Issue: "Suspicious" tag on local dashboard
**Old Behavior**: Local URLs flagged as suspicious  
**New Behavior**: Neutral domain trust for local/extension  
**Fix Applied**: ✅ Done - domain trust logic improved

### Issue: Startup hangs or slow first request
**Old Behavior**: Models load on first request, DNS timeout  
**New Behavior**: Models preload at startup, fast-fail  
**Fix Applied**: ✅ Done - startup preloading added

---

## Performance Benchmarks

### Expected Timings

**Startup** (first time, with network):
- Model downloads: 1-3 minutes (one-time)
- Subsequent startups: 2-5 seconds

**Per Request**:
- With OpenAI Vision: 2-4 seconds
- Without Vision: 0.5-1 second
- With LLM enabled: +1-2 seconds

**First Request** (models already cached):
- Should be same as subsequent requests
- No 30+ second hang

---

## Verification Checklist

Use this checklist after deploying the fixes:

- [ ] Backend starts without errors
- [ ] Models preload (or fail gracefully with clear logs)
- [ ] Red Bull image → Trust 85+, Confidence 80+
- [ ] Red Bull → Category "Energy Drink (Catalog)"
- [ ] Red Bull → Health advisory present
- [ ] Red Bull → No "Suspicious" tag
- [ ] Unknown brand → Trust ~50-70, honest labels
- [ ] Similarity shows "Unavailable" when CLIP fails (not "0.00")
- [ ] Price shows "Not detected" when absent (not confusing text)
- [ ] UI tooltips explain unavailable features
- [ ] Offline mode works (ADAWARE_HF_OFFLINE=1)
- [ ] No 30+ second hangs on first request
- [ ] Logs show ✓/✗ for model loading
- [ ] Web dashboard displays results correctly
- [ ] History stores and displays properly

---

## Next Steps After Testing

1. **If all tests pass**:
   - Mark BUGFIX_REPORT.md as verified
   - Deploy to production
   - Monitor logs for any edge cases

2. **If tests fail**:
   - Note which scenario failed
   - Check logs for error messages
   - Report specific failure mode

3. **Optional improvements**:
   - Add more brands to catalog
   - Train category classifier
   - Improve price detection regex

---

## Support

If you encounter issues:
1. Check `BUGFIX_REPORT.md` for root cause analysis
2. Review backend logs for error messages
3. Verify environment variables are set correctly
4. Test in offline mode to isolate network issues
