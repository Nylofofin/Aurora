from __future__ import annotations

import re
import unicodedata


def normalize_words(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode('ascii').casefold()).strip()


def strip_wake_word(text):
    return re.sub(r'^\s*(?:(?:ei|ol[áa])\s+)?aurora[\s,.:;!?-]*','',str(text),flags=re.I).strip()
