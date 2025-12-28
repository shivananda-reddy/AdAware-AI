
from typing import List
from backend.schemas import RuleTrigger

def evaluate_rules(text: str) -> List[RuleTrigger]:
    triggers = []
    t_lower = (text or "").lower()
    
    # H1: Health claim + cure
    if "cure" in t_lower or "remedy" in t_lower:
        if "guaranteed" in t_lower or "100%" in t_lower:
            triggers.append(RuleTrigger(
                rule_id="H1", 
                description="Guaranteed cure/remedy claim detected", 
                severity="high"
            ))

    # F1: Financial promise
    if "double your money" in t_lower or "guaranteed returns" in t_lower:
        triggers.append(RuleTrigger(
            rule_id="F1",
            description="Unrealistic financial promise",
            severity="high"
        ))
        
    # B1: Before/After
    if "before" in t_lower and "after" in t_lower:
         triggers.append(RuleTrigger(
            rule_id="B1",
            description="Before/After comparison usage",
            severity="medium"
        ))

    # C1: Urgency / FOMO
    fomo_phrases = ["limited time", "only today", "act now", "don't miss"]
    if any(p in t_lower for p in fomo_phrases):
         triggers.append(RuleTrigger(
            rule_id="C1",
            description="High urgency / FOMO tactics",
            severity="medium"
        ))
        
    return triggers
