
import os
import sys

# Ensure backend acts as if we are at root
sys.path.append(os.getcwd())

from backend.services.catalog import get_catalog

def test_catalog():
    print("Initializing Catalog...")
    c = get_catalog()
    print(f"Catalog Loaded: {c.loaded}")
    print(f"Brand Count: {len(c.brands)}")
    
    # Test Cases
    cases = [
        ([], "Empty List"),
        (["Red Bull"], "Exact Match"),
        (["red bull"], "Lowercase Match"),
        (["RedBull"], "Variant Match"),
        ([" Some Brand "], "Unknown"),
    ]
    
    for visions, desc in cases:
        res = c.lookup("", visions) 
        print(f"[{desc}] vision={visions} -> Found: {res['names'][0] if res else 'None'}")

    # OCR Test
    print("\n-- OCR Tests --")
    ocr_res = c.lookup("Buy some Red Bull today", [])
    print(f"OCR 'Buy some Red Bull today' -> Finding: {ocr_res['names'][0] if ocr_res else 'None'}")


if __name__ == "__main__":
    test_catalog()
