# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re

ENGLISH_MARKERS={'absolutely','and','answer','are','because','can','certainly','could','degrees','do','does','face','fast','four','from','good','have','has','here','hot','how','is','it','its','okay','please','should','smiling','sure','temperature','that','the','they','this','those','three','today','tomorrow','two','was','we','weather','were','what','when','where','which','who','will','with','would','yes','you','your','eyes'}

PORTUGUESE_MARKERS={'a','agora','as','com','da','das','de','do','dos','ela','ele','em','está','estão','eu','hoje','mais','meu','minha','não','no','nos','o','os','para','pela','pelo','por','que','se','sim','sua','um','uma','você'}

# Words and verb forms that are strong Spanish signals and uncommon in normal
# Brazilian Portuguese. Keep this intentionally small to avoid translating
# Portuguese sentences just because they share words such as "que" or "para".
SPANISH_MARKERS={'aquí','allí','allá','comenzó','comenzo','puedo','puedes','pueden','según','siento','inició','inicio','el','los','pero','hay','fue','estoy','estás','tienes','quieres','necesitas','deberías','ha','hemos','había','ustedes'}

def likely_english(text):
    words=re.findall(r"[a-zA-ZÀ-ÿ']+",str(text).lower())
    english=sum(word in ENGLISH_MARKERS for word in words)
    portuguese=sum(word in PORTUGUESE_MARKERS for word in words)
    return english>=2 and english>portuguese or any(word in ('yes','please') for word in words)

def likely_portuguese(text):
    words=re.findall(r"[a-zA-ZÀ-ÿ']+",str(text).lower())
    return sum(word in PORTUGUESE_MARKERS for word in words)>=2

def likely_spanish(text):
    value=str(text).lower()
    words=re.findall(r"[a-zA-ZÀ-ÿ']+",value)
    spanish=sum(word in SPANISH_MARKERS for word in words)+int('¿' in value or '¡' in value)
    portuguese=sum(word in PORTUGUESE_MARKERS for word in words)
    # A single distinctive conjugation is enough for short spoken sentences;
    # otherwise require multiple signals and no clear Portuguese markers.
    return spanish >= 1 and (spanish >= 2 or portuguese == 0)
