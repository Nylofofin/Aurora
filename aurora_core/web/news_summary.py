from __future__ import annotations

from .freshness import _independent_recent_source_count, _publication_within_window
from .intent import news_unconfirmed_message


def format_news_digest(items, window=""):
    """Speak verified news headlines without asking a small model to paraphrase facts."""
    selected=[]
    sources=set()
    seen_titles=set()
    for item in items:
        host=str(item.get('host') or '').strip().casefold()
        source=((item.get('publisher') or '') if host=='news.google.com' else host).strip().casefold()
        title=' '.join(str(item.get('title') or '').split())
        published=str(item.get('published') or '').strip()
        if not source or not title or (window and not _publication_within_window(published,window)):
            continue
        title_key=title.casefold()
        if source in sources or title_key in seen_titles:
            continue
        candidate=selected+[item]
        if window and _independent_recent_source_count(candidate,window)<=_independent_recent_source_count(selected,window):
            continue
        selected.append(item)
        sources.add(source)
        seen_titles.add(title_key)
        if len(selected)>=2:
            break
    if window and len(selected)<2:
        return news_unconfirmed_message()
    if not selected:
        return news_unconfirmed_message()
    parts=[]
    for index,item in enumerate(selected):
        title=' '.join(str(item['title']).split())
        source=(item.get('publisher') or item.get('host') or 'fonte não identificada').strip()
        published=str(item.get('published') or '').strip()
        lead='Manchete' if index==0 else 'Outra manchete'
        sentence=f'{lead}: {title}. Fonte: {source}'
        if published:
            sentence+=f', {published}'
        parts.append(sentence+'.')
    return ' '.join(parts)
