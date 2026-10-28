# SPDX-License-Identifier: GPL-3.0-only
"""Private, bounded persistence for the current user's conversation context."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from .config import DATA_DIR
from .system.files import normalize_words

SESSION_FILE = DATA_DIR / "conversation-session.json"
_STOP_WORDS = {
    "agora", "ainda", "algo", "algum", "alguma", "alguns", "algumas", "aqui",
    "assim", "ate", "cada", "como", "com", "da", "das", "de", "dela", "dele",
    "depois", "do", "dos", "e", "ela", "elas", "ele", "eles", "em", "essa",
    "essas", "esse", "esses", "esta", "estao", "estar", "este", "estes", "eu",
    "foi", "for", "isso", "isto", "ja", "mais", "mas", "me", "mesmo", "meu",
    "minha", "muito", "na", "nas", "nem", "no", "nos", "o", "os", "ou", "para",
    "pela", "pelo", "por", "porque", "que", "qual", "quando", "quanto", "se",
    "sem", "ser", "seu", "sua", "tambem", "tem", "ter", "um", "uma", "umas",
    "uns", "voce",
}
_PERSONAL_FACT = re.compile(
    r"^(?:eu\s+(?:sou|moro|trabalho|estudo|tenho|gosto|prefiro|me chamo)\b|"
    r"meu nome [eé]\b|minha profiss[aã]o [eé]\b)"
)


def _empty_session():
    return {
        "version": 1,
        "session_id": uuid.uuid4().hex,
        "active": True,
        "history": [],
        "summary": "",
        "facts": [],
        "topic_counts": {},
    }


class ConversationSession:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else SESSION_FILE
        self.data = _empty_session()

    def load(self):
        try:
            os.chmod(self.path, 0o600)
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = _empty_session()
            return self.data["history"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Não consegui ler a sessão local; o arquivo foi preservado.") from exc
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("A sessão local está inválida; o arquivo foi preservado.")

        fresh = _empty_session()
        history = data.get("history", [])
        if not isinstance(history, list):
            raise ValueError("O histórico da sessão local está inválido; o arquivo foi preservado.")
        facts = data.get("facts", [])
        if not isinstance(facts, list):
            raise ValueError("Os fatos da sessão local estão inválidos; o arquivo foi preservado.")
        topic_counts = data.get("topic_counts", {})
        if not isinstance(topic_counts, dict):
            raise ValueError("Os temas da sessão local estão inválidos; o arquivo foi preservado.")
        fresh.update({
            "session_id": str(data.get("session_id") or fresh["session_id"])[:64],
            "active": bool(data.get("active", True)),
            "history": [
                {"role": item["role"], "content": str(item["content"])[:1200]}
                for item in history
                if isinstance(item, dict)
                and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)
            ][-6:],
            "summary": str(data.get("summary") or "")[-1200:],
            "facts": [str(item)[:240] for item in facts if isinstance(item, str)][-24:],
            "topic_counts": {
                str(key)[:40]: max(1, min(1000, int(value)))
                for key, value in topic_counts.items()
                if isinstance(key, str) and str(key).isalpha() and str(value).isdigit()
            },
        })
        self.data = fresh
        return list(fresh["history"])

    def start_new(self):
        self.data["session_id"] = uuid.uuid4().hex
        self.data["active"] = True
        self.data["history"] = []
        self.save()

    def close(self):
        self.data["active"] = False
        self.save()

    def record_exchange(self, user_text, assistant_text):
        user_text = " ".join(str(user_text).split())[:700]
        assistant_text = " ".join(str(assistant_text).split())[:1200]
        if not user_text or not assistant_text:
            return

        history = self.data["history"]
        history.extend((
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ))
        while len(history) > 6:
            old_user = history.pop(0)
            old_assistant = history.pop(0) if history else {"content": ""}
            line = (f'Pessoa: {str(old_user.get("content", ""))[:120]} | '
                    f'Aurora: {str(old_assistant.get("content", ""))[:120]}')
            summary_lines = (self.data["summary"].splitlines() + [line])[-6:]
            self.data["summary"] = "\n".join(summary_lines)[-1200:]

        if _PERSONAL_FACT.search(normalize_words(user_text)):
            facts = self.data["facts"]
            if user_text not in facts:
                facts.append(user_text[:240])
            self.data["facts"] = facts[-24:]

        counts = self.data["topic_counts"]
        words = {
            word for word in re.findall(r"[a-z0-9]{4,}", normalize_words(user_text))
            if word not in _STOP_WORDS
        }
        for word in words:
            counts[word] = min(1000, int(counts.get(word, 0)) + 1)
        if len(counts) > 100:
            keep = sorted(counts, key=counts.get, reverse=True)[:100]
            self.data["topic_counts"] = {word: counts[word] for word in keep}
        self.save()

    def prompt_context(self):
        lines = []
        if self.data["summary"]:
            lines.append("Resumo curto de conversas anteriores, baseado no histórico local:")
            lines.append(self.data["summary"])
        if self.data["facts"]:
            lines.append("Afirmações pessoais feitas explicitamente pela pessoa:")
            lines.append("; ".join(self.data["facts"][-8:]))
        topics = sorted(
            ((word, count) for word, count in self.data["topic_counts"].items() if count > 1),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        if topics:
            lines.append("Termos recorrentes nas conversas: " + ", ".join(word for word, _ in topics))
        return "\n".join(lines)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(self.data, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)
