
from typing import List, Dict, Any, Optional
import urllib.parse
import re

from backend.schemas import SourceReputation

def get_domain_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        # handle cases without protocol
        if not url.startswith("http"):
            # Special case for internal/extension contexts
            if url in ["WebDashboard", "localhost", "127.0.0.1"] or "extension" in url:
                return url
            url = "http://" + url
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc
    except Exception:
        return None

def check_reputation(url: Optional[str], page_origin: Optional[str] = None) -> SourceReputation:
    target_url = url or page_origin
    
    rep = SourceReputation(https=False, flags=[])
    
    if not target_url:
        return rep

    # Basic Heuristics
    domain = get_domain_from_url(target_url)
    rep.domain = domain
    
    if target_url.lower().startswith("https"):
        rep.https = True
    elif domain in ["WebDashboard", "localhost", "127.0.0.1"]:
        # Internal tools are safe
        rep.https = True
    else:
        rep.flags.append("Not HTTPS")
        
    if domain:
        # 1. Length check
        if len(domain) > 30:
            rep.flags.append("Very long domain name")
            
        # 2. Hyphen check
        if domain.count("-") > 3:
            rep.flags.append("Excessive hyphens in domain")
            
        # 3. TLD check (simple list of typically spammy TLDs)
        spammy_tlds = {".xyz", ".top", ".club", ".info", ".biz"}
        for tld in spammy_tlds:
            if domain.lower().endswith(tld):
                rep.flags.append(f"Suspicious TLD ({tld})")
                break
                
        # 4. Punycode check (xn--)
        if "xn--" in domain.lower():
            rep.flags.append("Punycode domain (possible spoofing)")

    return rep
