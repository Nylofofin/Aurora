from __future__ import annotations

from html.parser import HTMLParser

class PageText(HTMLParser):
    def __init__(self): super().__init__(); self.skip=0; self.title_mode=False; self.title=[]; self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg','nav','footer','header'): self.skip+=1
        if tag=='title': self.title_mode=True
        if tag in ('p','div','br','li','h1','h2','h3','article','section'): self.text.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','nav','footer','header') and self.skip: self.skip-=1
        if tag=='title': self.title_mode=False
        if tag in ('p','div','br','li','h1','h2','h3','article','section'): self.text.append(' ')
    def handle_data(self,data):
        if self.skip: return
        clean=' '.join(data.split())
        if clean:
            if self.title_mode: self.title.append(clean)
            else: self.text.append(clean)

class PageMetadata(HTMLParser):
    """Collect explicit publication/update dates from public article metadata."""
    def __init__(self): super().__init__(); self.dates=[]
    def handle_starttag(self,tag,attrs):
        attrs={str(k).lower():str(v) for k,v in attrs}
        if tag=='meta':
            key=(attrs.get('property') or attrs.get('name') or attrs.get('itemprop') or '').lower()
            if key in ('article:published_time','article:modified_time','datepublished','datemodified','date','pubdate'):
                value=attrs.get('content','').strip()
                if value: self.dates.append((key,value))
        elif tag=='time':
            value=attrs.get('datetime','').strip()
            if value: self.dates.append(('time',value))

class SearchResults(HTMLParser):
    """Extract organic headings from Bing's public HTML results page."""
    def __init__(self): super().__init__(); self.active=False; self.in_snippet=False; self.href=''; self.current=[]; self.snippet=[]; self.results=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='h2': self.active=True; self.href=''; self.current=[]; self.snippet=[]
        elif tag=='a' and self.active: self.href=attrs.get('href','')
        elif tag=='p' and self.results and not self.active and not self.results[-1][2]: self.in_snippet=True; self.snippet=[]
    def handle_data(self,data):
        if self.active: self.current.append(data)
        elif self.in_snippet: self.snippet.append(data)
    def handle_endtag(self,tag):
        if tag=='h2' and self.active:
            title=' '.join(' '.join(self.current).split())
            if self.href and title: self.results.append((self.href,title,''))
            self.active=False
        elif tag=='p' and self.in_snippet:
            if self.results: self.results[-1]=(self.results[-1][0],self.results[-1][1],' '.join(' '.join(self.snippet).split()))
            self.in_snippet=False

class DuckDuckGoResults(HTMLParser):
    """Extract organic result titles and snippets from DuckDuckGo's HTML endpoint."""
    def __init__(self): super().__init__(); self.active=''; self.href=''; self.current=[]; self.results=[]
    def handle_starttag(self,tag,attrs):
        if tag!='a': return
        attrs=dict(attrs); classes=set(attrs.get('class','').split())
        if 'result__a' in classes:
            self.active='title'; self.href=attrs.get('href',''); self.current=[]
        elif 'result__snippet' in classes and self.results:
            self.active='snippet'; self.current=[]
    def handle_data(self,data):
        if self.active: self.current.append(data)
    def handle_endtag(self,tag):
        if tag!='a' or not self.active: return
        value=' '.join(' '.join(self.current).split())
        if self.active=='title' and value: self.results.append((self.href,value,''))
        elif self.active=='snippet' and self.results:
            href,title,_=self.results[-1]; self.results[-1]=(href,title,value)
        self.active=''; self.current=[]

class DuckDuckGoLiteResults(HTMLParser):
    """Extract organic results from DDG's lightweight, non-JavaScript page."""
    def __init__(self): super().__init__(); self.in_link=False; self.in_snippet=False; self.current=[]; self.results=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs); classes=set(attrs.get('class','').split())
        if tag=='a' and 'result-link' in classes:
            self.in_link=True; self.current=[]; self.href=attrs.get('href','')
        elif tag in ('td','div') and 'result-snippet' in classes and self.results:
            self.in_snippet=True; self.current=[]
    def handle_data(self,data):
        if self.in_link or self.in_snippet: self.current.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.in_link:
            title=' '.join(' '.join(self.current).split())
            if title: self.results.append((self.href,title,''))
            self.in_link=False; self.current=[]
        elif tag in ('td','div') and self.in_snippet:
            if self.results:
                href,title,_=self.results[-1]; self.results[-1]=(href,title,' '.join(' '.join(self.current).split()))
            self.in_snippet=False; self.current=[]
