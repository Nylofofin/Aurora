from __future__ import annotations

import re

ENGLISH_MARKERS={'absolutely','and','answer','are','because','can','certainly','could','degrees','do','does','face','fast','four','from','good','have','has','here','hot','how','is','it','its','okay','please','should','smiling','sure','temperature','that','the','they','this','those','three','today','tomorrow','two','was','we','weather','were','what','when','where','which','who','will','with','would','yes','you','your','eyes'}

PORTUGUESE_MARKERS={'a','agora','as','com','da','das','de','do','dos','ela','ele','em','está','estão','eu','hoje','mais','meu','minha','não','no','nos','o','os','para','pela','pelo','por','que','se','sim','sua','um','uma','você'}

def likely_english(text):
    words=re.findall(r"[a-zA-ZÀ-ÿ']+",str(text).lower())
    english=sum(word in ENGLISH_MARKERS for word in words)
    portuguese=sum(word in PORTUGUESE_MARKERS for word in words)
    return english>=2 and english>portuguese or any(word in ('yes','please') for word in words)

def likely_portuguese(text):
    words=re.findall(r"[a-zA-ZÀ-ÿ']+",str(text).lower())
    return sum(word in PORTUGUESE_MARKERS for word in words)>=2
