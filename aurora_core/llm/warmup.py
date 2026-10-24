# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread
import json, threading, urllib.request
from .prompts import assistant_system_prompt

class ModelWarmup(QThread):
    """Pre-load both the conversation model and the agent model into Ollama.

    Loading both models during startup means the first user request that
    triggers the agent (gemma4:e2b-it-q4_K_M) does not pay the 30-40 s
    cold-start penalty of loading 4.6 GB from disk.  The two warm-up
    requests run concurrently so they do not extend the total startup time
    significantly when the machine has enough RAM (≥6 GB free).
    """

    def __init__(self, cfg): super().__init__(); self.cfg = cfg

    def _warmup_one(self, model, num_ctx):
        try:
            ep = self.cfg['endpoint'].rstrip('/')
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': assistant_system_prompt()},
                    {'role': 'user', 'content': 'Responda apenas: Pronto.'},
                ],
                'stream': False,
                'keep_alive': self.cfg.get('keep_alive', -1),
                'think': False,
                'options': {
                    'num_ctx': num_ctx,
                    'num_thread': int(self.cfg['num_thread']),
                    'num_gpu': int(self.cfg['num_gpu']),
                    'num_batch': 128,
                    'temperature': 0.1,
                    'num_predict': 2,
                },
            }
            req = urllib.request.Request(
                ep + '/api/chat',
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'},
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                r.read()
        except Exception:
            pass

    def run(self):
        conv_model = self.cfg['model']
        agent_model = self.cfg.get('agent_model', '')
        conv_ctx = int(self.cfg.get('num_ctx', 1024))
        agent_ctx = max(conv_ctx, int(self.cfg.get('agent_num_ctx', 2048)))

        threads = [threading.Thread(target=self._warmup_one, args=(conv_model, conv_ctx), daemon=True)]
        if agent_model and agent_model != conv_model:
            threads.append(threading.Thread(target=self._warmup_one, args=(agent_model, agent_ctx), daemon=True))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=150)
