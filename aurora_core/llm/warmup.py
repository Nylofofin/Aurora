from __future__ import annotations

from PySide6.QtCore import QThread
import json, urllib.request
from .prompts import assistant_system_prompt

class ModelWarmup(QThread):

    def __init__(self,cfg): super().__init__(); self.cfg=cfg

    def run(self):

        try:

            ep=self.cfg['endpoint'].rstrip('/')

            payload={'model':self.cfg['model'],'messages':[{'role':'system','content':assistant_system_prompt()},{'role':'user','content':'Responda apenas: Pronto.'}],

                'stream':False,'keep_alive':-1,'think':False,'options':{'num_ctx':int(self.cfg['num_ctx']),'num_thread':int(self.cfg['num_thread']),'num_gpu':int(self.cfg['num_gpu']),'num_batch':128,'temperature':0.1,'num_predict':2}}

            req=urllib.request.Request(ep+'/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})

            with urllib.request.urlopen(req,timeout=120) as r: r.read()

        except Exception: pass
