from __future__ import annotations

from pathlib import Path
import os
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchSubagent:
    """A bounded, independent web-research assignment; never a model process."""
    name: str
    query: str


def plan_research_subagents(query: str, max_agents: int = 3) -> tuple[ResearchSubagent, ...]:
    """Split only explicit multi-part questions; otherwise retain one fast task."""
    text=" ".join(str(query).split()).strip()
    limit=max(1,min(3,int(max_agents)))
    if not text:
        return ()

    plain=unicodedata.normalize("NFKD",text).encode("ascii","ignore").decode().casefold()
    pieces=[]
    explicit_comparison=False
    # Comparison wording is the strongest signal that each side needs its own
    # source set before the parent can compare them.
    comparison=re.search(
        r"\b(?:compare|comparar|comparacao|diferenca(?:s)?\s+entre)\s+(.+?)\s+"
        r"(?:versus|vs\.?|contra|e|and)\s+(.+?)(?:[?.!]|$)", plain
    )
    if comparison:
        sides=[text[comparison.start(1):comparison.end(1)],text[comparison.start(2):comparison.end(2)]]
        sides=[re.sub(r"\s+", " ", side).strip(" \t,.;:?!") for side in sides]
        if all(len(side.split())>=1 for side in sides) and sides[0].casefold()!=sides[1].casefold():
            pieces=sides
            explicit_comparison=True

    # Split independent questions or explicit additional actions. Do not split
    # a simple noun list such as "notícias de ciência e tecnologia".
    if not pieces:
        parts=re.split(r"\s*\?\s+|\s*;\s*|\s+e\s+tambem\s+|\s+alem disso\s+",plain)
        if len(parts)>1:
            # Recover exact source spans while retaining punctuation-free clauses.
            original_parts=re.split(r"\s*\?\s+|\s*;\s*|\s+e\s+tamb[eé]m\s+|\s+al[eé]m disso\s+",text,flags=re.I)
            pieces=[part.strip(" \t,.;:?!") for part in original_parts if part.strip(" \t,.;:?!")]
        else:
            repeated_question=re.search(
                r"\s+e\s+(?=(?:quem|qual|quais|quanto|quantas|quando|onde|como|por que)\b)",plain
            )
            if repeated_question:
                original_parts=re.split(
                    r"\s+e\s+(?=(?:quem|qual|quais|quanto|quantas|quando|onde|como|por que)\b)",text,
                    maxsplit=1,flags=re.I,
                )
                pieces=[part.strip(" \t,.;:?!") for part in original_parts if part.strip(" \t,.;:?!")]

    def looks_standalone(part):
        normalized=unicodedata.normalize("NFKD",part).encode("ascii","ignore").decode().casefold()
        words=re.findall(r"[a-z0-9]+",normalized)
        stop={"the","and","for","with","from","what","when","where","who","why","how","qual","quais","quem","quando","onde","como","porque","isso","esse","essa","dele","dela","uma","uns","das","dos","de","do","da","em","no","na","e","ou","um","a","o","as","os","foi","sao","esta","hoje","agora","atual","atualmente"}
        return len({word for word in words if (len(word)>2 or word.isdigit()) and word not in stop})>=2

    if len(pieces)<2 or (not explicit_comparison and not all(looks_standalone(part) for part in pieces)):
        return (ResearchSubagent("Pesquisa principal",text),)
    selected=pieces[:limit]
    return tuple(ResearchSubagent(f"Subagente {index} · {part[:48]}",part) for index,part in enumerate(selected,1))


def resource_worker_limit(task_count: int, *, load_per_cpu=None, available_ram=None,
                          cpu_count=None) -> int:
    """Bound concurrent read-only web workers using current host pressure."""
    task_count = max(0, int(task_count))
    if task_count < 2:
        return task_count
    cpu_count = max(1, int(cpu_count or os.cpu_count() or 1))
    if load_per_cpu is None:
        try:
            load_per_cpu = os.getloadavg()[0] / cpu_count
        except (AttributeError, OSError):
            load_per_cpu = 0.0
    if available_ram is None:
        try:
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                if line.startswith("MemAvailable:"):
                    available_ram = int(line.split()[1]) * 1024
                    break
        except (OSError, ValueError):
            available_ram = None
    if cpu_count <= 2 or load_per_cpu >= 0.90 or (available_ram is not None and available_ram < 2 * 1024**3):
        return 1
    if load_per_cpu >= 0.55 or (available_ram is not None and available_ram < 6 * 1024**3):
        return min(2, task_count)
    return min(3, task_count)
