# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
import unicodedata

def normalize_words(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode('ascii').casefold()).strip()

def strip_wake_word(text, assistant_name='Aurora'):
    value=str(text or '')
    name_tokens=normalize_words(assistant_name or 'Aurora').split() or ['aurora']
    raw_tokens=list(re.finditer(r'[^\W_]+',value,flags=re.UNICODE))
    if not raw_tokens: return value.strip()

    def near_token(actual,expected):
        actual=normalize_words(actual); expected=normalize_words(expected)
        if actual==expected: return True
        # Whisper commonly changes one character in a short, acoustically
        # similar assistant name. Only forgive one edit on the leading name;
        # never apply fuzzy matching to the rest of the user's command.
        if min(len(actual),len(expected))<4 or abs(len(actual)-len(expected))>1: return False
        previous=list(range(len(expected)+1))
        for row,left in enumerate(actual,1):
            current=[row]
            for column,right in enumerate(expected,1):
                current.append(min(current[-1]+1,previous[column]+1,
                                   previous[column-1]+(left!=right)))
            if min(current)>1: return False
            previous=current
        return previous[-1]<=1

    offset=0
    if normalize_words(raw_tokens[0].group()) in {'ei','ola'}:
        offset=1
    if offset<len(raw_tokens) and normalize_words(raw_tokens[offset].group()) in {'a','o'}:
        if offset+1<len(raw_tokens) and near_token(raw_tokens[offset+1].group(),name_tokens[0]):
            offset+=1
    if len(raw_tokens)-offset<len(name_tokens): return value.strip()
    for index,(expected,match) in enumerate(zip(name_tokens,raw_tokens[offset:])):
        matches=near_token(match.group(),expected) if index==0 else normalize_words(match.group())==expected
        if not matches: return value.strip()
    end=raw_tokens[offset+len(name_tokens)-1].end()
    return value[end:].lstrip(' \t,.:;!?-')
