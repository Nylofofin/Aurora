from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QScrollArea, QVBoxLayout, QWidget,
)
import re
from urllib.parse import urlparse


_STAGES = {
    "planning": "Preparando pesquisa",
    "planning_complete": "Pesquisa preparada",
    "searching": "Pesquisando em paralelo",
    "validating": "Validando fontes",
    "reading": "Abrindo páginas verificadas",
    "synthesizing": "Preparando resposta",
    "complete": "Concluído",
}


class ResearchCard(QWidget):
    """Small contextual window for live research progress and sourced results."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Aurora · pesquisa")
        self.resize(366, 390)
        self.generation = None
        self._tasks = []
        self._finished = set()
        self._live_sources = []
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame()
        self.panel.setObjectName("researchPanel")
        self.panel.setStyleSheet(
            "QFrame#researchPanel { background: rgba(22,24,34,246); "
            "border: 1px solid rgba(188,170,255,100); border-radius: 16px; }"
            "QLabel { color: #f2f0fa; background: transparent; border: 0; }"
            "QLabel#muted { color: #a4a5b3; font-size: 11px; }"
            "QLabel#task { color: #dbd9e5; font-size: 11px; }"
            "QLabel#sourceTitle { color: #f4f2fc; font-weight: 600; font-size: 11px; }"
            "QLabel#sourceMeta { color: #aaaabd; font-size: 10px; }"
            "QPushButton { color: #c9c2dc; background: transparent; border: 0; "
            "font-size: 17px; padding: 1px 5px; }"
            "QProgressBar { background: #ffffff14; border: 0; border-radius: 2px; height: 4px; }"
            "QProgressBar::chunk { background: #aa9aff; border-radius: 2px; }"
        )
        outer.addWidget(self.panel)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(9)

        top = QHBoxLayout()
        brand = QLabel("AURORA  ·  ORCHESTRA")
        brand.setStyleSheet("color:#c9bbff;font-size:10px;font-weight:650;letter-spacing:1px")
        top.addWidget(brand)
        top.addStretch(1)
        close = QPushButton("×")
        close.setAccessibleName("Fechar cartão de pesquisa")
        close.clicked.connect(self.hide)
        top.addWidget(close)
        layout.addLayout(top)

        self.query_label = QLabel("")
        self.query_label.setWordWrap(True)
        self.query_label.setStyleSheet("font-size:14px;font-weight:600")
        layout.addWidget(self.query_label)

        self.stage_label = QLabel("Aguardando")
        self.stage_label.setObjectName("muted")
        layout.addWidget(self.stage_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.worker_list = QVBoxLayout()
        self.worker_list.setSpacing(4)
        layout.addLayout(self.worker_list)
        self.worker_labels = []

        self.source_heading = QLabel("Fontes")
        self.source_heading.setStyleSheet("font-size:11px;font-weight:600;color:#d8d2ed")
        layout.addWidget(self.source_heading)
        self.source_area = QScrollArea()
        self.source_area.setWidgetResizable(True)
        self.source_area.setFrameShape(QFrame.Shape.NoFrame)
        self.source_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_area.setStyleSheet("QScrollArea { background: transparent; }")
        self.source_content = QWidget()
        self.source_layout = QVBoxLayout(self.source_content)
        self.source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_layout.setSpacing(6)
        self.source_area.setWidget(self.source_content)
        self.source_area.setMaximumHeight(132)
        layout.addWidget(self.source_area)

        self.answer = QLabel("")
        self.answer.setWordWrap(True)
        self.answer.setStyleSheet("color:#d7d4e0;font-size:11px")
        layout.addWidget(self.answer)

        self._opacity = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity.setDuration(190)
        self._opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._position = QPropertyAnimation(self, b"pos", self)
        self._position.setDuration(250)
        self._position.setEasingCurve(QEasingCurve.Type.OutCubic)

    def begin(self, generation, query, anchor):
        self._hide_timer.stop()
        self.generation = generation
        self._tasks = [str(query)]
        self._finished.clear()
        self._live_sources.clear()
        self.query_label.setText(" ".join(str(query).split())[:180])
        self.answer.clear()
        self._set_stage("searching")
        self._set_workers(self._tasks, 1)
        self._clear_sources()
        self.progress.setValue(8)
        self._show_near(anchor)

    def update_progress(self, generation, event):
        if generation != self.generation or not isinstance(event, dict):
            return
        stage = event.get("stage", "searching")
        tasks = event.get("tasks")
        if isinstance(tasks, list) and tasks:
            self._tasks = [str(task)[:120] for task in tasks[:3]]
            self._set_workers(self._tasks, max(1, int(event.get("workers", len(self._tasks)))))
        finished_task = event.get("finished_task")
        if finished_task:
            self._finished.add(str(finished_task))
        sources = event.get("sources")
        result = event.get("result")
        if isinstance(sources, list):
            self._live_sources.extend(item for item in sources if isinstance(item, dict))
            self._live_sources = self._dedupe(self._live_sources)[:4]
            self.set_sources(generation, self._live_sources)
        elif result:
            self._live_sources.extend(self._parse_sources(result))
            self._live_sources = self._dedupe(self._live_sources)[:4]
            self.set_sources(generation, self._live_sources)
        self._set_stage(stage)
        if stage == "planning":
            self.progress.setValue(max(self.progress.value(), 8))
        elif stage == "planning_complete":
            timing = int(event.get("planning_ms", 0))
            self.stage_label.setText(f"Plano local pronto · {timing / 1000:.1f} s · {len(self._tasks)} etapas")
            self.progress.setValue(max(self.progress.value(), 9))
        elif stage == "searching":
            completed = int(event.get("completed", len(self._finished)))
            total = max(1, int(event.get("total", len(self._tasks))))
            self.stage_label.setText(f"Pesquisando em paralelo · {completed}/{total} etapas")
            self.progress.setValue(10 + int(55 * completed / total))
            self._paint_workers()
        elif stage == "validating":
            counts = event.get("counts", {})
            rejected = event.get("rejected", {})
            if counts:
                extracted = sum(int(value.get("extraidos", 0)) for value in counts.values())
                related = sum(int(value.get("relevantes", 0)) for value in counts.values())
                self.stage_label.setText(f"Validando fontes · {related}/{extracted} relacionadas · {sum(rejected.values())} descartes")
            self.progress.setValue(76)
            self._paint_workers(force_done=True)
        elif stage == "reading":
            completed = int(event.get("completed", 0))
            total = max(1, int(event.get("total", 1)))
            self.stage_label.setText(f"Abrindo páginas verificadas · {completed}/{total}")
            self.progress.setValue(76 + int(11 * completed / total))
        elif stage == "synthesizing":
            self.progress.setValue(88)

    def set_sources(self, generation, items):
        if generation != self.generation:
            return
        self._clear_sources()
        for item in list(items)[:4]:
            card = QFrame()
            card.setStyleSheet("QFrame { background: rgba(255,255,255,8); border: 1px solid #ffffff18; border-radius: 9px; }")
            box = QVBoxLayout(card)
            box.setContentsMargins(9, 7, 9, 7)
            box.setSpacing(2)
            title = QLabel(str(item.get("title") or "Fonte consultada"))
            title.setObjectName("sourceTitle")
            title.setWordWrap(True)
            meta = " · ".join(value for value in (
                str(item.get("publisher") or item.get("host") or "Web"),
                str(item.get("published") or "data não informada"),
            ) if value)
            source = QLabel(meta)
            source.setObjectName("sourceMeta")
            source.setWordWrap(True)
            excerpt = QLabel(" ".join(str(item.get("snippet") or "").split())[:180])
            excerpt.setObjectName("muted")
            excerpt.setWordWrap(True)
            box.addWidget(title)
            box.addWidget(source)
            if excerpt.text(): box.addWidget(excerpt)
            self.source_layout.addWidget(card)
        if not items:
            empty = QLabel("Nenhuma fonte verificável chegou à etapa de síntese.")
            empty.setObjectName("muted")
            empty.setWordWrap(True)
            self.source_layout.addWidget(empty)

    def finish(self, generation, answer):
        if generation != self.generation:
            return
        self.answer.setText(" ".join(str(answer).split())[:420])
        self._set_stage("complete")
        self.progress.setValue(100)
        self._hide_timer.start(15_000)

    def _set_stage(self, stage):
        self.stage_label.setText(_STAGES.get(stage, str(stage).replace("_", " ").capitalize()))

    @staticmethod
    def _parse_sources(output):
        items = []
        for line in str(output or "").splitlines()[1:]:
            if " — " not in line:
                continue
            label, url = line.rsplit(" — ", 1)
            snippet = ""
            if " :: " in label:
                label, snippet = label.split(" :: ", 1)
            match = re.search(r"\s*\[([^\]]+?)\s*[·|]\s*([^\]]+)\]$", label)
            publisher = published = ""
            if match:
                publisher, published = match.groups()
                label = label[:match.start()].strip()
            items.append({
                "title": label.strip(), "snippet": snippet[:240],
                "publisher": publisher,
                "published": published,
                "host": (urlparse(url.strip()).hostname or "").removeprefix("www."),
                "url": url.strip(),
            })
        return items

    @staticmethod
    def _dedupe(items):
        seen = set()
        result = []
        for item in items:
            parsed = urlparse(str(item.get("url", "")))
            key = parsed._replace(query="", fragment="").geturl().rstrip("/").casefold()
            if not parsed.scheme or not parsed.netloc or key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _set_workers(self, tasks, workers):
        while self.worker_list.count():
            item = self.worker_list.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.worker_labels = []
        for index, task in enumerate(tasks):
            label = QLabel()
            label.setObjectName("task")
            label.setWordWrap(True)
            label._task_text = task
            label._task_index = index
            label._worker_limit = workers
            self.worker_list.addWidget(label)
            self.worker_labels.append(label)
        self._paint_workers()

    def _paint_workers(self, force_done=False):
        for label in self.worker_labels:
            task = label._task_text
            done = force_done or task in self._finished
            state = "concluída" if done else ("em paralelo" if label._task_index < label._worker_limit else "na fila")
            mark = "✓" if done else ("◌" if state == "em paralelo" else "·")
            label.setText(f"{mark}  {task}  ·  {state}")

    def _clear_sources(self):
        while self.source_layout.count():
            item = self.source_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _show_near(self, anchor):
        if anchor is None or anchor.isNull():
            screen = QApplication.primaryScreen()
            area = screen.availableGeometry() if screen else self.geometry()
            target = QPoint(area.right() - self.width() - 24, area.bottom() - self.height() - 24)
        else:
            screen = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
            area = screen.availableGeometry() if screen else self.geometry()
            gap = 14
            left = anchor.left() - self.width() - gap
            right = anchor.right() + gap
            x = left if left >= area.left() else right
            if x + self.width() > area.right():
                x = anchor.left()
            target = QPoint(x, anchor.center().y() - self.height() // 2)
            target.setX(max(area.left() + 8, min(target.x(), area.right() - self.width() - 8)))
            target.setY(max(area.top() + 8, min(target.y(), area.bottom() - self.height() - 8)))
        self._position.stop()
        self._opacity.stop()
        if not self.isVisible():
            self.move(target + QPoint(0, 8))
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            self._position.setStartValue(self.pos())
            self._position.setEndValue(target)
            self._opacity.setStartValue(0.0)
            self._opacity.setEndValue(1.0)
            self._position.start()
            self._opacity.start()
        else:
            self.move(target)
            self.raise_()
