# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
import unicodedata

def normalize_words(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode('ascii').casefold()).strip()

def strip_wake_word(text, assistant_name='Aurora'):
    value=str(text or '')
    name_tokens=normalize_words(assistant_name or 'Aurora').split() or ['aurora']
    prefix=re.match(r'^\s*(?:(?:ei|ol[áa])(?:[\s,.:;!?-]+))?',value,flags=re.I)
    position=prefix.end() if prefix else 0
    raw_tokens=list(re.finditer(r'[^\W_]+',value[position:],flags=re.UNICODE))
    if len(raw_tokens)<len(name_tokens): return value.strip()
    consumed=0
    for expected,match in zip(name_tokens,raw_tokens):
        if normalize_words(match.group())!=expected: return value.strip()
        consumed=match.end()
    end=position+consumed
    return value[end:].lstrip(' \t,.:;!?-')
