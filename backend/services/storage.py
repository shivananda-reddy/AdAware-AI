
import sqlite3
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.schemas import AnalysisResult, RiskLabel

LOG = logging.getLogger("adaware.storage")
DB_PATH = "adaware_history.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Analysis History Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                url TEXT,
                domain TEXT,
                final_label TEXT,
                risk_score REAL,
                ocr_snippet TEXT,
                raw_json TEXT
            )
        ''')
        
        # Feedback Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                analysis_id TEXT PRIMARY KEY,
                user_label TEXT,
                is_correct BOOLEAN,
                notes TEXT,
                timestamp TEXT,
                FOREIGN KEY(analysis_id) REFERENCES analyses(id)
            )
        ''')
        
        conn.commit()
        conn.close()
        LOG.info("Database initialized at %s", DB_PATH)
    except Exception as e:
        LOG.error("Failed to init database: %s", e)

def save_analysis(result: AnalysisResult, url: Optional[str] = None, domain: Optional[str] = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Store full JSON for retrieval
        result_json = result.model_dump_json() if hasattr(result, "model_dump_json") else result.json()
        
        ocr_snip = (result.ocr_text or "")[:100]
        
        c.execute('''
            INSERT INTO analyses (id, timestamp, url, domain, final_label, risk_score, ocr_snippet, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result.request_id,
            result.timestamp,
            url,
            domain,
            result.final_label.value,
            result.risk_score,
            ocr_snip,
            result_json
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        LOG.error("Failed to save analysis: %s", e)

def get_history(limit: int = 50) -> List[AnalysisResult]:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute('SELECT raw_json FROM analyses ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = c.fetchall()
        
        results = []
        for r in rows:
            try:
                data = json.loads(r['raw_json'])
                results.append(AnalysisResult(**data))
            except Exception as e:
                LOG.warning("Failed to parse history item: %s", e)
                
        conn.close()
        return results
    except Exception as e:
        LOG.error("Failed to get history: %s", e)
        return []

def get_analysis_by_id(aid: str) -> Optional[AnalysisResult]:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT raw_json FROM analyses WHERE id = ?', (aid,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return AnalysisResult(**json.loads(row['raw_json']))
        return None
    except Exception as e:
        LOG.error("Failed to get analysis by id: %s", e)
        return None

def save_feedback(analysis_id: str, user_label: str, is_correct: bool, notes: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        ts = datetime.utcnow().isoformat()
        
        c.execute('''
            INSERT OR REPLACE INTO feedback (analysis_id, user_label, is_correct, notes, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (analysis_id, user_label, is_correct, notes, ts))
        
        conn.commit()
        conn.close()
    except Exception as e:
        LOG.error("Failed to save feedback: %s", e)

def get_stats() -> Dict[str, Any]:
    stats = {
        "total_analyses": 0,
        "label_counts": {},
        "confusion_matrix": {"correct": 0, "incorrect": 0}
    }
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Total
        c.execute('SELECT count(*) from analyses')
        stats["total_analyses"] = c.fetchone()[0]
        
        # Label counts
        c.execute('SELECT final_label, count(*) FROM analyses GROUP BY final_label')
        rows = c.fetchall()
        for label, count in rows:
            stats["label_counts"][label] = count
            
        # Confusion matrix (simple)
        c.execute('SELECT is_correct, count(*) FROM feedback GROUP BY is_correct')
        f_rows = c.fetchall()
        for is_corr, count in f_rows:
            key = "correct" if is_corr else "incorrect"
            stats["confusion_matrix"][key] = count
            
        conn.close()
    except Exception as e:
        LOG.error("Failed to get stats: %s", e)
        
    return stats
