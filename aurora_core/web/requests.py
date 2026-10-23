from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import aurora_fx
from ..web.intent import current_search_window, news_search_intent
from ..web.pipeline import search_public_web
from ..web.weather import weather_now

class WeatherRequest(QThread):

    result=Signal(str); error=Signal(str)

    def __init__(self,cfg,prompt): super().__init__(); self.cfg=cfg; self.prompt=prompt

    def run(self):

        try: self.result.emit(weather_now(self.cfg,self.prompt))

        except Exception as exc: self.error.emit(str(exc))

class SearchRequest(QThread):

    result=Signal(str,str); error=Signal(str,str); progress=Signal(object)

    def __init__(self,query,freshness=None,news_only=False):
        super().__init__()
        self.query=query; self.freshness=freshness; self.news_only=news_only

    def run(self):

        try:
            self.progress.emit({"stage":"searching","tasks":["DuckDuckGo Lite", "Bing RSS", "Bing Notícias"],"workers":1,"completed":0,"total":3})
            output=search_public_web(self.query,self.freshness,self.news_only,progress=self.progress.emit)
            self.result.emit(self.query,output)

        except Exception as exc: self.error.emit(self.query,str(exc))

class FXRequest(QThread):

    result=Signal(object); error=Signal(str)

    def __init__(self,intent,prompt): super().__init__(); self.intent=intent; self.prompt=prompt

    def run(self):

        try:

            fallback=lambda _intent: search_public_web(self.prompt,current_search_window(self.prompt),news_search_intent(self.prompt))

            self.result.emit(aurora_fx.get_quote(self.intent,search_fallback=fallback,timeout=aurora_fx.API_TIMEOUT))

        except Exception as exc: self.error.emit(str(exc))
