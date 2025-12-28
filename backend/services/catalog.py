import json
import os
import logging
from typing import List, Dict, Optional

LOG = logging.getLogger(__name__)

class BrandCatalog:
    _instance = None
    
    def __init__(self, catalog_path: str = None):
        if catalog_path is None:
            # Default to backend/data/brand_catalog.json relative to this file
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            catalog_path = os.path.join(base_dir, "data", "brand_catalog.json")
            
        self.catalog_path = catalog_path
        self.brands: List[Dict] = []
        self.loaded = False
        self._load()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self):
        try:
            if not os.path.exists(self.catalog_path):
                LOG.warning(f"Brand catalog not found at {self.catalog_path}")
                return
            
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                self.brands = json.load(f)
                self.loaded = True
            LOG.info(f"Loaded {len(self.brands)} brands from catalog.")
        except Exception as e:
            LOG.error(f"Failed to load brand catalog: {e}")

    def lookup(self, text: str, vision_brands: List[str] = None) -> Optional[Dict]:
        """
        Look up a brand by text (OCR) or vision labels.
        Returns the brand dict if found, or None.
        """
        if not self.loaded:
            return None
            
        text_lower = text.lower() if text else ""
        vision_lower = [v.lower() for v in (vision_brands or [])]
        
        # 1. Exact match on Vision Brands
        for v_brand in vision_lower:
            for entry in self.brands:
                for name in entry.get("names", []):
                    if name.lower() == v_brand:
                        return entry

        # 2. Key phrase match in OCR text
        # This is a bit loose, so we prioritize longer matches or specific names
        best_match = None
        
        for entry in self.brands:
            for name in entry.get("names", []):
                n_lower = name.lower()
                # Check if brand name appears as a distinct word/phrase in text
                # Simple check: space-bounded or start/end
                if n_lower in text_lower:
                    # Heuristic: verify if it makes sense contextually?
                    # For now, just return first strong match
                    return entry
                    
        return None

# Singleton access
_catalog = None

def get_catalog() -> BrandCatalog:
    global _catalog
    if _catalog is None:
        _catalog = BrandCatalog()
    return _catalog
