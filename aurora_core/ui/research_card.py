# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QPalette
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
    "executing": "Consultando ferramentas locais",
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
        self.resize(392, 432)
        self.generation = None
        self.mode = "web"
        self._hide_after_animation = False
        self._tasks = []
        self._finished = set()
        self._live_sources = []
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._dismiss)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.panel = QFrame()
        self.panel.setObjectName("researchPanel")
        outer.addWidget(self.panel)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(18, 16, 18, 17)
        layout.setSpacing(10)

        top = QHBoxLayout()
        brand = QLabel("Aurora")
        brand.setObjectName("brand")
        brand.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(brand)
        self.kind_label = QLabel("Pesquisa")
        self.kind_label.setObjectName("kind")
        self.kind_label.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(self.kind_label)
        top.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("closeButton")
        close.setAccessibleName("Fechar cartão de pesquisa")
        close.clicked.connect(self._dismiss)
        close.setFixedSize(34, 34)
        top.addWidget(close)
        layout.addLayout(top)

        self.query_label = QLabel("")
        self.query_label.setTextFormat(Qt.TextFormat.PlainText)
        self.query_label.setWordWrap(True)
        self.query_label.setObjectName("query")
        layout.addWidget(self.query_label)

        self.stage_label = QLabel("Aguardando")
        self.stage_label.setObjectName("stage")
        self.stage_label.setTextFormat(Qt.TextFormat.PlainText)
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
        self.source_heading.setObjectName("sectionTitle")
        self.source_heading.setTextFormat(Qt.TextFormat.PlainText)
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
        self.source_area.setMinimumHeight(72)
        self.source_area.setMaximumHeight(146)
        layout.addWidget(self.source_area)

        self.answer = QLabel("")
        self.answer.setObjectName("answer")
        self.answer.setTextFormat(Qt.TextFormat.PlainText)
        self.answer.setWordWrap(True)
        self.answer.setMaximumHeight(84)
        self.answer.hide()
        layout.addWidget(self.answer)

        self._opacity = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity.setDuration(240)
        self._opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._position = QPropertyAnimation(self, b"pos", self)
        self._position.setDuration(280)
        self._position.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._opacity.finished.connect(self._finish_dismiss)
        self.colors = self._material_colors()
        self._apply_theme()

    def begin(self, generation, query, anchor, mode="web"):
        self._hide_timer.stop()
        self._hide_after_animation = False
        self._opacity.stop()
        self._position.stop()
        self.generation = generation
        self.mode = mode
        self.kind_label.setText("Local" if mode == "local" else "Pesquisa")
        self._tasks = [str(query)]
        self._finished.clear()
        self._live_sources.clear()
        self.query_label.setText(" ".join(str(query).split())[:220])
        self.answer.clear()
        self.answer.hide()
        self._set_stage("searching")
        self._set_workers(self._tasks, 1)
        self._clear_sources()
        self.source_heading.setVisible(mode != "local")
        self.source_area.setVisible(mode != "local")
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
            duration = event.get("duration_ms")
            timing = f" · {duration / 1000:.1f} s" if duration is not None and event.get("finished_task") else ""
            self.stage_label.setText(f"Pesquisando em paralelo · {completed}/{total} etapas{timing}")
            self.progress.setValue(10 + int(55 * completed / total))
            self._paint_workers()
        elif stage == "executing":
            completed = int(event.get("completed", len(self._finished)))
            total = max(1, int(event.get("total", len(self._tasks))))
            self.stage_label.setText(f"Consultando ferramentas locais · {completed}/{total}")
            self.progress.setValue(12 + int(76 * completed / total))
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
            card.setObjectName("sourceCard")
            card.setStyleSheet(
                f"QFrame#sourceCard {{ background: {self.colors['container']}; "
                f"border: 1px solid {self.colors['outline']}; border-radius: 16px; }}"
            )
            box = QVBoxLayout(card)
            box.setContentsMargins(12, 9, 12, 9)
            box.setSpacing(4)
            title = QLabel(str(item.get("title") or "Fonte consultada"))
            title.setObjectName("sourceTitle")
            title.setTextFormat(Qt.TextFormat.PlainText)
            title.setWordWrap(True)
            meta = " · ".join(value for value in (
                str(item.get("publisher") or item.get("host") or "Web"),
                str(item.get("published") or "data não informada"),
            ) if value)
            source = QLabel(meta)
            source.setObjectName("sourceMeta")
            source.setTextFormat(Qt.TextFormat.PlainText)
            source.setWordWrap(True)
            excerpt = QLabel(" ".join(str(item.get("snippet") or "").split())[:145])
            excerpt.setObjectName("muted")
            excerpt.setTextFormat(Qt.TextFormat.PlainText)
            excerpt.setWordWrap(True)
            box.addWidget(title)
            box.addWidget(source)
            if excerpt.text(): box.addWidget(excerpt)
            self.source_layout.addWidget(card)
        if not items:
            empty = QLabel("Nenhuma fonte verificável chegou à etapa de síntese.")
            empty.setObjectName("muted")
            empty.setTextFormat(Qt.TextFormat.PlainText)
            empty.setWordWrap(True)
            self.source_layout.addWidget(empty)

    def finish(self, generation, answer):
        if generation != self.generation:
            return
        self.answer.setText(self._summary_preview(answer))
        self.answer.setVisible(bool(self.answer.text()))
        self._set_stage("complete")
        self.progress.setValue(100)
        self._hide_timer.start(15_000)

    @staticmethod
    def _summary_preview(answer, limit=220):
        text = " ".join(str(answer or "").split())
        if len(text) <= limit:
            return text
        prefix = text[:limit]
        sentence_end = max(prefix.rfind(mark) for mark in (".", "!", "?"))
        if sentence_end >= limit // 2:
            return prefix[:sentence_end + 1]
        return prefix.rsplit(" ", 1)[0].rstrip(" ,;:") + "…"

    @staticmethod
    def _material_colors():
        window = QApplication.palette().color(QPalette.ColorRole.Window)
        if window.lightness() < 128:
            return {
                "surface": "#211F26", "container": "#2C2933", "container_high": "#36323E",
                "text": "#F4EFF7", "secondary": "#CAC3D2", "muted": "#B0A9B8",
                "primary": "#D0BCFF", "blue": "#B8C8FF", "outline": "#494451",
            }
        return {
            "surface": "#FBF8FF", "container": "#F0ECF5", "container_high": "#E8E1F0",
            "text": "#1D1A22", "secondary": "#49454F", "muted": "#625D68",
            "primary": "#6750A4", "blue": "#52628A", "outline": "#D5CEDD",
        }

    def _apply_theme(self):
        c = self.colors
        self.source_area.setStyleSheet(
            "QScrollArea { background: transparent; border: 0; }"
            f"QScrollBar:vertical {{ background: transparent; width: 5px; margin: 2px 0; }}"
            f"QScrollBar::handle:vertical {{ background: {c['outline']}; border-radius: 2px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        self.source_content.setStyleSheet("background: transparent;")
        self.panel.setStyleSheet(
            f"QFrame#researchPanel {{ background: {c['surface']}; border: 1px solid {c['outline']}; border-radius: 26px; }}"
            f"QLabel {{ color: {c['text']}; background: transparent; border: 0; }}"
            f"QLabel#brand {{ color: {c['primary']}; font-size: 15px; font-weight: 650; }}"
            f"QLabel#kind {{ color: {c['secondary']}; background: {c['container']}; border-radius: 11px; padding: 4px 9px; font-size: 11px; }}"
            f"QLabel#query {{ color: {c['text']}; font-size: 17px; font-weight: 600; }}"
            f"QLabel#stage {{ color: {c['secondary']}; background: {c['container']}; border-radius: 12px; padding: 7px 10px; font-size: 11px; }}"
            f"QLabel#sectionTitle {{ color: {c['secondary']}; font-size: 12px; font-weight: 600; }}"
            f"QLabel#muted {{ color: {c['muted']}; font-size: 11px; }}"
            f"QLabel#task {{ color: {c['secondary']}; font-size: 11px; padding: 3px 2px; }}"
            f"QLabel#sourceTitle {{ color: {c['text']}; font-weight: 600; font-size: 12px; }}"
            f"QLabel#sourceMeta {{ color: {c['muted']}; font-size: 10px; }}"
            f"QLabel#answer {{ color: {c['text']}; background: {c['container']}; border-radius: 16px; padding: 9px 12px; font-size: 12px; }}"
            f"QPushButton#closeButton {{ color: {c['secondary']}; background: {c['container']}; border: 0; border-radius: 17px; font-size: 19px; }}"
            f"QPushButton#closeButton:hover {{ color: {c['text']}; background: {c['container_high']}; }}"
            f"QProgressBar {{ background: {c['container_high']}; border: 0; border-radius: 3px; height: 5px; }}"
            f"QProgressBar::chunk {{ background: {c['primary']}; border-radius: 3px; }}"
        )

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
                widget.hide()
                widget.deleteLater()
        self.worker_labels = []
        for index, task in enumerate(tasks):
            label = QLabel()
            label.setObjectName("task")
            label.setTextFormat(Qt.TextFormat.PlainText)
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
                widget.hide()
                widget.deleteLater()

    def _show_near(self, anchor):
        if anchor is None or anchor.isNull():
            screen = QApplication.primaryScreen()
            area = screen.availableGeometry() if screen else self.geometry()
            self.resize(min(400, max(320, area.width() - 24)), min(448, max(360, area.height() - 32)))
            self.source_area.setMaximumHeight(min(146, max(86, self.height() - 300)))
            target = QPoint(area.right() - self.width() - 24, area.bottom() - self.height() - 24)
        else:
            screen = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
            area = screen.availableGeometry() if screen else self.geometry()
            self.resize(min(400, max(320, area.width() - 24)), min(448, max(360, area.height() - 32)))
            self.source_area.setMaximumHeight(min(146, max(86, self.height() - 300)))
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
        self._hide_after_animation = False
        self._position.setDuration(280)
        self._position.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._opacity.setDuration(240)
        self._opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
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
            self.setWindowOpacity(1.0)
            self.move(target)
            self.raise_()

    def _dismiss(self):
        self._hide_timer.stop()
        if not self.isVisible():
            return
        self._position.stop()
        self._opacity.stop()
        self._hide_after_animation = True
        self._position.setDuration(170)
        self._position.setEasingCurve(QEasingCurve.Type.InCubic)
        self._position.setStartValue(self.pos())
        self._position.setEndValue(self.pos() + QPoint(0, 7))
        self._opacity.setDuration(170)
        self._opacity.setEasingCurve(QEasingCurve.Type.InCubic)
        self._opacity.setStartValue(self.windowOpacity())
        self._opacity.setEndValue(0.0)
        self._position.start()
        self._opacity.start()

    def _finish_dismiss(self):
        if self._hide_after_animation and self.windowOpacity() < 0.05:
            self._hide_after_animation = False
            self.hide()
